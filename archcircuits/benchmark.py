"""ArchBench: an architectural-reasoning benchmark for Qwen2.5-Coder-0.5B (base).

Four categories, authored from scratch for this research branch:

* VAR  - variable and state tracking (reassignment, aliasing, cross-call state)
* CON  - interface-contract compliance (signatures, returned shapes, bindings)
* JSR  - JavaScript reasoning (values, async ordering, web/express behavior)
* XCOM - cross-component reasoning (storage<->API<->frontend contracts)

Every task is a short-answer question with a deterministic gold answer that is
verified by executing the *reference* snippet authored by us (never
model-generated code).  Tasks are partitioned into dev / val / holdout before
any weight modification is constructed.  The holdout partition is authored
with deliberately different identifier names, domains and structures.

Zero tasks are drawn from HumanEval (all 164 HumanEval IDs were consumed by
Sessions 001-009 of this repository), so there is no contamination of the
kind tracked in AGENTS.md.

dev tasks additionally carry a *counterfactual* variant (a modified critical
value with its own gold answer) used only for causal activation patching in
Phase B.  Counterfactuals are never used to build weight edits directly.
"""

from __future__ import annotations

CATEGORIES = ("VAR", "CON", "JSR", "XCOM")

_INSTR = {
    "VAR": "Read the Python code, then answer with the exact final value.",
    "CON": "Read the interface contract, then answer with the exact requested code line or identifier.",
    "JSR": "Read the JavaScript code, then answer with the exact value.",
    "XCOM": "Read both files, then answer with the exact identifier or keyword that keeps the components consistent.",
}

# Two fixed few-shot examples per category.  They are part of the prompt
# template, never scored, and deliberately use names/values absent from all
# scored tasks.
_FEWSHOT = {
    "VAR": [
        ("```python\nn = 2\nn = n + 5\n```\nWhat is the value of n?", "7"),
        ("```python\np = [4]\nq = p\nq.append(5)\n```\nWhat is the value of p?", "[4, 5]"),
    ],
    "CON": [
        (
            "# Contract: send_error must respond with a JSON object having exactly the key \"error\".\n"
            "Write the one-line Express statement for message \"gone\" (use res, status 404).",
            'res.status(404).json({ error: "gone" });',
        ),
        (
            "# helpers.py exposes: slugify(text) -> str\n"
            "# pages.py must convert a title to a slug.\n"
            "def page_slug(title):\n    return ______(title)",
            "slugify",
        ),
    ],
    "JSR": [
        ("```javascript\nconst m = [2, 3].map(v => v * 10);\n```\nWhat is the value of m?", "[20, 30]"),
        ("```javascript\nconsole.log(\"x\");\nPromise.resolve().then(() => console.log(\"y\"));\nconsole.log(\"z\");\n```\nWhat is the logged order?", "x z y"),
    ],
    "XCOM": [
        (
            "```python\n# data.py\nLIMIT = 9\n\n# app.py\nimport data\n\ndef cap():\n    return data.______\n```\nWhich name fills the blank?",
            "LIMIT",
        ),
        (
            "```javascript\n// api.js responds with: res.json({ rows: [5, 6] });\n// table.js\nconst payload = await fetchJSON(\"/rows\");\nconst shown = payload.______;\n```\nWhich property fills the blank?",
            "rows",
        ),
    ],
}


def build_prompt(category: str, question: str) -> str:
    """Render one task as a completion-style prompt for the base model."""
    parts = [_INSTR[category], ""]
    for q, a in _FEWSHOT[category]:
        parts += [f"Q: {q}", f"A: {a}", ""]
    parts += [f"Q: {question}", "A:"]
    return "\n".join(parts)


def _t(task_id, category, sub, difficulty, partition, question, gold, cf=None, critical=None):
    return {
        "id": task_id,
        "category": category,
        "subcategory": sub,
        "difficulty": difficulty,
        "partition": partition,
        "question": question,
        "gold": gold,
        "cf": cf,          # {"question": ..., "gold": ..., "critical": ...} for dev tasks
        "critical": critical,
    }


TASKS: list[dict] = []

# ---------------------------------------------------------------------------
# A1 - VAR: variable and state tracking
# ---------------------------------------------------------------------------
VAR_DEV = [
    _t("VAR-001", "VAR", "reassign", 1, "dev",
       "```python\nx = 5\nx = x + 3\nx = x * 2\n```\nWhat is the value of x?", "16",
       cf={"question": "```python\nx = 6\nx = x + 3\nx = x * 2\n```\nWhat is the value of x?", "gold": "18", "critical": "x = 6"},
       critical="x = 5"),
    _t("VAR-002", "VAR", "reassign", 1, "dev",
       "```python\ntotal = 10\ntotal = total - 4\ntotal = total + 1\n```\nWhat is the value of total?", "7",
       cf={"question": "```python\ntotal = 11\ntotal = total - 4\ntotal = total + 1\n```\nWhat is the value of total?", "gold": "8", "critical": "total = 11"},
       critical="total = 10"),
    _t("VAR-003", "VAR", "reassign", 2, "dev",
       "```python\nn = 3\nn = n * n\nn = n + n\n```\nWhat is the value of n?", "18",
       cf={"question": "```python\nn = 4\nn = n * n\nn = n + n\n```\nWhat is the value of n?", "gold": "32", "critical": "n = 4"},
       critical="n = 3"),
    _t("VAR-004", "VAR", "reassign", 2, "dev",
       "```python\ns = \"ab\"\ns = s + \"cd\"\ns = s[1:]\n```\nWhat is the value of s?", "\"bcd\"",
       cf={"question": "```python\ns = \"ax\"\ns = s + \"cd\"\ns = s[1:]\n```\nWhat is the value of s?", "gold": "\"xcd\"", "critical": "s = \"ax\""},
       critical="s = \"ab\""),
    _t("VAR-005", "VAR", "reassign", 3, "dev",
       "```python\na = 2\nb = a * 3\na = b + 1\nb = a * 2\n```\nWhat is the value of b?", "14",
       cf={"question": "```python\na = 3\nb = a * 3\na = b + 1\nb = a * 2\n```\nWhat is the value of b?", "gold": "20", "critical": "a = 3"},
       critical="a = 2"),
    _t("VAR-006", "VAR", "alias", 1, "dev",
       "```python\na = [1, 2]\nb = a\nb.append(3)\n```\nWhat is the value of a?", "[1, 2, 3]",
       cf={"question": "```python\na = [1, 7]\nb = a\nb.append(3)\n```\nWhat is the value of a?", "gold": "[1, 7, 3]", "critical": "a = [1, 7]"},
       critical="a = [1, 2]"),
    _t("VAR-007", "VAR", "alias", 2, "dev",
       "```python\na = [1, 2]\nb = a[:]\nb.append(3)\n```\nWhat is the value of a?", "[1, 2]",
       cf={"question": "```python\na = [1, 7]\nb = a[:]\nb.append(3)\n```\nWhat is the value of a?", "gold": "[1, 7]", "critical": "a = [1, 7]"},
       critical="b = a[:]"),
    _t("VAR-008", "VAR", "alias", 2, "dev",
       "```python\na = [1, 2]\nb = a\nb = [9]\n```\nWhat is the value of a?", "[1, 2]",
       cf={"question": "```python\na = [4, 2]\nb = a\nb = [9]\n```\nWhat is the value of a?", "gold": "[4, 2]", "critical": "a = [4, 2]"},
       critical="b = a"),
    _t("VAR-009", "VAR", "alias", 3, "dev",
       "```python\nconfig = {\"db\": \"old\"}\ncopy = dict(config)\ncopy[\"db\"] = \"new\"\n```\nWhat is the value of config?", '{"db": "old"}',
       cf={"question": "```python\nconfig = {\"db\": \"prior\"}\ncopy = dict(config)\ncopy[\"db\"] = \"new\"\n```\nWhat is the value of config?", "gold": '{"db": "prior"}', "critical": 'config = {"db": "prior"}'},
       critical="copy = dict(config)"),
    _t("VAR-010", "VAR", "state", 1, "dev",
       "```python\nclass Counter:\n    def __init__(self):\n        self.count = 0\n    def inc(self):\n        self.count += 1\n\nc = Counter()\nc.inc()\nc.inc()\nc.inc()\n```\nWhat is the value of c.count?", "3",
       cf={"question": "```python\nclass Counter:\n    def __init__(self):\n        self.count = 0\n    def inc(self):\n        self.count += 1\n\nc = Counter()\nc.inc()\nc.inc()\n```\nWhat is the value of c.count?", "gold": "2", "critical": "c.inc()\nc.inc()\n```\nWhat is the value of c.count?"},
       critical="self.count += 1"),
    _t("VAR-011", "VAR", "state", 2, "dev",
       "```python\ndef make_greeter(greeting):\n    def greet(name):\n        return greeting + \", \" + name\n    return greet\n\nhello = make_greeter(\"Hello\")\nbye = make_greeter(\"Bye\")\n```\nWhat does hello(\"Ann\") return?", '"Hello, Ann"',
       cf={"question": "```python\ndef make_greeter(greeting):\n    def greet(name):\n        return greeting + \", \" + name\n    return greet\n\nhello = make_greeter(\"Hi\")\nbye = make_greeter(\"Bye\")\n```\nWhat does hello(\"Ann\") return?", "gold": '"Hi, Ann"', "critical": 'hello = make_greeter("Hi")'},
       critical='hello = make_greeter("Hello")'),
    _t("VAR-012", "VAR", "state", 3, "dev",
       "```python\ncount = 0\n\ndef bump():\n    global count\n    count += 2\n\nbump()\nbump()\ncount = count + 1\n```\nWhat is the value of count?", "5",
       cf={"question": "```python\ncount = 0\n\ndef bump():\n    global count\n    count += 3\n\nbump()\nbump()\ncount = count + 1\n```\nWhat is the value of count?", "gold": "7", "critical": "count += 3"},
       critical="count += 2"),
]
VAR_VAL = [
    _t("VAR-101", "VAR", "reassign", 1, "val",
       "```python\nw = 7\nw = w * 3\nw = w - 6\n```\nWhat is the value of w?", "15"),
    _t("VAR-102", "VAR", "reassign", 2, "val",
       "```python\np = 4\np = p * p\np = p // 2\n```\nWhat is the value of p?", "8"),
    _t("VAR-103", "VAR", "reassign", 3, "val",
       "```python\nk = 5\nm = k + 2\nk = m * 2\nm = k - m\n```\nWhat is the value of m?", "7"),
    _t("VAR-104", "VAR", "alias", 1, "val",
       "```python\nlst = [0]\nref = lst\nref.append(7)\n```\nWhat is the value of lst?", "[0, 7]"),
    _t("VAR-105", "VAR", "alias", 2, "val",
       "```python\nlst = [3, 4]\ncp = list(lst)\ncp.pop()\n```\nWhat is the value of lst?", "[3, 4]"),
    _t("VAR-106", "VAR", "alias", 3, "val",
       "```python\nd = {\"a\": 1}\ne = d\ne[\"b\"] = 2\n```\nWhat is the value of d?", '{"a": 1, "b": 2}'),
    _t("VAR-107", "VAR", "state", 2, "val",
       "```python\nclass Wallet:\n    def __init__(self):\n        self.balance = 10\n    def deposit(self, amount):\n        self.balance += amount\n\nw = Wallet()\nw.deposit(5)\nw.deposit(5)\n```\nWhat is the value of w.balance?", "20"),
    _t("VAR-108", "VAR", "state", 3, "val",
       "```python\ndef make_multiplier(factor):\n    def mul(v):\n        return v * factor\n    return mul\n\nf = make_multiplier(3)\n```\nWhat does f(4) return?", "12"),
]
VAR_HOLD = [
    _t("VAR-201", "VAR", "reassign", 1, "holdout",
       "```python\nscore = 12\nscore = score // 2\nscore = score + 3\n```\nWhat is the value of score?", "9"),
    _t("VAR-202", "VAR", "reassign", 2, "holdout",
       "```python\ntag = \"xy\"\ntag = tag + \"z\"\ntag = tag.replace(\"x\", \"\")\n```\nWhat is the value of tag?", '"yz"'),
    _t("VAR-203", "VAR", "reassign", 3, "holdout",
       "```python\nu = 6\nv = u - 2\nu = v * 3\nv = u + v\n```\nWhat is the value of v?", "16"),
    _t("VAR-204", "VAR", "alias", 1, "holdout",
       "```python\nqueue = [\"a\"]\nmirror = queue\nmirror.append(\"b\")\n```\nWhat is the value of queue?", '["a", "b"]'),
    _t("VAR-205", "VAR", "alias", 2, "holdout",
       "```python\ngrid = [1, 2]\nsnapshot = grid.copy()\nsnapshot[0] = 99\n```\nWhat is the value of grid?", "[1, 2]"),
    _t("VAR-206", "VAR", "alias", 3, "holdout",
       "```python\ncfg = {\"port\": 80}\nlink = cfg\nlink[\"port\"] = 443\n```\nWhat is the value of cfg[\"port\"]?", "443"),
    _t("VAR-207", "VAR", "state", 1, "holdout",
       "```python\nclass Timer:\n    def __init__(self):\n        self.ticks = 0\n    def tick(self):\n        self.ticks += 1\n\nt = Timer()\nt.tick()\nt.tick()\nt.tick()\n```\nWhat is the value of t.ticks?", "3"),
    _t("VAR-208", "VAR", "state", 3, "holdout",
       "```python\ndef make_accumulator():\n    total = 0\n    def add(v):\n        nonlocal total\n        total += v\n        return total\n    return add\n\nacc = make_accumulator()\nacc(4)\nacc(4)\n```\nWhat does acc(4) return the third time it is called with 4?", "12"),
]

# ---------------------------------------------------------------------------
# A2 - CON: interface-contract compliance
# ---------------------------------------------------------------------------
CON_DEV = [
    _t("CON-001", "CON", "binding", 1, "dev",
       "```python\n# storage.py\ndef get_user(user_id):\n    return {\"name\": \"Ann\", \"email\": \"a@x.io\"}\n\n# api.py\nfrom storage import get_user\n\ndef handler(user_id):\n    user = ______(user_id)\n    return user[\"name\"]\n```\nWhich function name fills the blank?", "get_user",
       cf={"question": "```python\n# storage.py\ndef load_user(user_id):\n    return {\"name\": \"Ann\", \"email\": \"a@x.io\"}\n\n# api.py\nfrom storage import load_user\n\ndef handler(user_id):\n    user = ______(user_id)\n    return user[\"name\"]\n```\nWhich function name fills the blank?", "gold": "load_user", "critical": "from storage import load_user"},
       critical="from storage import get_user"),
    _t("CON-002", "CON", "binding", 1, "dev",
       "# cart.py exposes: add_item(cart, item), remove_item(cart, item_id)\n\n# shop.py\nfrom cart import add_item\n\ndef purchase(cart, item):\n    return ______(cart, item)\n\nWhich function name fills the blank?", "add_item",
       cf={"question": "# cart.py exposes: put_item(cart, item), remove_item(cart, item_id)\n\n# shop.py\nfrom cart import put_item\n\ndef purchase(cart, item):\n    return ______(cart, item)\n\nWhich function name fills the blank?", "gold": "put_item", "critical": "from cart import put_item"},
       critical="from cart import add_item"),
    _t("CON-003", "CON", "binding", 2, "dev",
       "```javascript\n// storage.js\nexport function getUser(id) { return { name: \"Ann\" }; }\nexport function deleteUser(id) { }\n\n// route.js\nimport { ______ } from \"./storage.js\";\n\napp.get(\"/users/:id\", (req, res) => {\n  const user = getUser(req.params.id);\n  res.json(user);\n});\n```\nWhich function name fills the blank?", "getUser",
       cf={"question": "```javascript\n// storage.js\nexport function findUser(id) { return { name: \"Ann\" }; }\nexport function deleteUser(id) { }\n\n// route.js\nimport { ______ } from \"./storage.js\";\n\napp.get(\"/users/:id\", (req, res) => {\n  const user = findUser(req.params.id);\n  res.json(user);\n});\n```\nWhich function name fills the blank?", "gold": "findUser", "critical": "export function findUser(id)"},
       critical="export function getUser(id)"),
    _t("CON-004", "CON", "shape", 1, "dev",
       '# Contract: create_user must return a dict with exactly the keys "id" (int) and "name" (str).\nWrite the return statement (one line) for name="Bo" and id 42.', 'return {"id": 42, "name": "Bo"}',
       cf={"question": '# Contract: create_user must return a dict with exactly the keys "id" (int) and "name" (str).\nWrite the return statement (one line) for name="Bo" and id 43.', "gold": 'return {"id": 43, "name": "Bo"}', "critical": 'id 43'},
       critical='"id" (int) and "name" (str)'),
    _t("CON-005", "CON", "shape", 2, "dev",
       '# Contract: parse_config returns {"ok": <bool>, "value": <str>}; for input "a=1" it returns ok=True and value="1".\nWrite the exact dict literal returned.', '{"ok": True, "value": "1"}',
       cf={"question": '# Contract: parse_config returns {"ok": <bool>, "value": <str>} ; for input "a=9" it returns ok=True and value="9".\nWrite the exact dict literal returned.', "gold": '{"ok": True, "value": "9"}', "critical": 'value="9"'},
       critical='{"ok": <bool>, "value": <str>}'),
    _t("CON-006", "CON", "shape", 2, "dev",
       '// Contract: respondSuccess(res, data) must send { "status": "ok", "data": data }.\nWrite the single-line function body.', 'res.json({ status: "ok", data: data });',
       cf={"question": '// Contract: respondSuccess(res, data) must send { "status": "done", "data": data }.\nWrite the single-line function body.', "gold": 'res.json({ status: "done", data: data });', "critical": '"done"'},
       critical='{ "status": "ok", "data": data }'),
    _t("CON-007", "CON", "signature", 1, "dev",
       "Write only the Python function signature (one line, no body): a function named add_item that takes cart (dict) and item (str) and returns a dict.",
       "def add_item(cart: dict, item: str) -> dict:",
       cf={"question": "Write only the Python function signature (one line, no body): a function named add_row that takes cart (dict) and item (str) and returns a dict.", "gold": "def add_row(cart: dict, item: str) -> dict:", "critical": "add_row"},
       critical="add_item"),
    _t("CON-008", "CON", "signature", 2, "dev",
       "Write only the first line of a JavaScript function declaration (no body): a function named formatPrice that takes cents and returns a number.",
       "function formatPrice(cents) {",
       cf={"question": "Write only the first line of a JavaScript function declaration (no body): a function named formatCost that takes cents and returns a number.", "gold": "function formatCost(cents) {", "critical": "formatCost"},
       critical="formatPrice"),
    _t("CON-009", "CON", "binding", 2, "dev",
       "```python\n# storage.py\nclass Store:\n    def get(self, key): ...\n    def put(self, key, value): ...\n    def delete(self, key): ...\n\n# api.py — must remove the record for a key\ndef remove_record(store, key):\n    store.______(key)\n    return True\n```\nWhich method name fills the blank?", "delete",
       cf={"question": "```python\n# storage.py\nclass Store:\n    def get(self, key): ...\n    def put(self, key, value): ...\n    def erase(self, key): ...\n\n# api.py — must remove the record for a key\ndef remove_record(store, key):\n    store.______(key)\n    return True\n```\nWhich method name fills the blank?", "gold": "erase", "critical": "def erase(self, key): ..."},
       critical="def delete(self, key): ..."),
    _t("CON-010", "CON", "binding", 3, "dev",
       "```python\n# db.py\ndef fetch_orders(user_id): return [{\"id\": 1, \"total\": 9}]\ndef fetch_user(user_id): return {\"id\": 7}\n\n# report.py — must build {\"user\": {...}, \"orders\": [...]}\nfrom db import fetch_orders, fetch_user\n\ndef build_report(user_id):\n    return {\"user\": ______(user_id), \"orders\": fetch_orders(user_id)}\n```\nWhich function name fills the blank?", "fetch_user",
       cf={"question": "```python\n# db.py\ndef fetch_orders(user_id): return [{\"id\": 1, \"total\": 9}]\ndef load_user(user_id): return {\"id\": 7}\n\n# report.py — must build {\"user\": {...}, \"orders\": [...]}\nfrom db import fetch_orders, load_user\n\ndef build_report(user_id):\n    return {\"user\": ______(user_id), \"orders\": fetch_orders(user_id)}\n```\nWhich function name fills the blank?", "gold": "load_user", "critical": 'from db import fetch_orders, load_user'},
       critical='{"user": ______(user_id), "orders": fetch_orders(user_id)}'),
    _t("CON-011", "CON", "shape", 3, "dev",
       '# Contract: validate(data) raises ValueError for a non-list input and returns True otherwise.\nWhat does validate("no") do?',
       "raises ValueError",
       cf={"question": '# Contract: validate(data) raises TypeError for a non-list input and returns True otherwise.\nWhat does validate("no") do?', "gold": "raises TypeError", "critical": "raises TypeError"},
       critical="raises ValueError for a non-list input"),
    _t("CON-012", "CON", "shape", 1, "dev",
       'The frontend requires every API error response to be JSON of the form {"error": "<message>"}.\nWrite the one-line Express statement that responds with status 400 and error "invalid" (use res).',
       'res.status(400).json({ error: "invalid" });',
       cf={"question": 'The frontend requires every API error response to be JSON of the form {"error": "<message>"}.\nWrite the one-line Express statement that responds with status 409 and error "invalid" (use res).', "gold": 'res.status(409).json({ error: "invalid" });', "critical": "status 409"},
       critical='{"error": "<message>"}'),
]
CON_VAL = [
    _t("CON-101", "CON", "binding", 1, "val",
       "```python\n# kv.py\ndef set_key(k, v): ...\ndef get_key(k): ...\n\n# cache.py — must read the value for a key\nfrom kv import get_key, set_key\n\ndef read(k):\n    return ______(k)\n```\nWhich function name fills the blank?", "get_key"),
    _t("CON-102", "CON", "binding", 2, "val",
       "```python\n# repo.py\nclass Repo:\n    def insert(self, doc): ...\n    def find(self, doc_id): ...\n    def update(self, doc_id, doc): ...\n\n# service.py — must overwrite an existing document\ndef save(repo, doc_id, doc):\n    repo.______(doc_id, doc)\n```\nWhich method name fills the blank?", "update"),
    _t("CON-103", "CON", "shape", 1, "val",
       '# Contract: create_task must return a dict with exactly the keys "tid" (int) and "title" (str).\nWrite the return statement (one line) for title="fix" and tid 7.',
       'return {"tid": 7, "title": "fix"}'),
    _t("CON-104", "CON", "shape", 2, "val",
       '# Contract: parse_range returns {"ok": <bool>, "lo": <int>} ; for input "2..5" it returns ok=True, lo=2.\nWrite the exact dict literal returned.',
       '{"ok": True, "lo": 2}'),
    _t("CON-105", "CON", "signature", 1, "val",
       "Write only the Python function signature (one line, no body): a function named remove_item that takes cart (dict) and item_id (int) and returns a dict.",
       "def remove_item(cart: dict, item_id: int) -> dict:"),
    _t("CON-106", "CON", "signature", 2, "val",
       "Write only the first line of a JavaScript function declaration (no body): a function named buildQuery that takes params and returns a string.",
       "function buildQuery(params) {"),
    _t("CON-107", "CON", "binding", 3, "val",
       "```javascript\n// auth.js\nexport function signIn(user, pass) { }\nexport function signOut() { }\nexport function refreshToken(token) { }\n\n// session.js — must refresh an existing session token\nimport { ______ } from \"./auth.js\";\n\nexport async function keepAlive(token) {\n  return refreshToken(token);\n}\n```\nWhich function name fills the blank?", "refreshToken"),
    _t("CON-108", "CON", "shape", 2, "val",
       '// Contract: respondCreated(res, body) must send status 201 with { "created": body }.\nWrite the single-line function body.',
       'res.status(201).json({ created: body });'),
]
CON_HOLD = [
    _t("CON-201", "CON", "binding", 1, "holdout",
       "```python\n# crew_store.py\ndef fetch_shift(shift_id): ...\ndef fetch_member(member_id): ...\n\n# roster.py — must load one crew member\nfrom crew_store import fetch_member, fetch_shift\n\ndef load_member(member_id):\n    return ______(member_id)\n```\nWhich function name fills the blank?", "fetch_member"),
    _t("CON-202", "CON", "binding", 2, "holdout",
       "```python\n# ledger.py\nclass Ledger:\n    def post(self, entry): ...\n    def close(self, period): ...\n    def amend(self, entry_id, entry): ...\n\n# audit.py — must correct an already-posted entry\ndef correct(ledger, entry_id, entry):\n    ledger.______(entry_id, entry)\n```\nWhich method name fills the blank?", "amend"),
    _t("CON-203", "CON", "shape", 1, "holdout",
       '# Contract: create_invoice must return a dict with exactly the keys "ref" (int) and "amount" (int).\nWrite the return statement (one line) for amount=90 and ref 12.',
       'return {"ref": 12, "amount": 90}'),
    _t("CON-204", "CON", "shape", 2, "holdout",
       '# Contract: parse_window returns {"ok": <bool>, "start": <int>} ; for input "9-17" it returns ok=True, start=9.\nWrite the exact dict literal returned.',
       '{"ok": True, "start": 9}'),
    _t("CON-205", "CON", "signature", 1, "holdout",
       "Write only the Python function signature (one line, no body): a function named assign_crew that takes rota (dict) and shift_id (int) and returns a dict.",
       "def assign_crew(rota: dict, shift_id: int) -> dict:"),
    _t("CON-206", "CON", "signature", 2, "holdout",
       "Write only the first line of a JavaScript function declaration (no body): a function named renderBadge that takes count and returns a string.",
       "function renderBadge(count) {"),
    _t("CON-207", "CON", "binding", 3, "holdout",
       "```javascript\n// notify.js\nexport function sendMail(to, text) { }\nexport function sendPing(to) { }\n\n// alerts.js — must deliver a full notification text to an address\nimport { ______ } from \"./notify.js\";\n\nexport function alert(to, text) {\n  return sendMail(to, text);\n}\n```\nWhich function name fills the blank?", "sendMail"),
    _t("CON-208", "CON", "shape", 2, "holdout",
       '// Contract: respondGone(res) must send status 410 with { "reason": "expired" }.\nWrite the single-line function body.',
       'res.status(410).json({ reason: "expired" });'),
]

# ---------------------------------------------------------------------------
# A3 - JSR: JavaScript reasoning
# ---------------------------------------------------------------------------
JSR_DEV = [
    _t("JSR-001", "JSR", "values", 1, "dev",
       "```javascript\nconst a = [1, 2, 3].map(x => x * 2);\n```\nWhat is the value of a?", "[2, 4, 6]",
       cf={"question": "```javascript\nconst a = [1, 2, 4].map(x => x * 2);\n```\nWhat is the value of a?", "gold": "[2, 4, 8]", "critical": "[1, 2, 4]"},
       critical="[1, 2, 3]"),
    _t("JSR-002", "JSR", "values", 1, "dev",
       "```javascript\nconst { a, ...rest } = { a: 1, b: 2, c: 3 };\n```\nWhat is the value of rest?", "{ b: 2, c: 3 }",
       cf={"question": "```javascript\nconst { b, ...rest } = { a: 1, b: 2, c: 3 };\n```\nWhat is the value of rest?", "gold": "{ a: 1, c: 3 }", "critical": "const { b, ...rest }"},
       critical="const { a, ...rest }"),
    _t("JSR-003", "JSR", "values", 2, "dev",
       "```javascript\nconst items = [{ p: 3 }, { p: 1 }, { p: 2 }];\nitems.sort((x, y) => x.p - y.p);\n```\nWhat is items[0].p?", "1",
       cf={"question": "```javascript\nconst items = [{ p: 9 }, { p: 1 }, { p: 2 }];\nitems.sort((x, y) => x.p - y.p);\n```\nWhat is items[0].p?", "gold": "1", "critical": "(x, y) => y.p - x.p"},
       critical="(x, y) => x.p - y.p"),
    _t("JSR-004", "JSR", "values", 2, "dev",
       "```javascript\nconst out = [];\nfor (const v of [1, 2, 3]) {\n  out.unshift(v);\n}\n```\nWhat is the value of out?", "[3, 2, 1]",
       cf={"question": "```javascript\nconst out = [];\nfor (const v of [1, 2, 5]) {\n  out.unshift(v);\n}\n```\nWhat is the value of out?", "gold": "[5, 2, 1]", "critical": "[1, 2, 5]"},
       critical="out.unshift(v)"),
    _t("JSR-005", "JSR", "values", 3, "dev",
       "```javascript\nconst base = { count: 1 };\nconst next = { ...base, count: base.count + 1, tag: \"x\" };\n```\nWhat is the value of next?", '{ count: 2, tag: "x" }',
       cf={"question": "```javascript\nconst base = { count: 4 };\nconst next = { ...base, count: base.count + 1, tag: \"x\" };\n```\nWhat is the value of next?", "gold": '{ count: 5, tag: "x" }', "critical": "{ count: 4 }"},
       critical="base.count + 1"),
    _t("JSR-006", "JSR", "async", 1, "dev",
       "```javascript\nconsole.log(\"A\");\nPromise.resolve().then(() => console.log(\"B\"));\nconsole.log(\"C\");\n```\nWhat is the logged order?", "A C B",
       cf={"question": "```javascript\nconsole.log(\"P\");\nPromise.resolve().then(() => console.log(\"Q\"));\nconsole.log(\"R\");\n```\nWhat is the logged order?", "gold": "P R Q", "critical": "console.log(\"P\")"},
       critical="Promise.resolve().then"),
    _t("JSR-007", "JSR", "async", 2, "dev",
       "```javascript\nasync function run() {\n  console.log(\"1\");\n  await Promise.resolve();\n  console.log(\"2\");\n}\nconsole.log(\"3\");\nrun();\nconsole.log(\"4\");\n```\nWhat is the logged order?", "3 1 4 2",
       cf={"question": "```javascript\nasync function run() {\n  console.log(\"5\");\n  await Promise.resolve();\n  console.log(\"6\");\n}\nconsole.log(\"7\");\nrun();\nconsole.log(\"8\");\n```\nWhat is the logged order?", "gold": "7 5 8 6", "critical": 'console.log("7")'},
       critical="await Promise.resolve()"),
    _t("JSR-008", "JSR", "async", 3, "dev",
       "```javascript\nconst p = Promise.resolve(10).then(v => v * 2).then(v => v + 1);\n```\nWhat value does p resolve to?", "21",
       cf={"question": "```javascript\nconst p = Promise.resolve(11).then(v => v * 2).then(v => v + 1);\n```\nWhat value does p resolve to?", "gold": "23", "critical": "resolve(11)"},
       critical="resolve(10)"),
    _t("JSR-009", "JSR", "web", 1, "dev",
       "```javascript\napp.get(\"/users\", (req, res) => res.json({ users: [] }));\n```\nWhich HTTP method does this route handle?", "GET",
       cf={"question": "```javascript\napp.post(\"/users\", (req, res) => res.json({ users: [] }));\n```\nWhich HTTP method does this route handle?", "gold": "POST", "critical": "app.post("},
       critical="app.get("),
    _t("JSR-010", "JSR", "web", 2, "dev",
       "```javascript\napp.post(\"/items\", (req, res) => {\n  const { name } = req.body;\n  res.status(201).json({ id: 1, name });\n});\n```\nWhich status code does a successful response use?", "201",
       cf={"question": "```javascript\napp.post(\"/items\", (req, res) => {\n  const { name } = req.body;\n  res.status(200).json({ id: 1, name });\n});\n```\nWhich status code does a successful response use?", "gold": "200", "critical": "res.status(200)"},
       critical="res.status(201)"),
    _t("JSR-011", "JSR", "web", 3, "dev",
       "```javascript\nfetch(\"/api/data\")\n  .then(r => r.json())\n  .then(d => console.log(d.items));\n```\nThe API returns `{ \"items\": [1, 2] }`. What is logged?", "[1, 2]",
       cf={"question": "```javascript\nfetch(\"/api/data\")\n  .then(r => r.json())\n  .then(d => console.log(d.items));\n```\nThe API returns `{ \"items\": [3, 8] }`. What is logged?", "gold": "[3, 8]", "critical": '{ "items": [3, 8] }'},
       critical="d.items"),
    _t("JSR-012", "JSR", "values", 2, "dev",
       "```javascript\nconst s = \"abc\";\nconst t = s.toUpperCase();\n```\nWhat is the value of s?", '"abc"',
       cf={"question": "```javascript\nconst s = \"xyz\";\nconst t = s.toUpperCase();\n```\nWhat is the value of s?", "gold": '"xyz"', "critical": 'const s = "xyz"'},
       critical="const t = s.toUpperCase()"),
]
JSR_VAL = [
    _t("JSR-101", "JSR", "values", 1, "val",
       "```javascript\nconst b = [3, 6, 9].filter(x => x > 4);\n```\nWhat is the value of b?", "[6, 9]"),
    _t("JSR-102", "JSR", "values", 2, "val",
       "```javascript\nconst { id, ...rest } = { id: 5, role: \"dev\", team: \"core\" };\n```\nWhat is the value of rest?", '{ role: "dev", team: "core" }'),
    _t("JSR-103", "JSR", "values", 2, "val",
       "```javascript\nconst vals = [5, 2, 8, 1];\nconst total = vals.reduce((acc, v) => acc + v, 0);\n```\nWhat is the value of total?", "16"),
    _t("JSR-104", "JSR", "async", 2, "val",
       "```javascript\nsetTimeout(() => console.log(\"late\"), 0);\nPromise.resolve().then(() => console.log(\"micro\"));\nconsole.log(\"sync\");\n```\nWhat is the logged order?", "sync micro late"),
    _t("JSR-105", "JSR", "async", 3, "val",
       "```javascript\nconst q = Promise.resolve(3).then(v => v * v).then(v => v - 1);\n```\nWhat value does q resolve to?", "8"),
    _t("JSR-106", "JSR", "web", 1, "val",
       "```javascript\napp.delete(\"/items/:id\", (req, res) => res.json({ gone: true }));\n```\nWhich HTTP method does this route handle?", "DELETE"),
    _t("JSR-107", "JSR", "web", 2, "val",
       "```javascript\napp.put(\"/items/:id\", (req, res) => {\n  res.status(204).end();\n});\n```\nWhich status code does a successful response use?", "204"),
    _t("JSR-108", "JSR", "values", 3, "val",
       "```javascript\nconst cfg = { retries: 2 };\nconst merged = { retries: 5, ...cfg };\n```\nWhat is the value of merged.retries?", "2"),
]
JSR_HOLD = [
    _t("JSR-201", "JSR", "values", 1, "holdout",
       "```javascript\nconst crew = [\"ann\", \"bo\"].map(n => n.toUpperCase());\n```\nWhat is the value of crew?", '["ANN", "BO"]'),
    _t("JSR-202", "JSR", "values", 2, "holdout",
       "```javascript\nconst { wage, ...others } = { wage: 20, zone: 3, night: true };\n```\nWhat is the value of others?", "{ zone: 3, night: true }"),
    _t("JSR-203", "JSR", "values", 2, "holdout",
       "```javascript\nconst fees = [4, 1, 3];\nconst sum = fees.reduce((acc, v) => acc + v, 10);\n```\nWhat is the value of sum?", "18"),
    _t("JSR-204", "JSR", "async", 2, "holdout",
       "```javascript\nconsole.log(\"s1\");\nqueueMicrotask(() => console.log(\"m1\"));\nsetTimeout(() => console.log(\"t1\"), 0);\nconsole.log(\"s2\");\n```\nWhat is the logged order?", "s1 s2 m1 t1"),
    _t("JSR-205", "JSR", "async", 3, "holdout",
       "```javascript\nconst job = Promise.resolve(6).then(v => v + v).then(v => v / 2);\n```\nWhat value does job resolve to?", "6"),
    _t("JSR-206", "JSR", "web", 1, "holdout",
       "```javascript\napp.patch(\"/shifts/:id\", (req, res) => res.json({ ok: true }));\n```\nWhich HTTP method does this route handle?", "PATCH"),
    _t("JSR-207", "JSR", "web", 2, "holdout",
       "```javascript\napp.post(\"/shifts\", (req, res) => {\n  res.status(202).json({ queued: true });\n});\n```\nWhich status code does a successful response use?", "202"),
    _t("JSR-208", "JSR", "values", 3, "holdout",
       "```javascript\nconst def = { rate: 10 };\nconst opts = { ...def, rate: def.rate * 2, cap: 99 };\n```\nWhat is the value of opts.rate?", "20"),
]

# ---------------------------------------------------------------------------
# A4 - XCOM: cross-component reasoning
# ---------------------------------------------------------------------------
XCOM_DEV = [
    _t("XCOM-001", "XCOM", "field", 1, "dev",
       "```python\n# storage.py\ndef get_user(user_id):\n    return {\"name\": \"Ann\", \"email\": \"a@x.io\"}\n\n# api.py\nfrom storage import get_user\n\ndef handler(user_id):\n    user = get_user(user_id)\n    return {\"userName\": user[______]}\n```\nWhich key fills the blank so the API returns the user's name?", '"name"',
       cf={"question": "```python\n# storage.py\ndef get_user(user_id):\n    return {\"fullname\": \"Ann\", \"email\": \"a@x.io\"}\n\n# api.py\nfrom storage import get_user\n\ndef handler(user_id):\n    user = get_user(user_id)\n    return {\"userName\": user[______]}\n```\nWhich key fills the blank so the API returns the user's name?", "gold": '"fullname"', "critical": '"fullname": "Ann"'},
       critical='{"name": "Ann", "email": "a@x.io"}'),
    _t("XCOM-002", "XCOM", "field", 1, "dev",
       "```javascript\n// api.js responds with: res.json({ ok: true, items: [1, 2] });\n// frontend.js\nconst res = await fetch(\"/api\");\nconst data = await res.json();\nconst list = data.______;\n```\nWhich property fills the blank?", "items",
       cf={"question": "```javascript\n// api.js responds with: res.json({ ok: true, rows: [1, 2] });\n// frontend.js\nconst res = await fetch(\"/api\");\nconst data = await res.json();\nconst list = data.______;\n```\nWhich property fills the blank?", "gold": "rows", "critical": "{ ok: true, rows: [1, 2] }"},
       critical="{ ok: true, items: [1, 2] }"),
    _t("XCOM-003", "XCOM", "rename", 2, "dev",
       "```python\n# db.py (UPDATED): records now use \"user_id\" instead of \"userid\".\n\n# api.py\ndef same_user(record, session):\n    return record[______] == session[\"user_id\"]\n```\nWhich key fills the blank so api.py works with the UPDATED db.py?", '"user_id"',
       cf={"question": "```python\n# db.py (UPDATED): records now use \"uid\" instead of \"userid\".\n\n# api.py\ndef same_user(record, session):\n    return record[______] == session[\"user_id\"]\n```\nWhich key fills the blank so api.py works with the UPDATED db.py?", "gold": '"uid"', "critical": '"uid" instead of "userid"'},
       critical='"user_id" instead of "userid"'),
    _t("XCOM-004", "XCOM", "binding", 2, "dev",
       "```javascript\n// storage.js\nexport function saveUser(user) { users.push(user); return user; }\n\n// route.js\nimport { saveUser } from \"./storage.js\";\napp.post(\"/users\", (req, res) => {\n  const user = req.body;\n  ______(user);\n  res.status(201).json(user);\n});\n```\nWhich function name fills the blank?", "saveUser",
       cf={"question": "```javascript\n// storage.js\nexport function persistUser(user) { users.push(user); return user; }\n\n// route.js\nimport { persistUser } from \"./storage.js\";\napp.post(\"/users\", (req, res) => {\n  const user = req.body;\n  ______(user);\n  res.status(201).json(user);\n});\n```\nWhich function name fills the blank?", "gold": "persistUser", "critical": "export function persistUser"},
       critical="export function saveUser"),
    _t("XCOM-005", "XCOM", "field", 3, "dev",
       "```javascript\n// frontend.js expects every error response to be: { \"error\": <string> }\n\n// route.js\napp.get(\"/users/:id\", (req, res) => {\n  const user = findUser(req.params.id);\n  if (!user) {\n    return res.status(404).json({ ______: \"not found\" });\n  }\n  res.json(user);\n});\n```\nWhich key fills the blank?", '"error"',
       cf={"question": "```javascript\n// frontend.js expects every error response to be: { \"err\": <string> }\n\n// route.js\napp.get(\"/users/:id\", (req, res) => {\n  const user = findUser(req.params.id);\n  if (!user) {\n    return res.status(404).json({ ______: \"not found\" });\n  }\n  res.json(user);\n});\n```\nWhich key fills the blank?", "gold": '"err"', "critical": '{ "err": <string> }'},
       critical='{ "error": <string> }'),
    _t("XCOM-006", "XCOM", "binding", 3, "dev",
       "```python\n# store.py\nclass Store:\n    def __init__(self):\n        self.items = {}\n    def set(self, key, value):\n        self.items[key] = value\n    def get(self, key):\n        return self.items.get(key)\n\n# service.py\nfrom store import Store\n\ndef upsert(store, key, value):\n    store.______(key, value)\n    return store.get(key)\n```\nWhich method name fills the blank?", "set",
       cf={"question": "```python\n# store.py\nclass Store:\n    def __init__(self):\n        self.items = {}\n    def assign(self, key, value):\n        self.items[key] = value\n    def get(self, key):\n        return self.items.get(key)\n\n# service.py\nfrom store import Store\n\ndef upsert(store, key, value):\n    store.______(key, value)\n    return store.get(key)\n```\nWhich method name fills the blank?", "gold": "assign", "critical": "def assign(self, key, value):"},
       critical="def set(self, key, value):"),
    _t("XCOM-007", "XCOM", "field", 2, "dev",
       "```javascript\n// api.js: res.json({ user: { id, name }, token });\n// App.jsx\nconst { user, token } = await fetchJSON(\"/login\");\nsetUser(______.name);\n```\nWhich identifier fills the blank?", "user",
       cf={"question": "```javascript\n// api.js: res.json({ account: { id, name }, token });\n// App.jsx\nconst { account, token } = await fetchJSON(\"/login\");\nsetUser(______.name);\n```\nWhich identifier fills the blank?", "gold": "account", "critical": "const { account, token }"},
       critical="const { user, token }"),
    _t("XCOM-008", "XCOM", "binding", 2, "dev",
       "```python\n# config.py\nDEFAULTS = {\"retries\": 3, \"timeout\": 5}\n\n# worker.py\nimport config\n\ndef retry_count():\n    return config.______[\"retries\"]\n```\nWhich name fills the blank?", "DEFAULTS",
       cf={"question": "```python\n# config.py\nSETTINGS = {\"retries\": 3, \"timeout\": 5}\n\n# worker.py\nimport config\n\ndef retry_count():\n    return config.______[\"retries\"]\n```\nWhich name fills the blank?", "gold": "SETTINGS", "critical": "SETTINGS = {"},
       critical="DEFAULTS = {"),
    _t("XCOM-009", "XCOM", "binding", 1, "dev",
       "```python\n# math_utils.py\ndef clamp(v, lo, hi): ...\n\n# app.py\nfrom math_utils import clamp\n\ndef normalize(x):\n    return ______(x, 0, 1)\n```\nWhich function name fills the blank?", "clamp",
       cf={"question": "```python\n# math_utils.py\ndef bound(v, lo, hi): ...\n\n# app.py\nfrom math_utils import bound\n\ndef normalize(x):\n    return ______(x, 0, 1)\n```\nWhich function name fills the blank?", "gold": "bound", "critical": "from math_utils import bound"},
       critical="from math_utils import clamp"),
    _t("XCOM-010", "XCOM", "binding", 3, "dev",
       "```javascript\n// api.js\nexport async function loadConfig() {\n  const r = await fetch(\"/config\");\n  return r.json();\n}\n\n// app.js\nimport { loadConfig } from \"./api.js\";\n\nasync function start() {\n  const config = ______ loadConfig();\n  console.log(config.mode);\n}\n```\nWhich keyword fills the blank?", "await",
       cf={"question": "```javascript\n// api.js\nexport async function loadSettings() {\n  const r = await fetch(\"/config\");\n  return r.json();\n}\n\n// app.js\nimport { loadSettings } from \"./api.js\";\n\nasync function start() {\n  const config = ______ loadSettings();\n  console.log(config.mode);\n}\n```\nWhich keyword fills the blank?", "gold": "await", "critical": "export async function loadSettings"},
       critical="export async function loadConfig"),
    _t("XCOM-011", "XCOM", "rename", 3, "dev",
       "```javascript\n// storage.js (UPDATED): getUser now returns { profile: { name } } instead of { name }.\n\n// route.js must send the profile's name:\napp.get(\"/users/:id\", (req, res) => {\n  const user = getUser(req.params.id);\n  res.json({ name: user.______.name });\n});\n```\nWhich property fills the blank?", "profile",
       cf={"question": "```javascript\n// storage.js (UPDATED): getUser now returns { record: { name } } instead of { name }.\n\n// route.js must send the record's name:\napp.get(\"/users/:id\", (req, res) => {\n  const user = getUser(req.params.id);\n  res.json({ name: user.______.name });\n});\n```\nWhich property fills the blank?", "gold": "record", "critical": "{ record: { name } }"},
       critical="{ profile: { name } }"),
    _t("XCOM-012", "XCOM", "binding", 3, "dev",
       "```python\n# fetcher.py\ndef get_json(url):\n    data = requests_get(url)\n    if data is None:\n        raise ValueError(\"bad url: \" + url)\n    return data\n\n# handler.py\nfrom fetcher import get_json\n\ndef safe_handler(url):\n    try:\n        return get_json(url)\n    except ______:\n        return {\"error\": \"fetch failed\"}\n```\nWhich exception type fills the blank?", "ValueError",
       cf={"question": "```python\n# fetcher.py\ndef get_json(url):\n    data = requests_get(url)\n    if data is None:\n        raise TypeError(\"bad url: \" + url)\n    return data\n\n# handler.py\nfrom fetcher import get_json\n\ndef safe_handler(url):\n    try:\n        return get_json(url)\n    except ______:\n        return {\"error\": \"fetch failed\"}\n```\nWhich exception type fills the blank?", "gold": "TypeError", "critical": "raise TypeError("},
       critical='raise ValueError('),
]
XCOM_VAL = [
    _t("XCOM-101", "XCOM", "field", 1, "val",
       "```python\n# inventory.py\ndef get_item(sku):\n    return {\"title\": \"Bolt\", \"qty\": 9}\n\n# web.py\nfrom inventory import get_item\n\ndef view(sku):\n    item = get_item(sku)\n    return {\"stock\": item[______]}\n```\nWhich key fills the blank so the API returns the quantity?", '"qty"'),
    _t("XCOM-102", "XCOM", "field", 1, "val",
       "```javascript\n// api.js responds with: res.json({ done: false, rows: [7, 8] });\n// grid.js\nconst payload = await fetchJSON(\"/rows\");\nconst shown = payload.______;\n```\nWhich property fills the blank?", "rows"),
    _t("XCOM-103", "XCOM", "rename", 2, "val",
       "```python\n# cache.py (UPDATED): keys now use \"ttl\" instead of \"expires\".\n\n# middleware.py\ndef is_fresh(entry):\n    return entry[______] > 0\n```\nWhich key fills the blank so middleware.py works with the UPDATED cache.py?", '"ttl"'),
    _t("XCOM-104", "XCOM", "binding", 2, "val",
       "```javascript\n// session.js\nexport function loadSession(token) { }\nexport function dropSession(token) { }\n\n// logout.js\nimport { ______ } from \"./session.js\";\n\nexport function signOut(token) {\n  return dropSession(token);\n}\n```\nWhich function name fills the blank?", "dropSession"),
    _t("XCOM-105", "XCOM", "field", 3, "val",
       "```javascript\n// client.js expects every failure payload to be: { \"reason\": <string> }\n\n// gateway.js\napp.post(\"/pay\", (req, res) => {\n  if (!req.body.amount) {\n    return res.status(400).json({ ______: \"amount required\" });\n  }\n  res.json({ paid: true });\n});\n```\nWhich key fills the blank?", '"reason"'),
    _t("XCOM-106", "XCOM", "binding", 3, "val",
       "```python\n# tank.py\nclass Tank:\n    def drain(self): ...\n    def fill(self, liters): ...\n\n# plant.py — must add water to the tank\ndef refill(tank):\n    tank.______(50)\n```\nWhich method name fills the blank?", "fill"),
    _t("XCOM-107", "XCOM", "field", 2, "val",
       "```javascript\n// api.js: res.json({ doc: { slug, body }, etag });\n// page.js\nconst { doc, etag } = await fetchJSON(\"/page\");\nrender(______.body);\n```\nWhich identifier fills the blank?", "doc"),
    _t("XCOM-108", "XCOM", "binding", 3, "val",
       "```python\n# retry.py\ndef with_retry(fn, attempts):\n    for _ in range(attempts):\n        try:\n            return fn()\n        except ConnectionError:\n            continue\n    raise TimeoutError(\"retries exhausted\")\n\n# caller.py\nfrom retry import with_retry\n\ndef call(fn):\n    try:\n        return with_retry(fn, 3)\n    except ______:\n        return None\n```\nWhich exception type fills the blank?", "TimeoutError"),
]
XCOM_HOLD = [
    _t("XCOM-201", "XCOM", "field", 1, "holdout",
       "```python\n# crew_store.py\ndef fetch_member(member_id):\n    return {\"wage\": 20, \"zone\": 3}\n\n# payroll.py\nfrom crew_store import fetch_member\n\ndef pay(member_id):\n    member = fetch_member(member_id)\n    return {\"amount\": member[______]}\n```\nWhich key fills the blank so payroll returns the wage?", '"wage"'),
    _t("XCOM-202", "XCOM", "field", 1, "holdout",
       "```javascript\n// roster-api.js responds with: res.json({ ready: true, shifts: [\"am\", \"pm\"] });\n// board.js\nconst payload = await fetchJSON(\"/shifts\");\nconst listed = payload.______;\n```\nWhich property fills the blank?", "shifts"),
    _t("XCOM-203", "XCOM", "rename", 2, "holdout",
       "```python\n# roster_db.py (UPDATED): records now use \"crew_id\" instead of \"cid\".\n\n# scheduler.py\ndef owns(record, session):\n    return record[______] == session[\"crew_id\"]\n```\nWhich key fills the blank so scheduler.py works with the UPDATED roster_db.py?", '"crew_id"'),
    _t("XCOM-204", "XCOM", "binding", 2, "holdout",
       "```javascript\n// shift_store.js\nexport function bookShift(crewId, slot) { }\nexport function cancelShift(crewId, slot) { }\n\n// planner.js — must reserve a slot for a crew member\nimport { ______ } from \"./shift_store.js\";\n\nexport function reserve(crewId, slot) {\n  return bookShift(crewId, slot);\n}\n```\nWhich function name fills the blank?", "bookShift"),
    _t("XCOM-205", "XCOM", "field", 3, "holdout",
       "```javascript\n// board.js expects every failure payload to be: { \"code\": <string> }\n\n// roster-api.js\napp.post(\"/shifts\", (req, res) => {\n  if (!req.body.slot) {\n    return res.status(400).json({ ______: \"slot_missing\" });\n  }\n  res.json({ booked: true });\n});\n```\nWhich key fills the blank?", '"code"'),
    _t("XCOM-206", "XCOM", "binding", 3, "holdout",
       "```python\n# silo.py\nclass Silo:\n    def dispense(self, kg): ...\n    def purge(self): ...\n\n# mill.py — must release grain from the silo\ndef release(silo):\n    silo.______(25)\n```\nWhich method name fills the blank?", "dispense"),
    _t("XCOM-207", "XCOM", "field", 2, "holdout",
       "```javascript\n// roster-api.js: res.json({ shift: { slot, lead }, token });\n// assign.js\nconst { shift, token } = await fetchJSON(\"/assign\");\nlabel(______.slot);\n```\nWhich identifier fills the blank?", "shift"),
    _t("XCOM-208", "XCOM", "binding", 3, "holdout",
       "```python\n# guard.py\ndef guarded(fn, budget):\n    for _ in range(budget):\n        try:\n            return fn()\n        except KeyError:\n            continue\n    raise RuntimeError(\"budget exhausted\")\n\n# shell.py\nfrom guard import guarded\n\ndef run(fn):\n    try:\n        return guarded(fn, 2)\n    except ______:\n        return -1\n```\nWhich exception type fills the blank?", "RuntimeError"),
]

TASKS = VAR_DEV + VAR_VAL + VAR_HOLD + CON_DEV + CON_VAL + CON_HOLD \
    + JSR_DEV + JSR_VAL + JSR_HOLD + XCOM_DEV + XCOM_VAL + XCOM_HOLD

PARTITIONS = ("dev", "val", "holdout")


def tasks_for(partition: str | None = None, category: str | None = None) -> list[dict]:
    out = TASKS
    if partition is not None:
        out = [t for t in out if t["partition"] == partition]
    if category is not None:
        out = [t for t in out if t["category"] == category]
    return out


def task_by_id(task_id: str) -> dict:
    for t in TASKS:
        if t["id"] == task_id:
            return t
    raise KeyError(task_id)


def sanity_check() -> None:
    ids = [t["id"] for t in TASKS]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate task ids")
    for t in TASKS:
        if t["category"] not in CATEGORIES:
            raise ValueError(f"bad category in {t['id']}")
        if t["partition"] not in PARTITIONS:
            raise ValueError(f"bad partition in {t['id']}")
        if not t["gold"] or not t["question"]:
            raise ValueError(f"empty gold/question in {t['id']}")
        if t["partition"] == "dev" and t.get("cf") is None:
            raise ValueError(f"dev task {t['id']} lacks a counterfactual variant")
    for cat in CATEGORIES:
        patchable = [t for t in tasks_for("dev", cat) if t.get("cf")]
        if len(patchable) < 10:
            raise ValueError(f"category {cat} has only {len(patchable)} patchable dev tasks")
        for cat in CATEGORIES:
            for part in PARTITIONS:
                n = len(tasks_for(part, cat))
                if n == 0:
                    raise ValueError(f"empty cell {cat}/{part}")


if __name__ == "__main__":
    sanity_check()
    from collections import Counter
    print(Counter((t["category"], t["partition"]) for t in TASKS))
    print("total tasks:", len(TASKS))
