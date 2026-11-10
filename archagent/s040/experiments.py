"""Session 040 Track A-D experiment driver (resumable, fail-closed evidence).

For every (track, task) pair the driver:
  1. builds the track prompt from the frozen v2 contract (prompts.py);
  2. generates with the frozen Qwen model (greedy, deterministic seed);
  3. extracts the construct mechanically (L-TRIM brace balance; schemas keep
     full text) with one forced-continuation retry on near-empty output
     (L-EOS);
  4. stages the candidate and evaluates it inside the restricted execution
     tier (unshare local / Docker CI) via the matching evaluator;
  5. writes one JSON evidence record: prompt text + SHA-256, raw generation,
     usage (tokens/seconds/seed), extracted candidate, verdict, attribution
     (QWEN_GENERATED + controller-assembled for track D), wall time.

Track C reuses Track B's attempt-1 evidence and runs <= 3 repair rounds with
the evaluator's failing checks quoted back (full regeneration, never FIM).

Resumability: evidence files are keyed by track/domain/skill; completed
pairs are skipped on restart. The sample and all prompts derive ONLY from
train/dev contracts; the 24 holdout tasks stay sealed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.s040 import exec as s040exec  # noqa: E402
from archagent.s040 import (integration_eval, integration_fixtures, prompts,  # noqa: E402
                            react_eval, route_eval_s039_compat as compat,
                            schema_eval)

TRACKS = ("A", "B", "C", "D")
SAMPLE_DOMAINS = {"train": ("aquarium", "observatory"), "dev": ("radiostation")}
EVIDENCE_DIR = Path("experiments/z040-autonomous-fullstack/tracks")
NEAR_EMPTY_CHARS = 100
MAX_REPAIRS = 3

FILE_FOR_SKILL = {
    "schema-relationship": "output.prisma",
    "state-invariant": "output.ts",
    "api-get-filter": "output.ts",
    "api-post-validation": "output.ts",
    "react-interaction": "output.tsx",
    "fullstack-integration": "output.tsx",
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_sample(repo: Path) -> list[dict]:
    """Frozen paired sample: 3 domains x 6 skills from train/dev only."""
    from archagent.s039 import scenarios
    sample = []
    for split, domains in SAMPLE_DOMAINS.items():
        suite = scenarios.load_split(repo, split, suite_version=2)
        for task in suite["tasks"]:
            if task["domain"] in domains:
                entry = dict(task)
                if task["skill"] == "fullstack-integration":
                    spec = integration_fixtures.integration_contract(
                        repo, split, task["id"])
                    entry["_route_path"] = spec["route_path"]
                    entry["_envelope_key"] = spec["envelope_key"]
                sample.append(entry)
    return sample


def extract_construct(anchor: str, generation: str, skill: str) -> tuple[str, bool]:
    """L-TRIM: keep anchor+generation up to brace balance (TS/TSX); schemas
    keep the full text. Balance is counted from the anchor's FINAL opening
    brace (depth starts at 1 at the start of the generation), so braces
    inside the anchor itself (e.g. the destructuring ``{ data }``) cannot
    truncate the construct. Returns (candidate, balanced)."""
    text = anchor + generation
    if skill == "schema-relationship":
        return text, True
    depth = 1
    for i, ch in enumerate(generation):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[: len(anchor) + i + 1], True
    return text, False


def forced_anchor(anchor: str, skill: str) -> str:
    if skill == "schema-relationship":
        return anchor + "  id String @id @default(cuid())\n"
    if skill in ("react-interaction", "fullstack-integration"):
        return anchor + "  const ["
    return anchor + "  const "


def evaluate_candidate(repo: Path, entry: dict, candidate_dir: Path,
                       backend: str, image: str | None) -> dict:
    skill = entry["skill"]
    split = "dev" if entry["domain"] in SAMPLE_DOMAINS["dev"] else "train"
    if skill == "schema-relationship":
        return schema_eval.evaluate(repo, split, entry["id"], candidate_dir,
                                    backend=backend, image=image)
    if skill == "state-invariant":
        return compat.evaluate_invariant(repo, split, entry["id"], candidate_dir,
                                         backend=backend, image=image)
    if skill in ("api-get-filter", "api-post-validation"):
        return compat.evaluate_route(repo, split, entry["id"], candidate_dir,
                                     backend=backend, image=image)
    if skill == "react-interaction":
        return react_eval.evaluate(repo, split, entry["id"], candidate_dir,
                                   backend=backend, image=image)
    if skill == "fullstack-integration":
        return integration_eval.evaluate(repo, split, entry["id"], candidate_dir,
                                         backend=backend, image=image)
    raise ValueError(skill)


def _stage_candidate(text: str, skill: str, stage_root: Path) -> Path:
    cand = stage_root / "candidate"
    if cand.exists():
        shutil.rmtree(cand)
    cand.mkdir(parents=True)
    (cand / FILE_FOR_SKILL[skill]).write_text(text, encoding="utf-8")
    return cand


def _failing_checks(verdict: dict) -> list[dict]:
    checks = verdict.get("checks")
    if not isinstance(checks, list):
        return []
    return [c for c in checks if isinstance(c, dict) and c.get("passed") is not True]


def _generate(model, prompt: str, seed: int, max_tokens: int) -> tuple[str, dict]:
    return model.generate(prompt, max_tokens=max_tokens, seed=seed, stochastic=False)


def run_pair(repo: Path, model, track: str, entry: dict, backend: str,
             image: str | None, track_b_first: dict | None = None) -> dict:
    """Run one (track, task) pair; returns the evidence record."""
    task_id = entry["id"]
    skill = entry["skill"]
    t_start = time.time()
    record = {
        "track": track, "task_id": task_id, "skill": skill,
        "domain": entry["domain"], "split": "dev" if entry["domain"] in SAMPLE_DOMAINS["dev"] else "train",
        "decoding": "greedy",
        "attribution": "QWEN_GENERATED",
        "attempts": [],
    }
    if track == "D":
        record["attribution"] = "QWEN_GENERATED_CONTROLLER_ASSEMBLED"

    def attempt(prompt: str, seed: int, max_tokens: int, note: str,
                anchor: str | None = None) -> dict:
        raw, usage = _generate(model, prompt, seed, max_tokens)
        att = {"note": note, "prompt_sha256": sha256_text(prompt),
               "prompt": prompt, "raw_generation": raw, "usage": usage}
        if anchor is not None:
            candidate, balanced = extract_construct(anchor, raw, skill)
            att.update({"candidate": candidate, "brace_balanced": balanced,
                        "near_empty": len(candidate.strip()) < NEAR_EMPTY_CHARS})
        record["attempts"].append(att)
        return att

    if track in ("A", "B"):
        prompt = prompts.build_track_a(entry) if track == "A" else prompts.build_track_b(entry)
        seed = prompts.seed_for(track, task_id)
        att = attempt(prompt, seed, prompts.max_tokens_for(entry), "single-shot",
                      prompts.anchor_for(entry))
        if att.get("near_empty"):
            retry_prompt = prompt.replace(
                prompts.anchor_for(entry), forced_anchor(prompts.anchor_for(entry), skill))
            att = attempt(retry_prompt, seed + 1, prompts.max_tokens_for(entry),
                          "forced-continuation-retry", forced_anchor(prompts.anchor_for(entry), skill))
        candidate = att["candidate"]
    elif track == "C":
        if track_b_first is None:
            raise ValueError("Track C requires the Track B attempt-1 record")
        record["reuses"] = {"track": "B", "task_id": task_id,
                            "attempt1_prompt_sha256": track_b_first["attempts"][0]["prompt_sha256"]}
        record["attempts"].append(track_b_first["attempts"][0])
        candidate = track_b_first["attempts"][0]["candidate"]
        current_verdict = track_b_first["verdict"]
        repairs = 0
        while current_verdict.get("passed") is not True and repairs < MAX_REPAIRS:
            repairs += 1
            repair_prompt = prompts.build_track_c_repair(entry, repairs, _failing_checks(current_verdict))
            att = attempt(repair_prompt, prompts.seed_for("C", task_id) + repairs,
                          prompts.max_tokens_for(entry), f"repair-{repairs}",
                          prompts.anchor_for(entry))
            candidate = att["candidate"]
            with tempfile.TemporaryDirectory(prefix="s040-c-stage-") as tmp:
                cand = _stage_candidate(candidate, skill, Path(tmp))
                current_verdict = evaluate_candidate(repo, entry, cand, backend, image)
            record.setdefault("repair_verdicts", []).append(
                {"repair": repairs, "verdict": current_verdict,
                 "candidate_sha256": sha256_text(candidate)})
        record["repairs_used"] = repairs
        # the loop's last evaluation IS the final verdict (deterministic
        # evaluators; re-running the same candidate would only cost time)
        record["verdict"] = current_verdict
        record["candidate_final"] = candidate
        record["candidate_final_sha256"] = sha256_text(candidate)
        record["wall_seconds"] = round(time.time() - t_start, 1)
        return record
    elif track == "D":
        parts = prompts.build_track_d_prompts(entry)
        pieces = []
        for i, part in enumerate(parts):
            seed = prompts.seed_for(f"D{i}", task_id)
            att = attempt(part["prompt"], seed, part["max_tokens"],
                          f"sub-piece-{i + 1}:{part['name']}", part["anchor"])
            pieces.append(att)
        # deterministic assembly (disclosed): api/helper first, then the component
        assembled = "\n\n".join(p["candidate"] for p in pieces)
        if skill == "react-interaction":
            helper_name = parts[0]["name"]
            assembled = pieces[0]["candidate"] + "\n\n" + \
                pieces[1]["candidate"].replace(
                    f"import {{ {helper_name} }} from './helpers';", "")
        candidate = assembled
    else:
        raise ValueError(track)

    with tempfile.TemporaryDirectory(prefix="s040-stage-") as tmp:
        cand = _stage_candidate(candidate, skill, Path(tmp))
        verdict = evaluate_candidate(repo, entry, cand, backend, image)
    record["verdict"] = verdict
    record["candidate_final"] = candidate
    record["candidate_final_sha256"] = sha256_text(candidate)
    record["wall_seconds"] = round(time.time() - t_start, 1)
    return record


def evidence_path(track: str, entry: dict) -> Path:
    return ROOT / EVIDENCE_DIR / f"track-{track}" / f"{entry['domain']}__{entry['skill']}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--tracks", nargs="*", default=list(TRACKS))
    parser.add_argument("--backend", choices=["auto", "docker", "unshare"], default="auto")
    parser.add_argument("--image", help="exact image@sha256 digest (Docker backend)")
    parser.add_argument("--limit", type=int, default=0, help="stop after N new pairs (0 = all)")
    args = parser.parse_args()

    repo = args.repo.resolve()
    sample = load_sample(repo)
    print(json.dumps({"sample_tasks": len(sample),
                      "domains": sorted({e["domain"] for e in sample}),
                      "skills": sorted({e["skill"] for e in sample})}))

    model = None
    completed = 0
    manifest_rows = []
    for track in args.tracks:
        for entry in sample:
            if track == "D" and not prompts.decomposition_supported(entry):
                continue
            out_path = evidence_path(track, entry)
            if out_path.is_file():
                record = json.loads(out_path.read_text(encoding="utf-8"))
                manifest_rows.append(record)
                continue
            if args.limit and completed >= args.limit:
                continue
            track_b_first = None
            if track == "C":
                b_path = evidence_path("B", entry)
                if not b_path.is_file():
                    print(f"SKIP C {entry['id']}: track B evidence missing")
                    continue
                track_b_first = json.loads(b_path.read_text(encoding="utf-8"))
                if track_b_first.get("verdict", {}).get("passed") is True:
                    # already solved single-shot: record the carry-over honestly
                    record = dict(track_b_first)
                    record["track"] = "C"
                    record["reuses"] = {"track": "B", "task_id": entry["id"], "passed_at_attempt": 1}
                    record["repairs_used"] = 0
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                    manifest_rows.append(record)
                    print(f"C {entry['id']}: carried over (B passed attempt 1)")
                    continue
            if model is None:
                from archagent.model import FrozenModel
                model = FrozenModel(threads=2)
            t0 = time.time()
            try:
                record = run_pair(repo, model, track, entry, args.backend, args.image,
                                  track_b_first=track_b_first)
            except Exception as error:  # fail-closed record, never crash the batch
                record = {"track": track, "task_id": entry["id"], "skill": entry["skill"],
                          "domain": entry["domain"], "error": str(error)[:300],
                          "verdict": {"passed": False, "status": "DRIVER_ERROR"}}
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest_rows.append(record)
            completed += 1
            verdict = record.get("verdict", {})
            print(f"{track} {entry['id']}: {'PASS' if verdict.get('passed') else 'FAIL'} "
                  f"({verdict.get('status')}) [{time.time() - t0:.0f}s]")

    # manifest
    summary = {}
    for record in manifest_rows:
        key = (record["track"], record["skill"])
        passed = 1 if record.get("verdict", {}).get("passed") is True else 0
        total, ok = summary.get(key, (0, 0))
        summary[key] = (total + 1, ok + passed)
    manifest = {"pairs_total": len(manifest_rows),
                "pass_rates": {f"{t}/{s}": {"n": n, "passed": p}
                               for (t, s), (n, p) in sorted(summary.items())},
                "evidence_files": [str(evidence_path(t, e)) for t in args.tracks for e in sample
                                   if (t != "D" or prompts.decomposition_supported(e))
                                   and evidence_path(t, e).is_file()]}
    (ROOT / EVIDENCE_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest["pass_rates"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
