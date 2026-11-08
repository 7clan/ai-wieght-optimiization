"""Session 034 visual development curriculum.

Graded CSS exercises (Stages 1-3) for the frozen Qwen2.5-Coder-0.5B,
following the staged anchored-generation discipline proven in Session
033: every piece prompt contains ONLY (a) a programming-concept
explanation, (b) a worked example from a DIFFERENT domain (never the
target classes), (c) measurable requirements, and (d) the anchor (the
selector line the model must continue from).  No teacher target code.

Acceptance is automatic: static structural gates here + the harness
DOM/computed-style criteria in archagent/visual/check_component.mjs.

Stage 1 — CSS fundamentals (tokens, reset, typography, spacing, cards,
           buttons, inputs, interactive states)
Stage 2 — reusable components (badges, progress, header, nav, task row,
           empty state, modal, toast, skeleton)
Stage 3 — page composition (app shell + responsive collapse + assembly)
Stage 4 — React integration (ui_builder_v2, separate module)
Stage 5 — full-app polish (visual evaluator + browser feedback loop)
"""
from __future__ import annotations

# Design-token contract (interface names are the contract; VALUES are the
# model's own choice and are verified by measurable gates).
TOKEN_VARS = [
    "--c-bg", "--c-surface", "--c-border", "--c-text", "--c-muted",
    "--c-primary", "--c-on-primary", "--c-primary-soft",
    "--c-danger", "--c-danger-soft",
    "--c-high", "--c-medium", "--c-low",
    "--c-done", "--c-todo", "--c-doing", "--c-success", "--c-success-soft",
    "--sp-1", "--sp-2", "--sp-3", "--sp-4", "--sp-5", "--sp-6",
    "--r-1", "--r-2", "--r-3",
    "--shadow-1",
    "--t-body", "--t-lg", "--t-xl", "--t-2xl", "--t-3xl",
    "--font-body", "--font-mono",
]

CONCEPT = """You write CSS rules for a professional web application.
All rules are plain CSS. Use the design tokens already defined on
:root (CSS custom properties like --c-surface, --sp-4, --r-2) instead
of raw values wherever a requirement mentions a token."""

# Compact worked examples from a DIFFERENT domain (a cooking blog),
# used as few-shot demonstrations of the ANSWER FORMAT only.  The names
# and values are deliberately unrelated to the target application.
DEMO_TOKENS = """First, one example task from a DIFFERENT app (a cooking
blog) so you see the answer format.  That task was "define the blog
theme tokens", and the correct answer was:

/* blog theme tokens */
:root {
  --blog-bg: #faf7f2;
  --blog-surface: #ffffff;
  --blog-ink: #26221c;
  --blog-muted: #6b6459;
  --blog-accent: #8a5a2f;
  --blog-gap-1: 4px;
  --blog-gap-2: 12px;
  --blog-round: 8px;
}
"""

DEMO_COMPONENT = """First, one example task from a DIFFERENT app (a cooking
blog) so you see the answer format.  That task was "style the recipe
card component", and the correct answer was:

/* recipe card */
.recipe-card {
  background: var(--blog-surface);
  border: 1px solid #e7e0d5;
  border-radius: var(--blog-round);
  padding: var(--blog-gap-2);
}
.recipe-card:hover {
  border-color: var(--blog-accent);
}
"""

# ---------------------------------------------------------------- tasks --

TASKS = [
    # ---- Stage 1: fundamentals --------------------------------------
    dict(
        id="tokens", stage=1, harness="design-tokens",
        anchor=":root {\n",
        spec="""Write the design tokens block. Start from ":root {" and
define EVERY ONE of these custom properties with a value of your choice:
""" + "\n".join("  " + v for v in TOKEN_VARS) + """
Rules: colors must be valid CSS colors; --sp-1..--sp-6 must be an
increasing spacing scale in px (small to larger); --r-1..--r-3 must be
increasing border radii in px; --t-body..--t-3xl must be an increasing
font-size scale in px starting at 14 or 15px; --font-body must be a
font-family stack with a generic fallback. Text colors must contrast
with their intended backgrounds: --c-text with --c-bg (aim >= 4.5:1),
--c-muted with --c-bg (aim >= 4.5:1, but visibly lighter than --c-text),
--c-on-primary with --c-primary (aim >= 4.5:1). Close the block with }.""",
        static=dict(
            require_vars=TOKEN_VARS,
            forbid=["!important"],
        ),
    ),
    dict(
        id="reset", stage=1, harness="base-reset",
        anchor="*,\n*::before,\n*::after {\n",
        spec="""Write the base reset and document defaults. Start from
the universal selector that is already written. Rules:
1. universal selector: box-sizing: border-box; margin: 0; padding: 0;
2. a `body` rule: font-family var(--font-body); font-size var(--t-body);
   line-height 1.5; color var(--c-text); background-color var(--c-bg);
   -webkit-font-smoothing: antialiased;
3. a `button, input, select, textarea` rule: font: inherit;
   color: inherit;
4. an `img` rule: max-width: 100%; display: block;""",
        static=dict(fail_words=[], forbid=["!important", "display: none"]),
    ),
    dict(
        id="typography", stage=1, harness="typography-scale",
        anchor="h1, h2, h3, h4 {\n",
        spec="""Write the typography scale using the size tokens. Start
from the shared heading rule that is already written. Rules:
1. shared heading rule: font-weight 600; line-height 1.25; color
   var(--c-text);
2. h1 { font-size: var(--t-3xl); }  h2 { font-size: var(--t-2xl); }
   h3 { font-size: var(--t-xl); }  h4 { font-size: var(--t-lg); }
   (each size strictly larger than the next)
3. a `p` rule: margin-bottom var(--sp-3);
4. a `.t-muted` rule: color var(--c-muted); font-size: 13px;""",
        static=dict(fail_words=[], forbid=["!important"]),
    ),
    dict(
        id="spacing", stage=1, harness="spacing-layout",
        anchor=".stack {\n",
        spec="""Write the layout utilities. Start from ".stack {". Rules:
1. .stack { display: flex; flex-direction: column; gap: var(--sp-4); }
2. .row { display: flex; flex-direction: row; align-items: center;
   gap: var(--sp-3); }
3. .grid { display: grid; grid-template-columns: repeat(3, 1fr);
   gap: var(--sp-3); }
4. a media query: @media (max-width: 720px) { .grid becomes one column;
   .row wraps (flex-wrap: wrap); }""",
        static=dict(require_selectors=[".stack", ".row", ".grid",
                                       "@media"], forbid=["!important"]),
    ),
    dict(
        id="card", stage=1, harness="card",
        anchor=".card {\n",
        spec="""Write the card component. Start from ".card {". Rules:
1. .card: background var(--c-surface); border 1px solid var(--c-border);
   border-radius var(--r-2); padding var(--sp-4); box-shadow
   var(--shadow-1);
2. .card h3 { font-size: var(--t-lg); margin-bottom: var(--sp-2); }
3. .card p { color: var(--c-muted); }
4. .card-interactive:hover { border-color must change to something
   visibly different from the default border color }""",
        static=dict(require_selectors=[".card", ".card-interactive:hover"],
                    forbid=["!important", "display: none"]),
    ),
    dict(
        id="buttons", stage=1, harness="button-basics",
        anchor=".btn {\n",
        spec="""Write the base button. Start from ".btn {". Rules:
1. .btn: display inline-flex; align-items center; justify-content center;
   gap var(--sp-2); min-height 36px; padding var(--sp-2) var(--sp-4);
   border 1px solid transparent; border-radius var(--r-2);
   background var(--c-surface); color var(--c-text);
   font-size var(--t-body); font-weight 500; cursor pointer;
   transition for background-color, border-color and box-shadow;
2. .btn:hover { background must visibly change (e.g. a soft tint) }
3. .btn:focus-visible { outline: 2px solid var(--c-primary);
   outline-offset: 2px; }
4. .btn:disabled { opacity 0.55; cursor: not-allowed; }""",
        static=dict(require_selectors=[".btn", ".btn:hover",
                                       ".btn:focus-visible", ".btn:disabled"],
                    forbid=["!important", "display: none"]),
    ),
    dict(
        id="button-variants", stage=1, harness="button-variants",
        anchor=".btn-primary {\n",
        spec="""Write the button variants. Start from ".btn-primary {". Rules:
1. .btn-primary: background var(--c-primary); color var(--c-on-primary);
   and its :hover uses a visibly darker or lighter version of the same
   hue (e.g. filter: brightness(0.9));
2. .btn-ghost: background transparent; border 1px solid var(--c-border);
   color var(--c-text); its :hover changes the background to a soft tint
   (e.g. var(--c-primary-soft));
3. .btn-danger: background var(--c-danger); color must contrast with it
   (use var(--c-surface) or white); its :hover uses brightness;""",
        static=dict(require_selectors=[".btn-primary", ".btn-ghost",
                                       ".btn-danger", ".btn-primary:hover"],
                    forbid=["!important"]),
    ),
    dict(
        id="inputs", stage=1, harness="form-inputs",
        anchor=".input {\n",
        spec="""Write the form controls. Start from ".input {". Rules:
1. .input and .select (one shared rule): width 100%; min-height 36px;
   padding var(--sp-2) var(--sp-3); border 1px solid var(--c-border);
   border-radius var(--r-1); background var(--c-surface);
   color var(--c-text); font-size var(--t-body);
2. .input:focus, .select:focus { border-color var(--c-primary);
   outline none; box-shadow 0 0 0 3px var(--c-primary-soft); }
3. .input.is-invalid { border-color var(--c-danger); }
4. .field { display flex; flex-direction column; gap var(--sp-2); }
5. .field-label { font-size 13px; font-weight 500; color var(--c-muted); }
6. .field-error { color var(--c-danger); font-size 12px; }""",
        static=dict(require_selectors=[".input", ".select", ".input:focus",
                                       ".field", ".field-error"],
                    forbid=["!important"]),
    ),
    dict(
        id="states", stage=1, harness="interactive-states",
        anchor=".link {\n",
        spec="""Write the remaining interaction states. Start from
".link {". Rules:
1. .link { color var(--c-primary); text-decoration none; cursor pointer; }
2. .link:hover { text-decoration underline; }
3. .btn, .project-btn, .filter-all, .filter-todo, .filter-doing,
   .filter-done (one shared rule) { cursor: pointer; }
4. a shared transition rule for .btn and .link: transition color
   0.15s ease, background-color 0.15s ease;""",
        static=dict(require_selectors=[".link", ".link:hover"],
                    forbid=["!important"]),
    ),
    # ---- Stage 2: components ---------------------------------------
    dict(
        id="badges", stage=2, harness="badge",
        anchor=".badge {\n",
        spec="""Write the status/priority badges. Start from ".badge {". Rules:
1. .badge { display inline-flex; align-items center; padding 2px
   var(--sp-2); border-radius 999px; font-size 12px; font-weight 600;
   letter-spacing 0.02em; }
2. .badge-high { background var(--c-high); } — and the TEXT color must
   be readable on that background: use color var(--c-surface) or white
   if the background is dark;
3. .badge-medium { background var(--c-medium); } with readable text;
4. .badge-low { background var(--c-low); } with readable text;
5. .badge-done { background var(--c-done); } with readable text;
6. .badge-todo { background var(--c-todo); } with readable text;
7. .badge-doing { background var(--c-doing); } with readable text;
Every badge's text must reach at least 3:1 contrast against its own
background — prefer light text (white / var(--c-surface)) on saturated
backgrounds.""",
        static=dict(require_selectors=[".badge", ".badge-high",
                                       ".badge-medium", ".badge-low",
                                       ".badge-done", ".badge-todo",
                                       ".badge-doing"], forbid=["!important"]),
    ),
    dict(
        id="progress", stage=2, harness="progress",
        anchor=".progress {\n",
        spec="""Write the progress visualization. Start from ".progress {". Rules:
1. .progress { height 10px; border-radius 999px; background
   var(--c-border); overflow hidden; width 100%; }
2. .progress-fill { height 100%; border-radius 999px; background
   var(--c-primary); }
3. .progress-card { background var(--c-surface); border 1px solid
   var(--c-border); border-radius var(--r-2); padding var(--sp-4);
   display flex; flex-direction column; gap var(--sp-2); }
4. .progress-head { display flex; justify-content space-between;
   align-items baseline; }
5. .progress-label { font-size 13px; font-weight 500;
   color var(--c-muted); }
6. .progress-text { font-size var(--t-lg); font-weight 600;
   color var(--c-text); font-variant-numeric tabular-nums; }""",
        static=dict(require_selectors=[".progress", ".progress-fill",
                                       ".progress-card", ".progress-text"],
                    forbid=["!important", "display: none"]),
    ),
    dict(
        id="header", stage=2, harness="app-header",
        anchor=".app-header {\n",
        spec="""Write the application header. Start from ".app-header {". Rules:
1. .app-header { display flex; align-items center; justify-content
   space-between; gap var(--sp-4); padding var(--sp-3) var(--sp-5);
   background var(--c-surface); border-bottom 1px solid
   var(--c-border); }
2. .brand { display flex; align-items baseline; gap var(--sp-3); }
3. .brand-name { font-size var(--t-xl); font-weight 700;
   letter-spacing -0.01em; }
4. .brand-tag { font-size 13px; color var(--c-muted); }
5. .header-actions { display flex; align-items center; gap var(--sp-3); }
6. .offline-badge { padding 2px var(--sp-2); border-radius 999px;
   font-size 12px; font-weight 600; background var(--c-primary-soft);
   color var(--c-text); border 1px solid var(--c-border); }""",
        static=dict(require_selectors=[".app-header", ".brand",
                                       ".brand-name", ".offline-badge"],
                    forbid=["!important"]),
    ),
    dict(
        id="nav", stage=2, harness="app-nav",
        anchor=".app-nav {\n",
        spec="""Write the sidebar navigation. Start from ".app-nav {". Rules:
1. .app-nav { display flex; flex-direction column; gap var(--sp-3); }
2. .nav-title { font-size var(--t-lg); font-weight 600; }
3. .nav-list { display flex; flex-direction column; gap var(--sp-2);
   max-height 40vh; overflow-y auto; padding-right var(--sp-1); }
4. .project-btn { display flex; align-items center; width 100%;
   text-align left; min-height 36px; padding var(--sp-2) var(--sp-3);
   border 1px solid transparent; border-radius var(--r-2);
   background transparent; color var(--c-text); cursor pointer;
   transition background-color 0.15s ease; }
5. .project-btn:hover { background var(--c-primary-soft); }
6. .project-btn.active or .project-btn:focus-visible { background
   var(--c-primary-soft); border-color var(--c-primary); }""",
        static=dict(require_selectors=[".app-nav", ".nav-list",
                                       ".project-btn", ".project-btn:hover"],
                    forbid=["!important", "display: none"]),
    ),
    dict(
        id="taskrow", stage=2, harness="task-row",
        anchor=".task-row {\n",
        spec="""Write the task list row. Start from ".task-row {". Rules:
1. .task-row { display flex; align-items center; gap var(--sp-3);
   padding var(--sp-3) var(--sp-4); background var(--c-surface);
   border 1px solid var(--c-border); border-radius var(--r-2);
   transition border-color 0.15s ease; }
2. .task-row:hover { border-color must visibly change }
3. .task-check { display flex; align-items center; gap var(--sp-3);
   flex 1; min-width 0; cursor pointer; }
4. .task-title { font-size var(--t-body); overflow hidden;
   text-overflow ellipsis; white-space nowrap; }
5. .task-done .task-title { color var(--c-muted);
   text-decoration line-through; }
6. .task-actions { display flex; gap var(--sp-2); margin-left auto; }
7. .task-list { display flex; flex-direction column; gap var(--sp-2); }""",
        static=dict(require_selectors=[".task-row", ".task-row:hover",
                                       ".task-title", ".task-actions",
                                       ".task-list"], forbid=["!important"]),
    ),
    dict(
        id="empty", stage=2, harness="empty-state",
        anchor=".empty-state {\n",
        spec="""Write the empty state. Start from ".empty-state {". Rules:
1. .empty-state { display flex; flex-direction column; align-items
   center; justify-content center; text-align center; gap var(--sp-2);
   padding var(--sp-6) var(--sp-4); border 1px dashed
   var(--c-border); border-radius var(--r-2); }
2. .empty-icon { width 40px; height 40px; display flex; align-items
   center; justify-content center; border-radius 999px; background
   var(--c-primary-soft); color var(--c-primary); font-size
   var(--t-lg); font-weight 700; }
3. .empty-title { font-size var(--t-lg); font-weight 600; }
4. .empty-text { font-size 13px; color var(--c-muted); max-width
   32ch; }""",
        static=dict(require_selectors=[".empty-state", ".empty-icon",
                                       ".empty-title", ".empty-text"],
                    forbid=["!important"]),
    ),
    dict(
        id="modal", stage=2, harness="modal",
        anchor=".modal-overlay {\n",
        spec="""Write the modal dialog. Start from ".modal-overlay {". Rules:
1. .modal-overlay { position fixed; inset 0; display flex; align-items
   center; justify-content center; padding var(--sp-4); background
   rgba(15, 23, 42, 0.55); }
2. .modal { background var(--c-surface); border-radius var(--r-3);
   box-shadow var(--shadow-1); padding var(--sp-5); width 100%;
   max-width 420px; display flex; flex-direction column; gap
   var(--sp-4); }
3. .modal-title { font-size var(--t-xl); font-weight 600; }
4. .modal-actions { display flex; justify-content flex-end; gap
   var(--sp-3); }""",
        static=dict(require_selectors=[".modal-overlay", ".modal",
                                       ".modal-actions"], forbid=["!important"]),
    ),
    dict(
        id="toast", stage=2, harness="toast",
        anchor=".toast-stack {\n",
        spec="""Write the toast notifications. Start from ".toast-stack {". Rules:
1. .toast-stack { position fixed; bottom var(--sp-4); right var(--sp-4);
   display flex; flex-direction column; gap var(--sp-2); z-index 50; }
2. .toast { padding var(--sp-2) var(--sp-4); border-radius var(--r-2);
   font-size var(--t-body); font-weight 500; box-shadow
   var(--shadow-1); }
3. .toast-success { background var(--c-success); color must be
   readable on it (white or var(--c-surface)); }
4. .toast-error { background var(--c-danger); color must be readable
   on it (white or var(--c-surface)); }""",
        static=dict(require_selectors=[".toast", ".toast-success",
                                       ".toast-error"], forbid=["!important"]),
    ),
    dict(
        id="skeleton", stage=2, harness="skeleton",
        anchor=".skeleton {\n",
        spec="""Write the loading skeleton. Start from ".skeleton {". Rules:
1. .skeleton { background var(--c-border); border-radius var(--r-1);
   animation skeleton-pulse 1.4s ease-in-out infinite; }
2. .skeleton-line { height 12px; width 60%; }
3. .skeleton-block { height 72px; width 100%; }
4. @keyframes skeleton-pulse { 0%, 100% { opacity 1; } 50% { opacity
   0.45; } }""",
        static=dict(require_selectors=[".skeleton", "@keyframes"],
                    forbid=["!important"]),
    ),
    # ---- Stage 3: composition --------------------------------------
    dict(
        id="shell", stage=3, harness="app-shell",
        anchor=".app {\n",
        spec="""Write the application shell layout. Start from ".app {". Rules:
1. .app { display flex; flex-direction column; min-height 100vh;
   background var(--c-bg); }
2. .app-side { display flex; flex-direction column; gap var(--sp-4);
   padding var(--sp-4); background var(--c-surface); border-right 1px
   solid var(--c-border); }
3. .app-main { flex 1; padding var(--sp-5); min-width 0; }
4. On desktop (a new media query with min-width: 721px) the .app
   becomes a horizontal row: flex-direction row; and .app-side gets
   width 280px; flex-shrink 0;
5. .panel { display flex; flex-direction column; gap var(--sp-4);
   max-width 860px; }
6. .panel-head { display flex; align-items baseline; justify-content
   space-between; gap var(--sp-4); flex-wrap wrap; }
7. .panel-title { font-size var(--t-2xl); font-weight 700; }
8. a media query (max-width 720px): .app-main padding var(--sp-3);
   .panel-head keeps wrapping (no horizontal overflow anywhere).""",
        static=dict(require_selectors=[".app", ".app-side", ".app-main",
                                       ".panel", "@media"],
                    forbid=["!important"]),
    ),
]

TASK_IDS = [t["id"] for t in TASKS]


def task_by_id(tid: str):
    for t in TASKS:
        if t["id"] == tid:
            return t
    raise KeyError(tid)


def piece_prompt(task: dict, feedback: str | None = None,
                 own_previous: str | None = None) -> str:
    """Build the anchored few-shot prompt for one curriculum piece.

    Structure (base-model friendly): concept -> compact different-domain
    demo -> task requirements -> (own previous bytes + checker failures
    on repair rounds) -> final instruction + anchor as the last line.
    """
    parts = [CONCEPT, ""]
    demo = DEMO_TOKENS if task["id"] == "tokens" else DEMO_COMPONENT
    parts.append(demo)
    parts.append("Now YOUR task. " + task["spec"])
    if own_previous:
        parts.append("")
        parts.append("Your previous attempt (which did not pass the "
                     "automated checker) was:")
        parts.append(own_previous)
    if feedback:
        parts.append("")
        parts.append("The automated checker reported these failures:")
        parts.append(feedback)
        parts.append("Fix exactly those problems. Keep everything else "
                     "the same.")
    parts.append("")
    parts.append("Write the answer now. The first line is already "
                 "written; continue from it:")
    parts.append(task["anchor"])
    return "\n".join(parts)


# Selectors that must NOT appear in a candidate (they belong to the
# different-domain demos; their presence means the model echoed the
# example instead of writing the target component).
DEMO_MARKERS = ["--blog-", ".recipe-card", ".chip"]; 
