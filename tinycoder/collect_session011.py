"""Publish only verified measurements from both hosted Session011 runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import lzma
from pathlib import Path
import struct

from .rome20 import save_json

BEGIN = "<!-- SESSION-011-COMPARISON-START -->"
END = "<!-- SESSION-011-COMPARISON-END -->"


def merge_stress_reports(reports: list[dict]) -> dict:
    """Combine three independently measured CPU variants with identity checks."""
    if len(reports) != 3:
        raise ValueError("Expected exactly three independently measured stress levels")
    first = reports[0]
    for item in reports:
        if (item.get("status") != "completed" or item.get("track") != "stress" or
                item["benchmark_ids"] != first["benchmark_ids"] or
                item["source_failure_ids"] != first["source_failure_ids"] or
                item["source_archive_sha256"] != first["source_archive_sha256"] or
                item["baseline"]["passed_task_ids"] != first["baseline"]["passed_task_ids"] or
                item["baseline"]["ast_valid_count"] != first["baseline"]["ast_valid_count"]):
            raise ValueError("Stress variants do not share identical source/baseline identity")
    variants = {}
    for report in reports:
        for key, value in report["variants"].items():
            if key in variants:
                raise ValueError("Duplicate norm threshold result")
            variants[key] = value
    if set(variants) != {"15%", "30%", "50%"}:
        raise ValueError("Incomplete stress norm sweep")
    return {**first, "variants": {k: variants[k] for k in ("15%", "30%", "50%")},
            "reversible_factors": "experiments/unbounded_surgery_factors.safetensors",
            "task_predictions": "experiments/unbounded_predictions.json",
            "merge_method": "Matched independent GitHub Actions matrix jobs, one 70-task evaluation per level"}


def merge_factor_files(paths: list[Path], destination: Path):
    """Losslessly merge safetensors without requiring PyTorch in the collector."""
    if len(paths) != 3:
        raise ValueError("Expected three level-specific tensor files")
    entries = {}
    bodies = []
    length = 0
    for path in paths:
        data = path.read_bytes()
        header_len, = struct.unpack("<Q", data[:8])
        if header_len <= 0 or header_len > 1000000:
            raise ValueError("Corrupt safetensors header length")
        header = json.loads(data[8:8+header_len])
        body = data[8+header_len:]
        for key, meta in header.items():
            if key == "__metadata__":
                continue
            start, stop = meta["data_offsets"]
            if (key in entries or not 0 <= start < stop <= len(body) or
                    meta["dtype"] != "F32"):
                raise ValueError("Duplicate/unsupported/corrupt factor tensor")
            piece = body[start:stop]
            entries[key] = {"dtype": meta["dtype"], "shape": meta["shape"],
                            "data_offsets": [length, length + len(piece)]}
            bodies.append(piece)
            length += len(piece)
    if len(entries) != 24:
        raise ValueError("Expected 4 layers x 2 factors x 3 stress levels")
    metadata = json.dumps(entries, separators=(",", ":")).encode("utf-8")
    metadata += b" " * (-len(metadata) % 8)
    destination.write_bytes(struct.pack("<Q", len(metadata)) + metadata + b"".join(bodies))
    return {"tensor_count": len(entries), "data_bytes": length}


def compact_stress_factors(source: Path, destination: Path):
    """Losslessly deduplicate identical right factors across stress variants.

    For each layer: delta = `level%.layerX.mlp_down_proj.left` @
    `shared.layerX.mlp_down_proj.right`. Original lefts are preserved byte-for-
    byte; byte equality of the three right operands is mandatory.
    """
    data = source.read_bytes()
    header_len, = struct.unpack("<Q", data[:8])
    header = json.loads(data[8:8+header_len])
    body = data[8+header_len:]

    def part(key):
        item = header[key]
        a, b = item["data_offsets"]
        if item["dtype"] != "F32" or not 0 <= a < b <= len(body):
            raise ValueError("Unsupported/corrupt factor: " + key)
        return item, body[a:b]

    entries, blobs, offset = {}, [], 0

    def add(key, item, blob):
        nonlocal offset
        entries[key] = {"dtype": item["dtype"], "shape": item["shape"],
                        "data_offsets": [offset, offset + len(blob)]}
        blobs.append(blob)
        offset += len(blob)

    for layer in (6, 8, 10, 14):
        name = f"layer{layer}.mlp_down_proj"
        original_right = None
        for level in (15, 30, 50):
            prefix = f"{level}%.{name}"
            left_meta, left = part(prefix + ".left")
            right_meta, right = part(prefix + ".right")
            add(prefix + ".left", left_meta, left)
            if original_right is None:
                original_right = (right_meta, right)
            elif original_right[0]["shape"] != right_meta["shape"] or original_right[1] != right:
                raise ValueError("Right factors are not bit-identical; lossless packing impossible")
        add("shared." + name + ".right", *original_right)
    if len(entries) != 16:
        raise RuntimeError("Unexpected compact factor count")
    entries["__metadata__"] = {
        "format": "session011_stress_shared_right_v1",
        "reconstruction": "delta = [level%].[layer].left @ shared.[layer].right",
        "levels": "15%,30%,50%",
        "right_equality": "verified byte-for-byte before deduplication",
    }
    meta = json.dumps(entries, separators=(",", ":")).encode("utf-8")
    meta += b" " * (-len(meta) % 8)
    destination.write_bytes(struct.pack("<Q", len(meta)) + meta + b"".join(blobs))
    return {"factor_count": 16, "data_bytes": offset,
            "storage": "12 exact left tensors, 4 byte-identical shared right tensors"}


def pack_stress_factors_lossless(source: Path, destination: Path) -> dict:
    """Create a valid .safetensors U8 container of an XZ-compressed factor set.

    This is lossless even when CPU runs generate slightly different right-side
    factors. To recover native factor tensors, use unpack_stress_factors_lossless
    and safetensors.torch.load on the recovered bytes.
    """
    original = source.read_bytes()
    packed = lzma.compress(original, format=lzma.FORMAT_XZ, preset=9)
    digest = hashlib.sha256(original).hexdigest()
    header = {
        "packed_original_safetensors": {"dtype": "U8", "shape": [len(packed)],
                                         "data_offsets": [0, len(packed)]},
        "__metadata__": {"container": "session011_lossless_xz_v1",
                         "codec": "xz/lzma", "original_sha256": digest,
                         "original_bytes": str(len(original)),
                         "replay": "unpack_stress_factors_lossless(path) then safetensors.torch.load(bytes)"},
    }
    meta = json.dumps(header, separators=(",", ":")).encode("utf-8")
    meta += b" " * (-len(meta) % 8)
    destination.write_bytes(struct.pack("<Q", len(meta)) + meta + packed)
    verified = unpack_stress_factors_lossless(destination)
    if verified != original:
        raise RuntimeError("Compressed factor container did not roundtrip exactly")
    return {"status": "verified_lossless", "original_sha256": digest,
            "original_bytes": len(original), "packed_bytes": destination.stat().st_size}


def unpack_stress_factors_lossless(path: Path) -> bytes:
    raw = path.read_bytes()
    header_len, = struct.unpack("<Q", raw[:8])
    if not 0 < header_len < 1000000:
        raise ValueError("Invalid factor container header")
    header = json.loads(raw[8:8+header_len])
    meta = header["__metadata__"]
    if meta["container"] != "session011_lossless_xz_v1" or meta["codec"] != "xz/lzma":
        raise ValueError("Unsupported factor packing protocol")
    tensor = header["packed_original_safetensors"]
    start, end = tensor["data_offsets"]
    packed = raw[8+header_len:]
    if start != 0 or end != len(packed) or tensor["shape"] != [len(packed)]:
        raise ValueError("Compressed payload bounds invalid")
    expanded = lzma.decompress(packed, format=lzma.FORMAT_XZ)
    if (len(expanded) != int(meta["original_bytes"]) or
            hashlib.sha256(expanded).hexdigest() != meta["original_sha256"]):
        raise ValueError("Restored factor hash mismatch")
    return expanded


def combine(stress: dict, rank32: dict) -> dict:
    if (stress.get("status") != "completed" or stress.get("track") != "stress" or
            rank32.get("status") != "completed" or rank32.get("track") != "rank32" or
            stress.get("session") != "011" or rank32.get("session") != "011"):
        raise ValueError("Both genuine Session011 run reports are required")
    baseline_keys = ("passed_task_ids", "pass_at_1", "pass_count", "ast_valid_count")
    if (stress["benchmark_ids"] != rank32["benchmark_ids"] or
            stress["source_failure_ids"] != rank32["source_failure_ids"] or
            any(stress["baseline"][k] != rank32["baseline"][k] for k in baseline_keys)):
        raise ValueError("Runs disagree on benchmark, source or measured baseline")
    if (list(stress["variants"]) != ["15%", "30%", "50%"] or
            list(rank32["variants"]) != ["rank32"]):
        raise ValueError("Missing or misnamed experimental variant")
    return {
        "status": "completed", "session": "011", "base_model": stress["base_model"],
        "benchmark_ids": stress["benchmark_ids"],
        "source_failure_ids": stress["source_failure_ids"],
        "baseline": stress["baseline"],
        "variants": {**stress["variants"], **rank32["variants"]},
        "individual_branch_reports": {
            "stress": "exp/08-unbounded-norm:experiments/unbounded_stress_report.json",
            "rank32": "exp/09-rank32-surgery:experiments/unbounded_report.json"},
        "factors": {
            "stress": "exp/08-unbounded-norm:experiments/unbounded_surgery_factors.safetensors (lossless XZ-in-safetensors container)",
            "rank32": "exp/09-rank32-surgery:experiments/rank32_surgery_factors.safetensors"},
        "stress_factor_storage": "The stress file is a valid safetensors U8 container of a losslessly XZ-compressed native 24-factor safetensors. Recover with tinycoder.collect_session011.unpack_stress_factors_lossless(path) followed by safetensors.torch.load(recovered_bytes). Original float32 factors are bit-identical upon restoration.",
        "caution": "Reused HumanEval/94–163; exploratory, not independent validation. Three discrete stress points cannot establish an exact failure threshold. Edit activation targets are mechanistic proxies.",
    }


def markdown(report: dict) -> str:
    b = report["baseline"]
    n = len(report["benchmark_ids"])
    header = [
        "### Session 011 — four-layer stress and rank-32 covariance surgery",
        "",
        "Both experiments used CPU direct weight edits derived only from 50 archived baseline failures below HumanEval/94."
        " These 70 comparison tasks have appeared in earlier sessions and are **not an independent holdout**.",
        "",
        "| Variant | Execution pass@1 | AST-valid | Mean next-token entropy (nats) | Reference perplexity |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| Unedited base | {b['pass_count']}/{n} ({100*b['pass_at_1']:.1f}%) | {b['ast_valid_count']}/{n} | "
        f"{b['diagnostics']['next_token_entropy_nats']:.3f} | {b['diagnostics']['reference_perplexity']:.2f} |",
    ]
    for variant, details in report["variants"].items():
        execution = details["execution"]
        stats = details["diagnostics"]
        if execution is None:
            results, syntax = "N/A (failed)", "N/A"
        else:
            results = f"{execution['after_passes']}/{n} ({100*execution['pass_at_1_after']:.1f}%)"
            syntax = f"{execution['syntax_after']['valid']}/{n}"
        entropy = (f"{stats['next_token_entropy_nats']:.3f}"
                   if stats["next_token_entropy_nats"] is not None else "N/A")
        perplexity = (f"{stats['reference_perplexity']:.2f}"
                      if stats["reference_perplexity"] is not None else "N/A")
        header.append(f"| {variant} ({details['status']}) | {results} | {syntax} | {entropy} | {perplexity} |")
    header.extend(["", "All model-written code was assessed in a read-only, network-disabled Docker sandbox.",
                   "Next-token entropy is averaged over 12 fixed prompts; reference perplexity uses 8 source solutions,"
                   " up to 32 tokens each. All edits are reversible and do not use gradients or optimizers.",
                   "The 24 stress factors are stored losslessly inside a compressed `.safetensors` container"
                   " (XZ payload). To replay them, decode with `unpack_stress_factors_lossless()` from"
                   " `tinycoder.collect_session011`, then load the recovered bytes with `safetensors.torch.load()`.", ""])
    for variant, details in report["variants"].items():
        execution = details["execution"]
        if execution is not None:
            passes = ", ".join(execution["passed_ids_after"]) or "None"
            failed = ", ".join(execution["failed_ids_after"]) or "None"
            header.extend([f"- **{variant} passed IDs:** {passes}.",
                           f"- **{variant} failed IDs:** {failed}."])
    header.extend(["", "Measured reports: [`experiments/unbounded_report.json`](experiments/unbounded_report.json)"
                   " and the individual branch artifacts. The 15/30/50% points cannot identify a continuous"
                   " breakdown threshold, and no positive capability claim follows from a finite sample.", ""])
    return "\n".join(header)


def update_readme(path: Path, section: str):
    old = path.read_text(encoding="utf-8")
    wrapped = f"{BEGIN}\n{section}\n{END}"
    if BEGIN in old or END in old:
        if old.count(BEGIN) != 1 or old.count(END) != 1:
            raise ValueError("Partial or duplicate Session011 README markers")
        old = old[:old.index(BEGIN)] + wrapped + old[old.index(END)+len(END):]
    else:
        old = old.rstrip() + "\n\n" + wrapped + "\n"
    path.write_text(old, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stress", action="append", required=True,
                        help="Repeat for three independent 15/30/50 percent run reports")
    parser.add_argument("--rank32", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--readme", required=True)
    parser.add_argument("--stress-report-output")
    parser.add_argument("--factor-file", action="append", default=[])
    parser.add_argument("--factor-output")
    parser.add_argument("--predictions-file", action="append", default=[])
    parser.add_argument("--rank32-predictions")
    parser.add_argument("--predictions-output")
    args = parser.parse_args()
    reports = [json.loads(Path(p).read_text()) for p in args.stress]
    if len(reports) == 3:
        stress = merge_stress_reports(reports)
    elif len(reports) == 1:
        stress = reports[0]
    else:
        parser.error("Pass a single complete report or three independent stress reports")
    if args.stress_report_output:
        save_json(Path(args.stress_report_output), stress)
    if args.factor_file:
        if not args.factor_output:
            parser.error("Provide --factor-output when merging factor files")
        print("MERGED FACTORS", merge_factor_files([Path(p) for p in args.factor_file],
                                                   Path(args.factor_output)))
    if args.predictions_file:
        if not args.predictions_output:
            parser.error("Provide --predictions-output when merging predictions")
        cases = {}
        for path in args.predictions_file:
            records = json.loads(Path(path).read_text())
            if records["task_ids"] != stress["benchmark_ids"]:
                raise ValueError("Variant predictions do not match benchmark IDs")
            for name, rows in records["variants"].items():
                if name in cases or [x["task_id"] for x in rows] != records["task_ids"]:
                    raise ValueError("Duplicate/invalid task-level predictions")
                cases[name] = rows
        if set(cases) != {"15%", "30%", "50%"}:
            raise ValueError("Missing stress variant predictions")
        if args.rank32_predictions:
            rank = json.loads(Path(args.rank32_predictions).read_text())
            if (rank["task_ids"] != stress["benchmark_ids"] or
                    list(rank["variants"]) != ["rank32"] or
                    [x["task_id"] for x in rank["variants"]["rank32"]] != rank["task_ids"]):
                raise ValueError("Rank32 task-level predictions mismatch benchmark")
            cases["rank32"] = rank["variants"]["rank32"]
        save_json(Path(args.predictions_output), {
            "task_ids": stress["benchmark_ids"],
            "variants": {k: cases[k] for k in ("15%", "30%", "50%", "rank32") if k in cases}})
    summary = combine(stress,
                      json.loads(Path(args.rank32).read_text()))
    save_json(Path(args.output), summary)
    update_readme(Path(args.readme), markdown(summary))
    print("SESSION011 verified variants:", list(summary["variants"]))


if __name__ == "__main__":
    main()
