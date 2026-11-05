# Session 029 — a working teacher-assisted milestone

Purpose: repair the actual Qwen2.5-Coder-0.5B PocketLedger output after the
Session028 analogous-teaching experiment stalled on JavaScript architecture.

## Deliberately separate authorship

| File | Actual author |
|---|---|
| backend/logic.py | Qwen2.5-Coder-0.5B, exact Session028 output |
| client/style.css | Qwen2.5-Coder-0.5B, exact Session027 output |
| server/store.js | Teacher rewrite after observing Qwen's missing-file/persistence failures |
| server/routes.js | Teacher rewrite after observing out-of-function routes |
| client/App.jsx | Teacher rewrite after observing a static, interaction-free UI |
| bridge/build/startup | Trusted harness (not Qwen) |
| public/overrides.css | Teacher responsive CSS override; original Qwen CSS retained |

The final working result, if verified, is **not** independent Qwen authorship.
There are no training steps or weight modifications.

## Evidence

- Both the archived Qwen-only source and corrected source run through the same
  five-module public and holdout harness in network-disabled, read-only,
  unprivileged Docker. All model code stays in the sandbox.
- Only if the corrected modules pass will the collector package the app.
- A second isolated Docker image compiles the real React client and exercises
  actual Express POST/GET/DELETE requests, persistent store reloads, invalid
  input and the actual Python bridge. These are automated integration tests,
  not an observed browser user session.
- Published previews are script-free source inspection pages. The runnable
  app's Node/React/Python package is available in
  `apps/pocketledger-qwen-mentored`, to be started privately in the user's
  Codespace and manually checked in a browser.

## Learning next

Each Qwen failure and teacher correction is recorded as a pair with a reusable
abstract rule. A subsequent **unseen-task** experiment can feed those rules
back to frozen Qwen as retrieval memory. This constitutes in-context adaptation,
not parameter learning. Never use a corrected target as evidence of Qwen-only
application-building success.
