# Session 039 — Docker-only executable boundary (partial)

**Scope:** A trustworthy interface for testing generated *state-invariant*
functions. API routes, React and integrated full-stack evaluation are **not
implemented yet**; none of these model outputs has been executed here.

## Frozen contracts: explicit v2 amendment

The original 96-spec `suite/` remains byte-for-byte unchanged. Before any
Qwen generation, a cross-module contract review found that `schema-relationship`
did not require the persisted status field implied by UI/integration tasks.
This was not silently fixed in place. A new `suite-v2/` (54 train / 18 dev /
24 holdout) adds the persisted status requirement consistently to Prisma,
GET, POST and integration roles, including the initial workflow value.
The updated train/dev scenarios are in `scenarios-v2/`; original v1 plans
are retained for reproducibility.

Run the non-destructive drift checks:

```
python -m archagent.s039.curriculum --check
python -m archagent.s039.curriculum_v2 --check
python -m archagent.s039.scenarios --suite-version 2 --split train --check
python -m archagent.s039.scenarios --suite-version 2 --split dev --check
```

## Docker-only invariant evaluator

Code:

- `archagent/s039/docker_only.py`: restricted Docker invocation, fail-closed
  verdict parsing and explicit `BLOCKED_NO_DOCKER` status.
- `archagent/s039/invariant_eval.py`: freeze-check and trusted fixture
  staging for a specific train/dev invariant task.
- `archagent/s039/harness/runner.mjs`: trusted Node evaluator which imports
  the candidate TS file, runs all required named cases, and reports exactly
  one machine-readable verdict.

To use **in a separate approved Docker-capable environment**:

1. Independently vet and pin a local Node 24 evaluation image by immutable
   `image@sha256:<64 hex>` digest; build/install it under an approved image
   workflow. The evaluator refuses floating tags and does not pull images.
2. Put a raw Qwen-generated TypeScript module in precisely
   `experiments/z039-generalization-learning/candidates/radiostation__state-invariant/output.ts`.
   The candidate directory must contain that file only and no symlinks.
3. Run:

   ```bash
   python -m archagent.s039.invariant_eval \
     --split dev \
     --task-id radiostation:state-invariant \
     --candidate-dir experiments/z039-generalization-learning/candidates/radiostation__state-invariant \
     --image 'APPROVED_NODE_24_IMAGE@sha256:<actual digest>' \
     --out experiments/z039-generalization-learning/evaluations/radiostation-state.json
   ```

   The quoted image above is a **placeholder**. Do not run it unchanged.

4. Compare output hashes to the archived model completion before accepting
   model attribution. Use a trusted positive control and intentionally bad
   controls inside the same Docker environment before trusting scores.

The Docker invocation uses a non-root UID, network disabled, read-only
root and mounts, dropped Linux capabilities, no-new-privileges, limited
processes, CPU/memory/timeout bounds and an ephemeral tmpfs. An input
directory containing arbitrary host files cannot be mounted through the
high-level task evaluator. It refuses extra result markers that could
be stdout spoofing.

### Known limitations

- **No Docker binary is installed in this working environment.** The
  command builder and mocked verdict parser have unit tests, but the
  container has not been built or run. Passing unit tests do not prove
  runtime compatibility, security or candidate correctness.
- Candidate Node TypeScript import relies on a compatible pinned Node 24
  image with type stripping; it has not been integration tested here.
- A candidate can still deliberately introspect test inputs within its
  isolated process; this public/dev suite is not a security-hard hidden
  oracle. Holdout predictions must be frozen before opening hidden tests.
- The invariant harness only checks known finite cases; expanding
  randomized behavior tests is important, especially for numeric and
  interval invariants. The present stage handles state transitions only.
- TypeScript compiling to JavaScript or a syntax gate does not substitute
  for full integration; GET/POST, schema, React and full-stack executors
  remain next implementation work.
- No training or adapter exists. Root `AGENTS.md` continues to forbid
  gradients, optimizers and LoRA without a separately authorized change.

## Current evidence level

**Mocked harness-command tests pass. No generated candidate has been
executed and no behavior score is reported for Session 039.** The test
coverage is a control on our wrapper, not a measurement of Qwen skill.
