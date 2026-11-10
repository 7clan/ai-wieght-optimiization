# Z.ai Session 039B — Docker-isolated execution: static preparation complete, live phase honestly BLOCKED

**Branch:** `exp/zai-039-docker-execution` (from `exp/qwen-generalization-learning-039` @ `022836449959cd11c3df14d5d587155b41e5bd32`)
**Assignment:** GitHub issue #2 (`Session 039B — Z.ai: Docker-isolated Qwen full-stack behavioral execution`)
**Model:** frozen base `Qwen/Qwen2.5-Coder-0.5B` (weights untouched; safetensors SHA-256 pin `aff8914e…a47f80` re-confirmed as the recorded reference; the local model cache was lost to an environment reset and must be re-downloaded and re-verified before any future generation)
**Status:** Phase 0 verification complete; Phase 1 implemented to the maximum extent possible without Docker and validated on trusted controls (host tier); **live candidate execution and Qwen generation BLOCKED — no Docker-capable environment exists in this sandbox and the Session-039 boundary forbids host execution or `unshare` substitution.** Zero model-generated code executed. Zero Qwen candidates generated. All 24 v2 holdout contracts sealed.

## Headline

The assignment's central requirement — run model-generated code only inside
restricted Docker — cannot be satisfied in this environment. Per the handoff's
stop condition, this session completed the static preparation, validated the
new GET/POST evaluator against trusted positive and negative controls at the
disclosed host tier, published a ready-to-run Docker execution package
(pinned image recipe, restricted-container settings, ten-control matrix,
manual-dispatch-only CI workflow), and stops here. **No workaround was
attempted and no evidence tier was inflated.**

## Phase 0 — verification of the starting point (all reproduced)

| Check | Result |
| --- | --- |
| Unit tests (`tests.test_finetune_audit tests.test_candidate_queue tests.test_proof_gate tests.test_s039_preparation`) | **35/35 OK** |
| `archagent.s039.curriculum --check` (v1) | 54/18/24 splits, training false, no drift |
| `archagent.s039.curriculum_v2 --check` | 54/18/24 splits, training false, no drift |
| `archagent.s039.scenarios --suite-version 2 --split train --check` | checked; candidate code executed 0 |
| `archagent.s039.scenarios --suite-version 2 --split dev --check` | checked; candidate code executed 0 |
| `archagent.finetune.reconcile_038a` | metadata consistent; 22 replay claims; 12 normalized structures; 7 task families; training-eligible 0; errors 0 |
| Holdout | never opened; SHA reference `9a09d55b…c93e41` intact |

Machine-readable evidence: `experiments/z039-zai-execution/phase0-verification.json`.

## The Docker blocker (why the live phase stopped)

The environment survey is archived in
`experiments/z039-zai-execution/phase0-verification.json`. Summary:

- No `docker`, `podman`, `nerdctl`, `dockerd`, `containerd`, `runc` or `crun` binary; no `/var/run/docker.sock`.
- This sandbox is **itself an unprivileged Docker container** (`/.dockerenv` present).
- Rootless-Docker prerequisites are absent: no setuid `newuidmap`/`newgidmap`, no `slirp4netns`, no `fuse-overlayfs`; `sudo` exists but requires a password; `/sys/fs/cgroup` is read-only.
- `unshare -Urn` works but the Session-039 boundary **explicitly forbids substituting it** this time; it was not used for any candidate execution.

Consequences, exactly as the handoff prescribes: no trusted Docker control
run, no candidate execution, and therefore **no Qwen generation either** —
the work order permits generating candidates only after the verifier passes
positive and negative controls *in the Docker environment*, and that gate
has not been reached.

## Phase 1 (static part) — a real GET/POST Prisma+SQLite evaluator, implemented and control-validated

### What was built

1. **`archagent/s039/route_fixtures.py`** — trusted fixtures derived
   deterministically from the frozen v2 contracts: Prisma schema
   (optional→`SetNull` / required→`Restrict`, `status String @default("<initial>")`,
   cuid ids), PrismaClient provider, seed and reseed scripts, and oracle-case
   staging. Route path and list envelope are extracted from the authored
   contract requirements and were verified to resolve unambiguously for
   **all 24 train+dev GET/POST contracts**. Fixture rows are unit-tested to be
   byte-identical to the frozen scenario plans (drift guard).
2. **`archagent/s039/harness/route_runner.mjs`** — the trusted in-container
   orchestrator: stages the schema, runs `prisma db push` + `prisma generate`
   + seed **offline** (engines come from the pinned image), redirects the
   candidate's conventional `@/lib/db`-style imports to the trusted provider
   via a module-resolve hook (candidate bytes are never edited), invokes the
   exported Next.js-style `GET`/`POST` handler functions with standard
   `Request` objects, checks statuses, list envelopes, ordering, totals and
   per-case persistence deltas (each POST case starts from a freshly reseeded
   fixture so the frozen deltas stay exact), bounds every probe with a 10 s
   timeout, and emits exactly one fail-closed verdict line.
3. **`archagent/s039/docker_only.py`** — new `command_route`/`run_route` with
   the same hardening as the invariant path (digest pin mandatory,
   `--pull never`, network none, read-only root, non-root UID 10001,
   cap-drop ALL, no-new-privileges, pids/cpu/memory caps, mount-delimiter
   and directory-containment checks, single-verdict parsing) plus one
   **disclosed difference**: the `/work` tmpfs allows exec (nosuid kept)
   solely because the trusted Prisma query-engine library must be loadable
   from a writable location; the invariant path keeps its stricter noexec
   tmpfs.
4. **`archagent/s039/route_eval.py`** — the evaluator CLI mirroring
   `invariant_eval`: train/dev only (holdout sealed), candidate must live in
   its dedicated `candidates/<task>/output.ts` directory with exactly one
   non-symlink file, harness staged per run, `model_weight_change: false`
   always recorded.
5. **`archagent/s039/control_run.py` + ten trusted teacher controls** in
   `experiments/z039-zai-execution/controls/` — three spec-faithful positive
   controls (invariant, GET, POST) and seven known-bad controls: the
   demo-vocabulary copier, the fixture-copying GET, the
   write-before-validating POST, invalid TypeScript, missing export, a
   **partial** implementation (correct filtering, wrong ordering) and an
   asynchronous hang. All are labeled
   `TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE` and are never used as prompts or
   training data.
6. **Vetted image recipe** — `docker/s039-route-eval.Dockerfile` pins the
   `node:24` linux/amd64 manifest digest (`sha256:6b9d4ea…262e0`,
   NODE_VERSION 24.22.2, recorded 2026-11-10 via the registry API without
   pulling) and installs `prisma@6.19.3` + `@prisma/client@6.19.3` globally
   so engines are downloaded at **build** time and evaluation containers
   never need network. Digests and caveats: `experiments/z039-zai-execution/image-pins.json`.
7. **Manual-dispatch-only CI workflow** — `.github/workflows/s039-docker-eval.yml`
   with a two-stage design: stage 1 builds the pinned image and runs the ten
   controls (no model code); stage 2 (separate dispatch, requires the
   recorded digest) runs staged candidates via
   `experiments/z039-zai-execution/run_ci_candidates.py`. It never runs on
   push. **It has not been dispatched; the assignment asks for approval
   before any CI job.**
8. **Unit tests** — `tests/test_s039_route_eval.py` (18 tests, all Docker
   interactions mocked): command construction and digest refusal, resource
   limits, nested/missing-runner rejection, BLOCKED_NO_DOCKER, fail-closed
   verdict parsing (duplicate markers, invalid JSON, `pass:false`), fixture
   staging, scenario-plan equality, v2 schema semantics (SetNull vs
   Restrict, status default), holdout seal, candidate hygiene, control
   labeling and staging containment. Full suite: **53/53** (35 existing
   preparation tests unchanged and still passing).

### Host smoke test — trusted controls only, honestly labeled

Because Docker is absent, the ten controls were additionally run through the
real harness code with the host Node 24.22.2 binary in a disclosed
**trusted-code-only host smoke mode** (`--host-smoke`): the "candidate" path
is always a trusted control file, never model output. This tier does not
replace the Docker control run and confers no Docker-tier evidence; it
exists to catch harness logic defects that mocked tests cannot reach.

Result (`experiments/z039-zai-execution/host-smoke-controls.json`):
**10/10 oracles validated.**

- All three positive controls pass every frozen case (GET: 8/8 checks;
  POST: 12/12; invariant: 8/8).
- The demo-vocabulary invariant copier fails exactly the domain-state cases.
- The fixture-copying GET fails every filter case; the
  write-before-validating POST fails every persist-delta case.
- The partial control (correct filtering, insertion order) fails **exactly**
  the order-sensitive `list-all` case and passes the other seven — the
  oracle demonstrably does not pass "mostly right" implementations.
- Invalid TypeScript and missing export fail closed without crashing the
  harness; the asynchronous hang is bounded by the per-probe timeout.

The smoke test itself found and fixed two real harness defects before any
publication, both preserved in the commit history: the invariant runner had
hardcoded container paths (now environment-parameterized with identical
container defaults), and both runners now bind the real stdout writer at
startup so candidate code cannot suppress or spoof the verdict line
(candidate-added marker lines still fail closed upstream as
`NO_UNAMBIGUOUS_VERDICT`).

One contract-relevant empirical finding: **Prisma SQLite does not support
`mode: "insensitive"`**; the trusted positive control implements the
required case-insensitive search with `LOWER()`-based filtering, and future
model prompts must state this convention (or an equivalent) explicitly.

### What remains Docker-gated (not done, not claimed)

- The ten controls have **not** run inside the actual restricted container;
  image-level properties (global Prisma install under UID 10001, read-only
  root, network namespace, tmpfs sizes, engine loading from `/work`) remain
  unverified until stage-1 CI or an equivalent approved environment runs.
- No Qwen candidate has been generated or executed; per-family model-only
  vs controller metrics, token/CPU/RAM accounting and any interactive
  preview do not exist yet.
- React-interaction and integrated form→API→DB→UI evaluation paths are
  **not implemented** (the assignment's step 4 lists them; only the
  GET/POST and invariant paths exist). They remain the next implementation
  work once an execution environment is available.
- All 24 v2 holdout contracts remain sealed; no prediction or budget has
  been frozen against them.

## Phase 2 — not started (by design)

The work order sequences candidate generation *after* the verifier passes
controls in the Docker environment. That gate is unmet, so no balanced
2 train + 2 dev sample was generated, no prompts were spent, and no
generation budget was consumed. The model cache would also have to be
re-downloaded and its SHA-256 re-verified first.

## Phase 3 — reporting of what actually exists

- Qwen-generated candidates run: **0**. Behavior passes: **0** (no
  denominator exists). Model-written vs teacher-written byte accounting:
  0 model bytes; all harness/control bytes are teacher-authored and
  labeled.
- Model weights: **unchanged**. No gradients, no LoRA, no fine-tuning, no
  checkpoint written. `main` and every other branch untouched; no force
  pushes.
- Honest comparison to Session 038A: none possible — no new behavioral
  measurements were taken. The 038A gap analysis (routes 1/12, vocabulary
  copying, FK-optionality near-misses) remains the standing baseline.
- Known limitations: (a) the route evaluator invokes exported handler
  functions with standard `Request` objects rather than a full Next.js
  server — statuses and bodies are the handler's own, but middleware,
  routing tables and framework-level behavior are out of scope; (b) the
  frozen GET oracle cases do not assert the `include` relation shape
  (contract requirement not covered by a frozen case — flagged, not
  silently added); (c) the `/work` exec tmpfs deviation is disclosed
  above; (d) the include-`transmitter` requirement, React and integration
  families are unimplemented.

## Requested decisions (blocking)

1. **Approve dispatching the stage-1 control job** in
   `.github/workflows/s039-docker-eval.yml` (manual `workflow_dispatch`,
   `run_candidates=false`). The repository is public so standard hosted
   runners should not consume metered minutes, but the assignment asks for
   explicit approval before any CI job, so nothing has been dispatched.
   Post-review note: stage 1 now also **pushes the vetted image to GHCR** as
   a private, repository-linked package (see "CI workflow review fixes"
   below) — approving stage 1 covers that one-time package creation in the
   account's GHCR namespace. Alternatively, provide a Docker-capable
   environment and run:
   `python -m archagent.s039.control_run --repo . --image '<built-image@sha256:…>' --out experiments/z039-zai-execution/docker-controls.json`.
2. After stage 1 reports `all_oracles_validated: true`, **approve candidate
   generation + stage-2 execution** (or provide the environment for both).

## CI workflow review fixes (infrastructure only; post-report)

A pre-dispatch review of `.github/workflows/s039-docker-eval.yml` found two
infrastructure defects in the **workflow plumbing**. Nothing about the
evaluators, the trusted controls, or Qwen itself was wrong. Both defects
are fixed on this branch; the workflow still has never been dispatched.

1. **Image identification.** The build step recorded the image reference
   via `docker image inspect --format '{{index .RepoDigests 0}}'` with a
   silent fallback to `'{{.Id}}'`. A locally built image that has never
   been pushed has an *empty* `RepoDigests` list, so that fallback always
   fired and recorded the local image ID — a bare `sha256:<hex>` with **no
   repository name**, which the evaluators (`archagent/s039/docker_only.py`,
   `IMAGE_RE`) correctly refuse. The stage-1 control run would have crashed
   on its first control. The same wrong `{{.Id}}` guidance also lived in
   the Dockerfile header, the `image-pins.json` prose and this report's
   reproduction block — all corrected. The fixed workflow **pushes** the
   image to GHCR and records `RepoDigests[0]` *after the push* (a true
   registry manifest digest,
   `ghcr.io/<owner>/<repo>/s039-route-eval@sha256:<64-hex>`), validates it
   against the evaluator's exact regex and **fails loudly** on mismatch;
   the silent `.Id` fallback is gone.
2. **Image availability.** The candidates job runs on a *different*
   GitHub-hosted runner: an image built by the controls job is not present
   there, and the evaluators deliberately run with `--pull never`, so the
   stage-2 job could never have found the reviewed image — including a
   digest pasted from an earlier stage-1 dispatch, which existed on no
   runner and in no registry. The fixed workflow closes both gaps: the
   controls job pushes the pinned image to GHCR (job permission
   `packages: write`), and the candidates job validates the pasted
   reference, logs into GHCR with the ephemeral per-run `GITHUB_TOKEN`
   (permission `packages: read`) and `docker pull`s the exact digest before
   any evaluation starts. Digest references are immutable and
   content-addressed, so the reviewed image is byte-identical across
   dispatches.

Notes:

- The GHCR package is created **private** by default and linked to this
  repository; it only ever contains the vetted node+prisma evaluation
  image. No stored credentials are used — `GITHUB_TOKEN` is ephemeral and
  scoped per run (`docker login`/`logout` bracket every use).
- Regression protection: `tests/test_s039_preparation.py` now extracts both
  `grep -Eq` digest gates from the workflow file and asserts they are
  byte-identical to `docker_only.IMAGE_RE.pattern`; it also asserts that
  `docker_only.command` accepts the exact GHCR reference the workflow
  records and refuses the bare local image ID, floating tags and uppercase
  names (4 new tests; evaluator code unchanged — it was correct).
- Environment repair while re-verifying: the adversarial suite
  (`archagent/verify/adversarial.test.mjs`) reads the archived StockPilot
  surface from `/home/z/my-project`; that sandbox `prisma/schema.prisma`
  had been overwritten by earlier 038A Phase-2 bakery staging. It was
  restored byte-identically from `apps/stockpilot/prisma/schema.prisma`
  (the five other surface files already matched). Suite: **30/30** again.
- Unchanged: manual-dispatch-only trigger, the two-stage approval gate
  (`run_candidates=true` **plus** the reviewed digest from a prior stage-1
  run), every container hardening flag, zero model code executed, zero
  candidates generated, holdout sealed, no training.

## Reproduction

```bash
git checkout exp/zai-039-docker-execution
python -m unittest tests.test_finetune_audit tests.test_candidate_queue \
  tests.test_proof_gate tests.test_s039_preparation tests.test_s039_route_eval -v   # 57/57 (4 new CI-contract tests)
python -m archagent.s039.control_run --repo . --host-smoke \
  --out /tmp/host-smoke-controls.json   # 10/10, trusted controls only
# Docker tier (requires an approved Docker-capable environment):
docker build -f docker/s039-route-eval.Dockerfile -t s039-route-eval:local .
# The evaluators require name@sha256:<manifest-digest> and never pull, so push
# to a registry you control and record the manifest digest AFTER the push
# (a bare `{{.Id}}` is the local config ID with no repository name and is
# rejected by IMAGE_RE):
docker push <your-registry>/s039-route-eval:local
python -m archagent.s039.control_run --repo . \
  --image "$(docker image inspect --format '{{index .RepoDigests 0}}' s039-route-eval:local)" \
  --out experiments/z039-zai-execution/docker-controls.json
python experiments/z039-zai-execution/run_ci_candidates.py --repo . \
  --image '<same digest reference>' --out experiments/z039-zai-execution/docker-candidates.json
```

## Artifacts

- `experiments/z039-zai-execution/phase0-verification.json` — Phase 0 evidence + Docker blocker survey
- `experiments/z039-zai-execution/image-pins.json` — registry digest record and pinning rules
- `experiments/z039-zai-execution/host-smoke-controls.json` — 10/10 control evidence (host tier, trusted-only)
- `experiments/z039-zai-execution/controls/` — ten labeled trusted controls
- `experiments/z039-zai-execution/run_ci_candidates.py` — CI candidate runner
- `docker/s039-route-eval.Dockerfile` — vetted image recipe
- `.github/workflows/s039-docker-eval.yml` — manual-dispatch-only two-stage workflow
- `archagent/s039/{route_fixtures,route_eval,control_run}.py`, `archagent/s039/harness/route_runner.mjs`, `tests/test_s039_route_eval.py`

**No training occurred, no model weights changed, no app is claimed to
work, and no holdout was opened. The live execution phase is blocked on an
environment decision, not on code.**
