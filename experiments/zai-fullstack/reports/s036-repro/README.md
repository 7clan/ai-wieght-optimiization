# SESSION 036 — PHASE 0 REPRODUCTION RECORD

**Date:** 2026-11-08 (fresh sandbox, third environment)
**Operator:** Session 036 agent (`exp/zai-self-improving-fullstack`)
**Base:** clean checkout of Session 035 milestone `2782067a1acf4e9e547ad53558623a584a3e349d`

## Environment rebuilt from scratch (nothing inherited)

- Research repo cloned from `github.com/7clan/ai-wieght-optimiization` (PAT auth,
  credential not stored on-branch); milestone commit verified byte-identical.
- Model re-downloaded from `Qwen/Qwen2.5-Coder-0.5B` (988,097,824 bytes),
  **sha256 verified against the Session 035 pin**
  `aff8914ec707fcaf9e2d4dc97197cded50b1c63e1d3a7a82e56f54d83ea47f80` (match).
- Inference stack rebuilt: Python 3.12 venv, torch 2.15.0+cpu, transformers
  5.22.2.  `archagent.model.FrozenModel` loads the checkpoint, verifies
  494,032,768 params, and produces correct FIM completions (smoke:
  `a + b;` for `function add(a,b){ return _ }`).
- Preview workspace `/home/z/my-project` (Next.js 16 + Tailwind v4 + shadcn +
  Prisma/SQLite sandbox) restored to the StockPilot surface **exactly from the
  on-branch archive** `apps/stockpilot/` (src/, prisma schema, wipe script,
  tsconfig gate, globals.css additions, layout metadata per the final polish
  commit).  No application byte was edited during reproduction.

## Frozen-suite results (all from the archived, unmodified suites)

| Suite | Session 035 recorded | Session 036 reproduction |
|---|---|---|
| `apitest.mjs --phase pre` | 16/16 | **16/16** |
| dev-server restart + `--phase post-restart` | 2/2 | **2/2** |
| `uitest.mjs` (20 checks + page errors) | 20/20, 0 errors | **20/20, 0 page errors** |
| visual evaluator (10 metrics × 3 viewports) | 10/10 | **10/10** |

Raw console transcripts: `apitest-pre.txt`, `apitest-post.txt`, `uitest.txt`
(this directory); visual JSON: `visual-final.json`; screenshots:
`../../shots/s036-repro/` (desktop 1440×900, mobile 390×844, narrow 320×700,
empty state — all captured from the live running application).

## One reproduction defect (recorded, not a StockPilot defect)

First `GET /api/items` after install returned HTTP 500
(`db.inventoryItem` undefined): the dev server had loaded its Prisma client
**before** `db:push` regenerated it with the `InventoryItem` model.  A dev
server restart (already part of the frozen persistence protocol) resolved it;
the API then passed 16/16.  Root cause: process-lifetime module caching in the
running dev server, i.e. an environment-sequencing artifact of a fresh sandbox
install, not an application or suite defect.  The Session 035 install sequence
always pushed the schema before first route compile; reproduction from the
archive on an already-running server hit the ordering the original never saw.

## Conclusion

The archived StockPilot milestone **builds and tests independently of the
original preview environment**: 38/38 functional checks + 10/10 visual across
three viewports reproduce from a clean checkout in a rebuilt sandbox with a
sha256-verified frozen checkpoint.  The Phase 0 working baseline is preserved
(the archive `apps/stockpilot/` is untouched; reproduction artifacts live only
under `reports/s036-repro/` and `shots/s036-repro/`).  Harness modification
(Phase 1+) may now begin.
