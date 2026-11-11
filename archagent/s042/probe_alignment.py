"""SESSION 042 — GLM->Qwen weight-transfer feasibility probe.

Question: do the representation spaces of GLM-Edge-1.5B-Chat (the only
memory/disk-feasible open-weight GLM donor) and Qwen2.5-Coder-0.5B admit
a linear alignment suitable for closed-form weight transfer?

Both models are byte-level BPE with the GPT-2 unicode byte convention and
both tie word embeddings to the LM head, so the embedding matrices are the
one place a cross-space correspondence is measurable WITHOUT loading the
full donor (a 231MB tensor-range fetch vs a 3.05GB model).

Protocol (no gradients anywhere):
  1. anchor set  = vocab entries with byte-identical token strings
                   (printable ASCII, len <= 16) in BOTH tokenizers;
  2. deterministic 50/50 train/held-out split (sort by qwen id, even/odd);
  3. orthogonal Procrustes on train anchors:
        P = argmin_{P^T P = I} ||A P - B||_F,  A in R^{n x 2048}, B in R^{n x 896}
     solved closed-form as P = U V^T from the SVD of A^T B;
  4. held-out metrics: pairwise cosine of (A_test P, B_test), explained
     variance, and two null baselines (shuffled pairing; random orthogonal
     projection);
  5. semantic kNN probe: project GLM embeddings of shared code tokens into
     Qwen space and check where the SAME string's Qwen vector ranks by
     cosine among all 151,936 vocab rows (plus top-3 neighbours) — the
     qualitative "does aligned GLM 'def' land near Qwen 'def'?" test.

If even this shallowest-layer alignment is weak, deeper-layer transfer
(28 nonlinear GLM blocks -> 24 Qwen blocks, different GQA/head geometry,
different RoPE) has no foundation: that is the feasibility verdict.
"""

from __future__ import annotations

import json
import math
import os
import struct
import sys
from pathlib import Path

import requests
import torch

DONOR = "zai-org/glm-edge-1.5b-chat"
DONOR_EMBED_URL = f"https://huggingface.co/{DONOR}/resolve/main/model.safetensors"
# byte range of model.embed_tokens.weight in the donor safetensors
# (read from the file header on the fly; these are the recorded values)
EMBED_RANGE = (242_745_344, 485_490_688)

QWEN_SNAPSHOT = Path(os.environ.get(
    "ARCHAGENT_MODEL_DIR",
    "/home/z/.cache/huggingface/hub/models--Qwen--Qwen2.5-Coder-0.5B/snapshots/"
    "8123ea2e9354afb7ffcc6c8641d1b2f5ecf18301"))
GLM_TOKENIZER_JSON = Path(os.environ.get(
    "GLM_TOKENIZER_JSON",
    "/home/z/.cache/huggingface/hub/models--zai-org--glm-edge-1.5b-chat/"
    "snapshots"))
OUT_DIR = Path(__file__).resolve().parents[2] / "experiments/z042-glm-transfer"

CODE_PROBES = ["def", "class", "import", "return", "function", "const",
               "async", "await", "if", "for", "while", "true", "false",
               "None", "print", "export", "await", "request", "data",
               "error", "status", "schema", "model", "route", "state"]


def http_range_fetch(url: str, start: int, end: int, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size == end - start:
        print(f"[cache] {dest} already fetched")
        return
    with requests.get(url, headers={"Range": f"bytes={start}-{end - 1}"},
                      stream=True, allow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-range", "?").split("/")[-1])
        print(f"[fetch] {end - start} bytes of {url} (file total {total})")
        with open(dest, "wb") as fh:
            got = 0
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
                got += len(chunk)
    assert dest.stat().st_size == end - start, "range fetch incomplete"


def find_glm_tokenizer() -> Path:
    if GLM_TOKENIZER_JSON.is_file():
        return GLM_TOKENIZER_JSON
    for p in GLM_TOKENIZER_JSON.rglob("tokenizer.json"):
        return p
    raise FileNotFoundError("GLM tokenizer.json not found under "
                            f"{GLM_TOKENIZER_JSON} — set GLM_TOKENIZER_JSON")


def vocab_from_tokenizer_json(path: Path) -> dict[str, int]:
    d = json.loads(path.read_text(encoding="utf-8"))
    vocab = d["model"]["vocab"]
    assert len(vocab) > 1000, "suspiciously small vocab"
    return vocab


def load_glm_embed(cache: Path) -> torch.Tensor:
    raw = cache.read_bytes()
    t = torch.frombuffer(bytearray(raw), dtype=torch.bfloat16)
    return t.view(59264, 2048).float()


def load_qwen_embed() -> torch.Tensor:
    from safetensors import safe_open
    with safe_open(QWEN_SNAPSHOT / "model.safetensors", framework="pt") as f:
        t = f.get_tensor("model.embed_tokens.weight")  # bf16 [151936, 896]
    return t.float()


def printable_ascii(tok: str) -> bool:
    return all(32 <= ord(c) <= 126 for c in tok)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- donor embed tensor (range fetch, ~231MB) --------------------------
    embed_cache = OUT_DIR / "glm-edge-1.5b-embed.bf16"
    # sanity: re-read the header and re-verify the offsets before trusting
    head = requests.get(DONOR_EMBED_URL, headers={"Range": "bytes=0-65535"},
                        allow_redirects=True, timeout=60).content
    hlen = struct.unpack("<Q", head[:8])[0]
    header = json.loads(head[8:8 + hlen])
    meta = header["model.embed_tokens.weight"]
    assert tuple(meta["data_offsets"]) == EMBED_RANGE, meta
    assert meta["dtype"] == "BF16" and meta["shape"] == [59264, 2048], meta
    http_range_fetch(DONOR_EMBED_URL, *EMBED_RANGE, embed_cache)

    glm_tok_path = find_glm_tokenizer()
    vocab_g = vocab_from_tokenizer_json(glm_tok_path)
    vocab_q = vocab_from_tokenizer_json(QWEN_SNAPSHOT / "tokenizer.json")

    E_g = load_glm_embed(embed_cache)          # [59264, 2048] fp32
    E_q = load_qwen_embed()                    # [151936, 896] fp32

    # ---- anchor construction ----------------------------------------------
    shared = [t for t in vocab_g if t in vocab_q and printable_ascii(t)
              and 1 <= len(t) <= 16]
    # drop pure single 'Ġ'-class separator-only oddities? keep them: they are
    # real tokens in both vocabs. Deterministic order:
    shared = sorted(shared, key=lambda t: (vocab_q[t], vocab_g[t]))
    print(f"[anchors] shared printable-ASCII tokens: {len(shared)}")
    train = shared[0::2]
    test = shared[1::2]

    A_tr = E_g[[vocab_g[t] for t in train]]     # [n, 2048]
    B_tr = E_q[[vocab_q[t] for t in train]]     # [n, 896]
    A_te = E_g[[vocab_g[t] for t in test]]
    B_te = E_q[[vocab_q[t] for t in test]]

    # ---- closed-form orthogonal Procrustes ---------------------------------
    M = A_tr.T @ B_tr                           # [2048, 896]
    U, S, Vh = torch.linalg.svd(M, full_matrices=False)
    P = U @ Vh                                  # [2048, 896], orthonormal cols

    def cos_rows(X: torch.Tensor, Y: torch.Tensor) -> torch.Tensor:
        return torch.nn.functional.cosine_similarity(X, Y, dim=1)

    # held-out metrics
    proj_te = A_te @ P
    cos_te = cos_rows(proj_te, B_te)
    ev_te = 1 - ((proj_te - B_te) ** 2).sum() / (B_te ** 2).sum()
    ev_te = float(ev_te)

    # train-side fit (optimistic bound)
    proj_tr = A_tr @ P
    cos_tr = cos_rows(proj_tr, B_tr)
    ev_tr = float(1 - ((proj_tr - B_tr) ** 2).sum() / (B_tr ** 2).sum())

    # null 1: shuffle the held-out pairing
    perm = torch.randperm(B_te.shape[0], generator=torch.Generator().manual_seed(42))
    cos_null_shuffle = cos_rows(proj_te, B_te[perm])

    # null 2: random orthogonal projection (seeded)
    g = torch.Generator().manual_seed(42)
    Qr = torch.linalg.qr(torch.randn(2048, 896, generator=g)).Q
    cos_null_random = cos_rows(A_te @ Qr, B_te)

    # ---- semantic kNN probe -------------------------------------------------
    knn = []
    Eq_n = torch.nn.functional.normalize(E_q, dim=1)   # [151936, 896]
    id_to_tok_q = {i: t for t, i in vocab_q.items()}
    for tok in CODE_PROBES:
        if tok not in vocab_g or tok not in vocab_q:
            continue
        v = torch.nn.functional.normalize((E_g[vocab_g[tok]] @ P).unsqueeze(0), dim=1)
        sims = (Eq_n @ v.T).squeeze(1)                 # [151936]
        top = torch.topk(sims, 3)
        target_rank = int((sims > sims[vocab_q[tok]]).sum().item()) + 1
        knn.append({
            "token": tok,
            "same_string_rank": target_rank,
            "same_string_cos": float(sims[vocab_q[tok]].item()),
            "top3": [{"tok": id_to_tok_q[int(i)],
                      "cos": float(s.item())} for i, s in zip(top.indices, top.values)],
        })

    # ---- singular-value spectrum of the cross-correlation (alignment
    # strength: how concentrated is the shared subspace?) --------------------
    sv = S.float()
    spectrum = {
        "top10_singular_values": [round(float(x), 4) for x in sv[:10].tolist()],
        "effective_rank (>1% of s1)": int((sv > 0.01 * sv[0]).sum().item()),
        "total": int(sv.numel()),
    }

    report = {
        "donor": DONOR,
        "donor_tensor": "model.embed_tokens.weight [59264, 2048] bf16 (range-fetched)",
        "recipient": "Qwen/Qwen2.5-Coder-0.5B model.embed_tokens.weight [151936, 896] bf16",
        "n_shared_ascii_tokens": len(shared),
        "n_train": len(train), "n_test": len(test),
        "procrustes": {
            "train_cos_mean": round(float(cos_tr.mean()), 4),
            "train_explained_var": round(ev_tr, 4),
            "heldout_cos_mean": round(float(cos_te.mean()), 4),
            "heldout_cos_median": round(float(cos_te.median()), 4),
            "heldout_cos_p90": round(float(cos_te.quantile(0.9)), 4),
            "heldout_explained_var": round(ev_te, 4),
            "null_shuffled_cos_mean": round(float(cos_null_shuffle.mean()), 4),
            "null_random_orth_cos_mean": round(float(cos_null_random.mean()), 4),
        },
        "cross_correlation_spectrum": spectrum,
        "knn_code_tokens": knn,
        "notes": "Procrustes is the BEST-case linear alignment at the "
                 "shallowest layer (embeddings, tied to lm_head on both "
                 "sides). Held-out cosine near the null baselines means no "
                 "linear cross-space structure exists to build any "
                 "closed-form transfer on.",
    }
    out = OUT_DIR / "embedding-alignment-probe.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["procrustes"], indent=1))
    print("spectrum:", spectrum)
    for k in knn:
        print(f"  kNN {k['token']:>10s}: same-string rank {k['same_string_rank']:>6d} "
              f"(cos {k['same_string_cos']:.3f}) top3={[t['tok'] for t in k['top3']]}")
    print("[written]", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
