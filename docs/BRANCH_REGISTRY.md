# Git Branch Registry and Cleanup Policy

**Snapshot date:** 2026-11-08 (Asia/Beirut)  
**Repository:** [7clan/ai-wieght-optimiization](https://github.com/7clan/ai-wieght-optimiization)  
**Count:** 38 remote branches, including the new adaptive-generalization branch.  
**Action performed:** Created an inventory and a separate research branch. **Zero existing branches deleted, renamed, merged, rebased, force-pushed, or otherwise changed.**

This index avoids losing experimental results while allowing future branch hygiene. It is a **snapshot**, not a claim that a branch's author has stopped work. Commit hashes denote the latest head observed during inventory; Z.ai may update its heads later.

## Protected by project policy — do not modify

**GitHub's returned `protected=false` flags are not permission to change these references.** The following are protected by the user's instructions, even if repository settings have no server-enforced rule.

| Branch | Observed head | Status | Policy |
| --- | --- | --- | --- |
| [`main`](https://github.com/7clan/ai-wieght-optimiization/tree/main) | [`1868a8d2`](https://github.com/7clan/ai-wieght-optimiization/commit/1868a8d276beef3c10065e62856d85ae57bd4e69) | Mainline | No commits/merges without authorization. |
| [`exp/zai-architectural-circuits`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/zai-architectural-circuits) | [`e93e10b4`](https://github.com/7clan/ai-wieght-optimiization/commit/e93e10b48546c90d922f0f3a0407d4f54f4ddaaa) | Z.ai-owned / potentially active | Do not touch; obtain handoff before any consolidation. |
| [`exp/zai-autonomous-fullstack`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/zai-autonomous-fullstack) | [`45f81f0d`](https://github.com/7clan/ai-wieght-optimiization/commit/45f81f0d2b684e49a49544812bdb2443836c35c8) | Z.ai-owned / potentially active | Do not touch; obtain handoff before any consolidation. |
| [`exp/zai-visual-intelligence`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/zai-visual-intelligence) | [`a7334542`](https://github.com/7clan/ai-wieght-optimiization/commit/a7334542e6f038fd42756c9e463123a6d60db894) | Z.ai-owned / potentially active | Do not touch; obtain handoff before any consolidation. |
| [`exp/06-attn-steering-results`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/06-attn-steering-results) | [`c9ba7818`](https://github.com/7clan/ai-wieght-optimiization/commit/c9ba781883efb2d0a7c0e4d2e0f4cf0b6a5310c7) | [Open PR #1](https://github.com/7clan/ai-wieght-optimiization/pull/1) | Do not alter branch or PR without explicit approval. |

## Current project branch

| Branch | Initial documented head | Status | Policy |
| --- | --- | --- | --- |
| [`exp/qwen-adaptive-generalization`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/qwen-adaptive-generalization) | [`54f569cd`](https://github.com/7clan/ai-wieght-optimiization/commit/54f569cd0f77264923c01403c07691697daec7a9) | Adaptive generalization lab | Only branch used for new work; training remains gated. |

See [ADAPTIVE_GENERALIZATION_ROADMAP.md](./ADAPTIVE_GENERALIZATION_ROADMAP.md). The new branch is **based on main**, not Z.ai's unmerged work.

## Existing documentation work

| Branch | Observed head | Status | Policy |
| --- | --- | --- | --- |
| [`docs/taskflow-milestone-readme`](https://github.com/7clan/ai-wieght-optimiization/tree/docs/taskflow-milestone-readme) | [`bc5bff26`](https://github.com/7clan/ai-wieght-optimiization/commit/bc5bff26f0096123c6c3550768c97efc1aa6d8a4) | Independent README improvement | Preserve until deliberately reviewed/merged; no cleanup yet. |

## Historical experimental lines — preserve pending review

The numbered experiment branches below contain distinct research hypotheses/results and **are not automatically safe to delete just because they are older**. Their current activity state is not independently confirmed.

### Weight-space and mechanistic experiments

| Branch | Observed head | Status | Suggested handling |
| --- | --- | --- | --- |
| [`exp/01-transplant`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/01-transplant) | [`6e78af95`](https://github.com/7clan/ai-wieght-optimiization/commit/6e78af954532026f483c40973b67abae1238aa8d) | Research checkpoint | Retain; candidate for *later* archival review. |
| [`exp/02-svd-zeroing`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/02-svd-zeroing) | [`61a74ea0`](https://github.com/7clan/ai-wieght-optimiization/commit/61a74ea0237618aa9f3b9b96351fa58b91e453fa) | Research checkpoint | Retain; candidate for *later* archival review. |
| [`exp/03-norm-break`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/03-norm-break) | [`29f5af7c`](https://github.com/7clan/ai-wieght-optimiization/commit/29f5af7cb3bee007e992447fc523959c76304cdf) | Research checkpoint | Retain; candidate for *later* archival review. |
| [`exp/04-memit-single-layer`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/04-memit-single-layer) | [`45a7d7f1`](https://github.com/7clan/ai-wieght-optimiization/commit/45a7d7f1783ed3a297e268581ab5536ba1887eb9) | Research checkpoint | Retain; candidate for *later* archival review. |
| [`exp/05-svd-norm-fusion`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/05-svd-norm-fusion) | [`6e561e9d`](https://github.com/7clan/ai-wieght-optimiization/commit/6e561e9d35a7793d68fa320bdd39b007ca6cb5c4) | Research checkpoint | Retain; candidate for *later* archival review. |
| [`exp/06-attn-steering`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/06-attn-steering) | [`108436df`](https://github.com/7clan/ai-wieght-optimiization/commit/108436df60ab88520110ad63bb5a07e57e1768fa) | Research checkpoint | Retain; candidate for *later* archival review. |
| [`exp/07-highrank-logic-boost`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/07-highrank-logic-boost) | [`59dc7662`](https://github.com/7clan/ai-wieght-optimiization/commit/59dc76625b5f029cf5233e197638fc2c54fb1974) | Research checkpoint | Retain; candidate for *later* archival review. |
| [`exp/08-unbounded-norm`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/08-unbounded-norm) | [`c2f0c63a`](https://github.com/7clan/ai-wieght-optimiization/commit/c2f0c63aa091b0355c1c13bbfa611bd1c3e3a9f5) | Research checkpoint | Retain; candidate for *later* archival review. |
| [`exp/09-rank32-surgery`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/09-rank32-surgery) | [`73aabfdb`](https://github.com/7clan/ai-wieght-optimiization/commit/73aabfdb22b3793579e0fce1136f7a921a38a2cb) | Research checkpoint | Retain; candidate for *later* archival review. |
| [`exp/10-extreme-overdrive`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/10-extreme-overdrive) | [`d47e22ac`](https://github.com/7clan/ai-wieght-optimiization/commit/d47e22ac82a9de84f87adce5dbe60236e27f55de) | Research checkpoint | Retain; candidate for *later* archival review. |
| [`exp/11-mbpp-generalization`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/11-mbpp-generalization) | [`a8c356b4`](https://github.com/7clan/ai-wieght-optimiization/commit/a8c356b41df9b9ad38a871d4eca1d86a3e89282f) | Research checkpoint | Retain; candidate for *later* archival review. |
| [`exp/12-hybrid-ortho-hooks`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/12-hybrid-ortho-hooks) | [`cafe1848`](https://github.com/7clan/ai-wieght-optimiization/commit/cafe18487a12033d69c2ebd969622293973fb5f3) | Research checkpoint | Retain; candidate for *later* archival review. |
| [`exp/13-context-gated-subspaces`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/13-context-gated-subspaces) | [`c3cf12d1`](https://github.com/7clan/ai-wieght-optimiization/commit/c3cf12d127fefddcd52146f035888bbb3290a9a8) | Research checkpoint | Retain; candidate for *later* archival review. |

### Execution and contract-based generation

| Branch | Observed head | Status | Suggested handling |
| --- | --- | --- | --- |
| [`exp/14-execution-guided-search`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/14-execution-guided-search) | [`0febcd4b`](https://github.com/7clan/ai-wieght-optimiization/commit/0febcd4b5cee714b0e1d90827662153ec6954a37) | Research checkpoint | Retain; inspect provenance and successors before any consolidation. |
| [`exp/15-contract-first-fullstack`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/15-contract-first-fullstack) | [`7af45eee`](https://github.com/7clan/ai-wieght-optimiization/commit/7af45eee5b124f7802efed46cf86ff32915bf5dd) | Research checkpoint | Retain; inspect provenance and successors before any consolidation. |
| [`exp/16-extreme-python-search`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/16-extreme-python-search) | [`385f954d`](https://github.com/7clan/ai-wieght-optimiization/commit/385f954d5adc565f04a3b9f33272ffbe74179d0c) | Research checkpoint | Retain; inspect provenance and successors before any consolidation. |

### App generation, live mentoring and transfer

| Branch | Observed head | Status | Suggested handling |
| --- | --- | --- | --- |
| [`exp/17-generated-app-previews`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/17-generated-app-previews) | [`67f0d9de`](https://github.com/7clan/ai-wieght-optimiization/commit/67f0d9de42feba47edd62c3f6250c326c8a2767f) | Research checkpoint | Retain; check deliverables and tests before archival. |
| [`exp/18-real-project-manager`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/18-real-project-manager) | [`1b7a0596`](https://github.com/7clan/ai-wieght-optimiization/commit/1b7a05966f7c5839b1211746f45bb48707b98a39) | Research checkpoint | Retain; check deliverables and tests before archival. |
| [`exp/19-qwen-autonomous-app`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/19-qwen-autonomous-app) | [`81d416f9`](https://github.com/7clan/ai-wieght-optimiization/commit/81d416f92c869365a2efd4fb5d896b80f19b8c95) | Research checkpoint | Retain; check deliverables and tests before archival. |
| [`exp/20-execution-guided-app`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/20-execution-guided-app) | [`d07acbfc`](https://github.com/7clan/ai-wieght-optimiization/commit/d07acbfc9bd9d6ac799bf6e8b7bd8e7bf39d9b82) | Research checkpoint | Retain; check deliverables and tests before archival. |
| [`exp/21-live-mentor`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/21-live-mentor) | [`60d1a622`](https://github.com/7clan/ai-wieght-optimiization/commit/60d1a622b7325d745bd49383b1743d7425731e16) | Research checkpoint | Retain; check deliverables and tests before archival. |
| [`exp/22-live-mentor-delete`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/22-live-mentor-delete) | [`8a5e209c`](https://github.com/7clan/ai-wieght-optimiization/commit/8a5e209cdb0d9f1e42125352e3beeaa2aaea8e59) | Research checkpoint | Retain; check deliverables and tests before archival. |
| [`exp/23-live-focusboard`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/23-live-focusboard) | [`03d2364e`](https://github.com/7clan/ai-wieght-optimiization/commit/03d2364e968be068f2fba690cf7bfa45e7a0f869) | Research checkpoint | Retain; check deliverables and tests before archival. |
| [`exp/24-transfer-pattern-memory`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/24-transfer-pattern-memory) | [`878eddf3`](https://github.com/7clan/ai-wieght-optimiization/commit/878eddf3407acdf4d8209a2f956f44015049dc02) | Research checkpoint | Retain; check deliverables and tests before archival. |
| [`exp/25-autonomous-pocketledger`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/25-autonomous-pocketledger) | [`4fc2c137`](https://github.com/7clan/ai-wieght-optimiization/commit/4fc2c1377232af4af66f847302a44133da558581) | Research checkpoint | Retain; check deliverables and tests before archival. |
| [`exp/26-targeted-mentor`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/26-targeted-mentor) | [`b66407bf`](https://github.com/7clan/ai-wieght-optimiization/commit/b66407bf076c06913aed01a1e189edb6736658ef) | Research checkpoint | Retain; check deliverables and tests before archival. |
| [`exp/27-teacher-corrected-pocketledger`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/27-teacher-corrected-pocketledger) | [`18c0bb7c`](https://github.com/7clan/ai-wieght-optimiization/commit/18c0bb7cf4620075239c21191dfa6ae1de2bdd3e) | Research checkpoint | Retain; check deliverables and tests before archival. |
| [`exp/28-learner-transfer`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/28-learner-transfer) | [`5d194d20`](https://github.com/7clan/ai-wieght-optimiization/commit/5d194d200b08e5d704125043761690f9d81ea5a1) | Research checkpoint | Retain; check deliverables and tests before archival. |
| [`exp/29-js-structure`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/29-js-structure) | [`1e68bfbe`](https://github.com/7clan/ai-wieght-optimiization/commit/1e68bfbe6157baf32ba07915db29a6574b1fcf95) | Research checkpoint | Retain; check deliverables and tests before archival. |
| [`exp/29-selfrepair-deployment`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/29-selfrepair-deployment) | [`ac55558c`](https://github.com/7clan/ai-wieght-optimiization/commit/ac55558c951329774b9d58d16cb14ca1b89ea251) | Research checkpoint | Retain; check deliverables and tests before archival. |

### Later self-repair experiments

| Branch | Observed head | Status | Suggested handling |
| --- | --- | --- | --- |
| [`exp/32-fim-selfrepair`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/32-fim-selfrepair) | [`7a0aa171`](https://github.com/7clan/ai-wieght-optimiization/commit/7a0aa171f0a35766827c0804bd16d42c66d44a7c) | Research checkpoint | Retain; check whether another agent is continuing it. |

## What “organize” means safely

1. **Inventory now:** keep branch names, observed commit SHAs, groupings, open PR status and ownership in this document.
2. **Protect work in progress:** `main`, all `exp/zai-*` branches, any open PR head, and the current lab are no-touch unless the owner approves.
3. **Retain research history:** don't squash away failed or negative results; they matter for honest generalization comparisons.
4. **Use clear names from now on:** `exp/<owner-or-team>-<descriptive-topic>` for isolated work, `docs/<topic>` for documentation, and only approved integration into `main`.
5. **Propose cleanup separately:** once every old branch has a recorded final commit, report, reproducible artifacts and no active owner/PR dependency, propose exact archive/tag/merge/delete operations to the user for confirmation. Never silently delete or rewrite.
6. **Prefer a GitHub issue/PR for consolidation discussion** rather than re-pointing a branch that another agent may be using.

### Inventory checks

- Before touching any branch, fetch its current SHA again; if it changed, stop and reclassify.
- For branches that appear redundant, compare content and test reports rather than treating matching names as identical work.
- Use annotated tags only with user authorization; tags are not a substitute for preserving uncommitted or unpublished artifacts.
- The repository's `AGENTS.md` still prohibits gradients/training for new experiments. The adaptation track in this lab is planned only, not authorized implementation.

## Inventory totals

- Mainline: 1
- Z.ai-owned / guarded: 3
- Open PR head: 1
- Documentation branch: 1
- Numbered historical branches (excluding PR head): 31
- New adaptive generalization lab: 1
- **Total: 38**

## Review sources

- [GitHub branch list](https://github.com/7clan/ai-wieght-optimiization/branches)
- [GitHub open PRs](https://github.com/7clan/ai-wieght-optimiization/pulls)
- [Repository AGENTS.md](https://github.com/7clan/ai-wieght-optimiization/blob/main/AGENTS.md)
