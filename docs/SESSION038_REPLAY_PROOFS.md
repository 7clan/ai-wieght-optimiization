# Session 038: isolated replay evidence contract

This describes how to **report** independently executed candidate checks;
it is not a claim that any candidate has been executed or verified here.
See `archagent/finetune/proof_gate.py` for the conservative metadata reader.
The previous 22 accepted outputs are references awaiting independent replay.

## Producer expectations

1. On a separate Z.ai-owned branch, freeze each original task specification,
   oracle inputs and test runner **before** replay. Use a clean checkout of
   the archived generation, independently recompute the prompt and candidate
   SHA-256 digests, and record the unmodified candidate bytes.
2. Run generated Python/JavaScript only in the repository-approved
   restricted Docker environment: no network, read-only root filesystem,
   non-root account, no new privileges, explicit memory/CPU limits, bounded
   timeout, no host secrets or writable repository mounts. If tests need
   ephemeral writable files, isolate those inside a size-limited tmpfs.
3. Include a positive-control run and, where applicable, a negative control
   that demonstrates the behavioral oracle rejects a known incorrect output.
   Never use an edited candidate or teacher-supplied implementation to
   represent an independent Qwen success.
4. Save one machine-readable, non-secret test report and one candidate proof
   per content hash. Never add candidate source, patient information, tokens,
   credentials or complete prompts to the proof files.
5. Before publishing a proof, review it against the immutable original
   contract, not just the dynamic harness result. Changes to a test oracle
   made after seeing an output must be disclosed, with that sample excluded
   from independent accuracy claims.

## File names and schema

Place each proof at
`experiments/finetune-readiness-038/replay-proofs/<candidate_sha256>.json`.
All `path` values must be **relative to the repository root**, point to
committed files inside it, and have the matching SHA-256 hex digest.

The following is an **illustrative schema only** (hash placeholders are
not valid proofs):

```json
{
  "candidate_sha256": "<sha256 of raw Qwen candidate>",
  "prompt_sha256": "<sha256 of raw generation prompt>",
  "generation_path": "experiments/z037-generalization/.../gen/example.json",
  "provenance": "QWEN_GENERATED_UNMODIFIED",
  "teacher_written_bytes": 0,
  "candidate_edited_after_generation": false,
  "test_fixture_modified_after_generation": false,
  "sandbox": {
    "runtime": "docker",
    "network": "none",
    "read_only": true,
    "unprivileged": true,
    "no_new_privileges": true,
    "memory_mb": 512,
    "cpus": 1
  },
  "task_spec": {
    "path": "experiments/replay/specs/example.json",
    "sha256": "<sha256 of committed spec file>"
  },
  "test_report": {
    "path": "experiments/replay/results/example.json",
    "sha256": "<sha256 of committed report file>"
  }
}
```

The report object at `test_report.path` must have integer `exit_code: 0`
and `checks`, an array of objects with `name` and Boolean `passed`.
The current conservative contract recognizes these mandatory check names:

| Queue `kind` | Mandatory named checks |
| --- | --- |
| `prisma-model` | `schema_validate`, `database_behavior` |
| `invariant` | `typescript_compile`, `property_behavior` |
| `route-handler` | `typescript_compile`, `api_behavior` |
| `ui` | `typescript_compile`, `browser_behavior` |

Real behavioral tests must cover both valid and invalid inputs and the
cross-module effects relevant to the frozen specification. A passing name
alone does not constitute this evidence. Include scenario-level results,
execution command, pinned Docker image digest and bounded timestamps in
the report for human examination; the gate does not yet authenticate them.

Run locally without executing any generated code:

```bash
python -m archagent.finetune.proof_gate --repo . \
  --queue experiments/finetune-readiness-038/candidate-queue.jsonl \
  --proof-dir experiments/finetune-readiness-038/replay-proofs \
  --out experiments/finetune-readiness-038/proof-status.json
```

The statuses mean:

- `AWAITING_REPLAY`: no proof file was found.
- `QUARANTINED`: submitted proof did not pass metadata checks.
- `CONSISTENT_ATTESTATION_NEEDS_REVIEW`: proof content is internally
  consistent, but actual sandbox execution and correctness **remain
  unverified by this command**.

**No status grants training permission.** The evaluator never executes
generated code, grants `training_eligible`, or changes model weights.
Any future training step needs an explicit user-approved instruction change,
independently reproduced executions, provenance review and dataset licensing
review.
