# archagent/verify — Session 036 structural verification system

**TRUSTED-SCAFFOLD** (test tooling only; contains no application bytes).

Replaces the Session 035 text/substring gates that produced the documented
false acceptances (import-only "anchor" routes passing tsc; instruction and
spec echoes satisfying substring expects; unreachable or comment-only
validation logic).

## Components

| File | Role |
|---|---|
| `parse.mjs` | TypeScript-AST analysis: exports (function-like or not), reachable call/access chains, used string literals, JSX text, comments, unreachable regions, imports, echo fraction |
| `prisma_schema.mjs` | Structural Prisma parser (models, fields, types, nullability, attributes); comment-safe, truncation-safe |
| `gates.mjs` | Contract engine: `route`, `component`, `types`, `hook`, `page`, `prisma`, `interfaces` (cross-file) |
| `run_gates.mjs` | CLI (`--contract`, `--root`, `--stdin`) emitting one-line JSON verdicts for the Python harness |
| `classify.mjs` | Dynamic-test error classification: `app` / `harness` / `unknown` (NaN comparisons are always harness) |
| `adversarial.test.mjs` | 28-case adversarial suite proving the documented Session-035 false accepts are now rejected AND real archived StockPilot files still pass |

## Invariants (the point of the whole exercise)

1. **Required expressions are AST nodes.** Comments and string literals can
   never satisfy `calls`/`accesses` gates.
2. **Route gates require function-like exported handlers.** Import-only
   files, unexported consts, string consts and re-exports never pass.
3. **Unreachable code never satisfies a gate.** Chains are collected only
   from reachable positions; `if (false)` branches and statements after an
   unconditional `return`/`throw` are flagged.
4. **UI strings must be in used positions** (JSX text/attribute, call
   argument, referenced constant) — never comments or dead constants.
5. **Echo is measured, not guessed**: the fraction of comment+string
   8-grams duplicating the instruction text exceeds a limit ⇒ reject.
6. **Cross-file interfaces**: every `db.<model>` access must exist in the
   parsed schema; declared imports must be present; demo contamination
   (wrong model/fields) is caught mechanically.

## Usage

```bash
NODE_PATH=<sandbox node_modules> node archagent/verify/adversarial.test.mjs
node archagent/verify/run_gates.mjs --contract c.json --root /home/z/my-project
cat candidate.ts | node archagent/verify/run_gates.mjs --contract c.json --stdin
```

`typescript` resolves via the repo `node_modules` symlink to the preview
workspace's compiler (TS 5.9.3).

## Adversarial suite result (Session 036, Phase 1)

28/28 — including six real-file regression cases (the archived StockPilot
route/types/schema/states/page all still pass; no false rejects).
