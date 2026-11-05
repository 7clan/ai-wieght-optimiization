# Session 031 — contract-first structural repair

Session030 tested frozen Qwen2.5-Coder-0.5B on a previously unseen ShelfStock
application. Teacher guidance improved the independent module pass count from
1/5 (CSS only) to 2/5 (CSS and Express API), but integration still failed.

Session031 targets the three remaining failures with explicit *textual*
interface contracts and public error feedback. The teacher supplies **no
executable target code**; Qwen must generate each replacement. Only strict
public-functional improvements are accepted. The original successful API and
CSS sources remain untouched. We preserve raw completions, hashes, source,
and public and repeated-holdout scores.

**Important:** ShelfStock's holdout was consumed in Session030. Session031 is
a diagnostic repair/regression exercise, *not* a fresh generalization test.
Passing it would not demonstrate permanent model learning. The frozen model
has no weight edits, gradients, backpropagation, or training steps.

Qwen-generated executable code is evaluated only within existing network-
disabled, read-only, unprivileged Docker. The source-view preview is inert.

Run using the dedicated GitHub Actions workflow. Do not substitute teacher
solutions for model completions or claim success before actual measured output.
