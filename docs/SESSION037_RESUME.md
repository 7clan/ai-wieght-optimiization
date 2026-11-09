# SESSION 037 — RESUME / CONTINUITY DOCUMENT

**Branch:** `exp/zai-generalization-engine-037` (forked from Session-036 milestone
`384e024` on `exp/zai-self-improving-fullstack`)
**Machine-readable state:** `SESSION037_STATE.json` (updated at every phase)
**Model:** local `Qwen/Qwen2.5-Coder-0.5B`, sha256
`aff8914ec707fcaf9e2d4dc97197cded50b1c63e1d3a7a82e56f54d83ea47f80`
(identical to the Session-035/036 pin; frozen — **no weight changes ever**).

## Environment recovery (this sandbox was reset before Session 037)

Everything needed to resume after a fresh reset:

```bash
# 1. python stack
source /home/z/.venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install "transformers>=4.45,<5" "accelerate>=0.34,<2" "safetensors>=0.4"

# 2. model (hash-pinned; HF API may 429 — use resolve endpoints directly)
mkdir -p /home/z/models/Qwen2.5-Coder-0.5B && cd /home/z/models/Qwen2.5-Coder-0.5B
for f in config.json generation_config.json tokenizer_config.json vocab.json \
         merges.txt tokenizer.json model.safetensors; do
  curl -sL --retry 3 -o $f \
    "https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B/resolve/main/$f"
done
sha256sum model.safetensors   # must equal aff8914e...a47f80

# 3. repo (branch carries all Session-037 work)
cd /home/z/my-project/research && rm -rf aiwo   # if needed
git clone -b exp/zai-generalization-engine-037 https://github.com/7clan/ai-wieght-optimiization.git aiwo
cd aiwo && git log --oneline -1   # compare with SESSION037_STATE.json.repo_sha

# 4. evaluator baseline (needs the StockPilot surface in the workspace —
#    apps/stockpilot in this repo is the source of truth)
cd /home/z/my-project/research/aiwo
NODE_PATH=/home/z/my-project/node_modules node archagent/verify/adversarial.test.mjs
# expected: 30 passed, 0 failed
```

Git push credentials live only in `.git/config` of the local clone
(never committed, never printed).

## Phase map

| Phase | What | Status |
|---|---|---|
| 0 | Recovery, baseline reproduction, manifest | **complete** (adversarial 30/30) |
| 1 | Root-cause analysis of Session-036 failures | pending |
| 2 | TaskIR structured programming interface | pending |
| 3 | Budget-aware policy replacing the bandit | pending |
| 4 | Reasoning-principle engine | **complete** — 0 principles promoted (honest negative: model-reflected + teacher-seeded all failed transfer evidence) |
| 5 | Reflective prompt evolution | **complete** — promptevol.py; deterministic laws stayed ahead |
| 6 | Counterexample-driven repair | **complete** — in-loop probes + minimal counterexamples |
| 7 | Curricula | **complete** — A: 3/5 vs 4/5 dev, 1/1 transfer both; B: 1/5 vs 3/5 dev, 0/1 transfer both |
| 8 | Documentation retrieval workflow | pending |
| 9 | Frozen evaluation suite | **complete** — 15 pieces, sha 1a57852b... |
| 10 | Four-track comparison A/B/C/D | **in progress** — runner built; Track A interrupted by sandbox reset; re-run pending env restore |
| 11 | Full-stack independence challenge | pending |
| 12 | Optional weight-space investigation | skipped by default |

## Key Session-036 results being explained (Phase 1 input)

- Track B (fixed ladder): 7/12 contracts; Track C (adaptive bandit): 4/12
  at equal token budgets — adaptive selection LOST.
- `exact_shape` dominated: 2/12 in C while every other strategy ≤ 1 win.
- Zero-teacher failures: schema relations (16/16 both tracks), overlap
  logic (8/8), one-literal gaps, types file.
- doc_lookup 0/8.

## Workspace notes

- `/home/z/my-project` is the shared Next.js workspace (dev server,
  port 3000). The Session-036 delivered RoomReserve state is archived at
  `experiments/z037-generalization/workspace-snapshots/roomreserve-delivered-*.tar.gz`.
- For the Phase-0 baseline the StockPilot surface was restored into the
  workspace (page.tsx, schema.prisma, components, api/items) from
  `apps/stockpilot/` — this is what the adversarial suite's G cases read.
- RAM discipline: the dev server is stopped during generation phases
  (`archagent/fullstack/devserver.py`).
