# Session 040 — CI workflow & GHCR security review (Phase 1)

**Reviewer:** Z.ai (session 040, branch `exp/zai-040-autonomous-fullstack`)
**Reviewed object:** `.github/workflows/s039-docker-eval.yml` at commit `821cc89`
(post-review-fixed version), plus its registration PR
([#3](https://github.com/7clan/ai-wieght-optimiization/pull/3),
branch `pr/s040-register-s039-eval-workflow`, one file, byte-identical).
**Date:** 2026-11-10

## 1. The default-branch registration restriction (verified)

`workflow_dispatch` events only trigger workflows that exist on the
repository's **default branch** (documented GitHub behavior). Verified:
`git cat-file -e origin/main:.github/workflows/s039-docker-eval.yml` fails —
the workflow exists only on experimental branches, so it is invisible to the
Actions "Run workflow" control and to dispatch API calls until merged to
`main`. PR #3 registers exactly this one file and nothing else. **Merging PR #3
registers the workflow but dispatches nothing** — the file has no automatic
triggers (`on: workflow_dispatch` only). Merging remains blocked on explicit
maintainer approval per the Session-040 work order.

## 2. Immutable image digests — VERIFIED

| Property | Status | Evidence |
|---|---|---|
| Base image pinned by digest | ✅ | `FROM node:24@sha256:6b9d4ea…262e0` (linux/amd64 manifest digest, recorded in `experiments/z039-zai-execution/image-pins.json` via registry API on 2026-11-10) |
| Built image recorded by registry digest | ✅ | Push to GHCR first, then `docker image inspect --format '{{index .RepoDigests 0}}'` — a locally built, never-pushed image has **empty** `RepoDigests`; recording happens strictly after the push |
| Recorded reference format-gated | ✅ | `grep -Eq '^[a-z0-9][a-z0-9._/:-]*@sha256:[a-f0-9]{64}$'` — byte-identical to the evaluators' `docker_only.IMAGE_RE`; enforced by unit test `test_ci_workflow_gate_matches_evaluator_regex` (57-test suite) |
| No silent fallback | ✅ | The old `|| docker image inspect --format '{{.Id}}'` fallback (which produced a repository-less ID the evaluators reject) was removed in `821cc89`; a malformed reference now fails the job loudly |
| No floating tags at run time | ✅ | Evaluators invoke `docker run --pull never` with the digest reference; the candidates job `docker pull`s the exact digest before evaluation |
| Digest re-verification | ✅ | Stage 1 re-pulls the recorded reference (`docker pull "$REF"`) before running controls — same pull path stage 2 uses |
| Cross-dispatch immutability | ✅ | Registry digests are content-addressed and immutable; a stage-2 dispatch with a stage-1-recorded digest receives byte-identical image content |

## 3. Permissions — VERIFIED

- **Top level:** `contents: read` only.
- **`controls` job:** `contents: read` + `packages: write` (needed solely to
  push the vetted evaluation image so the separate stage-2 runner can pull it).
- **`candidates` job:** `contents: read` + `packages: read`.
- **Credentials:** no stored secrets of any kind; the ephemeral per-run
  `GITHUB_TOKEN` is used via `secrets.GITHUB_TOKEN` for `docker login`, and
  `docker logout ghcr.io` brackets every authenticated section in both jobs.
- **Checkouts:** `actions/checkout@v4` with an explicit `ref` (the dispatch
  input branch), so the evaluated code is pinned and auditable.

## 4. Cleanup — analysis and verdict

1. **Runner-local cleanup: unnecessary by construction.** GitHub-hosted
   runners are ephemeral single-use VMs; the local image, build cache and any
   credentials vanish with the runner. The workflow additionally logs out of
   GHCR explicitly (`docker logout`) rather than relying on VM teardown.
2. **GHCR package retention (the real accumulation vector):** every stage-1
   dispatch pushes one new package version of
   `ghcr.io/7clan/ai-wieght-optimiization/s039-route-eval` (estimated
   ~0.9–1.4 GB: node:24 base + global prisma 6.19.3 + engines). The package
   is created **private** by default and linked to this repository.
3. **Why automatic version deletion is deliberately NOT implemented:** the
   two-stage design requires a stage-2 dispatch (a different run, possibly
   days later) to `docker pull` the digest recorded by an earlier stage-1
   run. Deleting versions at stage-1 exit would invalidate every recorded
   digest and break the approval separation between "controls passed" and
   "candidates approved". Digest deletion is therefore treated as an
   **intentional revocation**, not housekeeping.
4. **Recommended owner-side policy (documented, not automated):** after a
   stage-2 run has consumed a digest and no further candidate runs are
   planned against it, the maintainer may delete superseded package versions
   in the package settings UI (or via `gh api` with an admin token). Old
   versions become unreferenced as soon as a newer stage-1 run records a new
   digest. For a private repository GHCR storage is not billed separately,
   so accumulation is an hygiene concern, not a cost concern.
5. **Verdict:** current cleanup behavior (logout bracketing, ephemeral
   runners, no automatic deletion) is correct for the two-stage approval
   design. No change made; retention guidance recorded here and in the
   workflow comments.

## 5. Threat model and residual risks

| Risk | Assessment |
|---|---|
| A malicious **checked-out branch** runs arbitrary Python inside the `controls`/`candidates` jobs with the job's `GITHUB_TOKEN` (packages:write for controls) | **Accepted with guidance.** The workflow evaluates whatever branch the dispatcher names; its evaluator code therefore executes in-job. Mitigations: manual dispatch only; the dispatcher is expected to name reviewed branches only (stated in PR #3 and the workflow header); token scopes are already minimal (no `contents:write`, no `issues`, no `actions`); the package namespace can only receive container images. A stronger future hardening (signing + environment protection rules) is optional owner-side configuration, not required for the vetted use. |
| `GITHUB_TOKEN` exfiltration via candidate behavior inside the restricted container | **Not present.** Candidate containers run with `--network none`; the token never enters the container environment (it is consumed by `docker login` before evaluation and the login is logged out; the Python evaluators pass a minimal env to `docker run`). |
| Image substitution between stage 1 and stage 2 | **Not possible via tags.** Stage 2 consumes an immutable digest pasted by the human dispatcher; `--pull never` prevents implicit fetches; the pull step validates the reference format. (Registry-level compromise is out of scope.) |
| Accidental automatic execution | **Not possible.** The only trigger is `workflow_dispatch`; there are no `push`/`pull_request`/`schedule` events. |
| Runaway jobs | Bounded: `timeout-minutes: 30` (controls) / `45` (candidates); containers additionally carry `--cpus 2 --memory 2560m --pids-limit 96 --ulimit cpu=90` and per-probe 10 s timeouts inside the evaluators. |
| Evidence tampering | Fail-closed artifact uploads (`if: always()`, `if-no-files-found: error`). |

## 6. Registration PR contents (PR #3)

- Adds exactly one file: `.github/workflows/s039-docker-eval.yml`, 171 lines,
  byte-identical to the reviewed copy at `821cc89` (verified by `git diff` —
  the branch diff vs `main` shows only this file).
- **Sync requirement:** the registered copy on `main` and the reviewed copy on
  the experiment branch must not drift. The unit test
  `test_ci_workflow_gate_matches_evaluator_regex` pins the digest-gate regex
  on whichever branch it runs; any change to either copy must be re-reviewed
  through a PR like this one.
- Merging PR #3 = registration only. The first actual dispatch still requires
  the separate stage-1 approval already requested in
  `docs/ZAI_SESSION039_DOCKER_EXECUTION.md`.

## 7. Verdict

**SAFE TO REGISTER and, upon the already-requested stage-1 approval, SAFE TO
DISPATCH** under the documented guidance (reviewed branches only; stage 2 only
after `all_oracles_validated: true` plus explicit candidate-execution
approval). No blocking findings. One accepted residual risk (branch trust at
dispatch time) is inherent to evaluating branch-resident code in CI and is
mitigated by the manual-only trigger and minimal scopes.
