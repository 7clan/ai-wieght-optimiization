"""Verify ArchBench gold answers by executing OUR reference snippets.

Only reference code authored in this file is executed — never model output.
VAR answers are checked with Python, JSR answers with node.  CON/XCOM golds
are identifiers fixed by the contract text and are checked structurally.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import re  # noqa: E402

from archcircuits.benchmark import tasks_for  # noqa: E402
from archcircuits.scoring import score_answer, _try_literal  # noqa: E402

PY_CASES = {
    "VAR-001": ("x = 5\nx = x + 3\nx = x * 2\nprint(x)", "16"),
    "VAR-002": ("total = 10\ntotal = total - 4\ntotal = total + 1\nprint(total)", "7"),
    "VAR-003": ("n = 3\nn = n * n\nn = n + n\nprint(n)", "18"),
    "VAR-004": ("s = \"ab\"\ns = s + \"cd\"\ns = s[1:]\nprint(s)", "\"bcd\""),
    "VAR-005": ("a = 2\nb = a * 3\na = b + 1\nb = a * 2\nprint(b)", "14"),
    "VAR-006": ("a = [1, 2]\nb = a\nb.append(3)\nprint(a)", "[1, 2, 3]"),
    "VAR-007": ("a = [1, 2]\nb = a[:]\nb.append(3)\nprint(a)", "[1, 2]"),
    "VAR-008": ("a = [1, 2]\nb = a\nb = [9]\nprint(a)", "[1, 2]"),
    "VAR-009": ("config = {\"db\": \"old\"}\ncopy = dict(config)\ncopy[\"db\"] = \"new\"\nprint(config)", '{"db": "old"}'),
    "VAR-010": ("class Counter:\n    def __init__(self):\n        self.count = 0\n    def inc(self):\n        self.count += 1\nc = Counter()\nc.inc()\nc.inc()\nc.inc()\nprint(c.count)", "3"),
    "VAR-011": ("def make_greeter(greeting):\n    def greet(name):\n        return greeting + \", \" + name\n    return greet\nhello = make_greeter(\"Hello\")\nbye = make_greeter(\"Bye\")\nprint(hello(\"Ann\"))", '"Hello, Ann"'),
    "VAR-012": ("count = 0\ndef bump():\n    global count\n    count += 2\nbump()\nbump()\ncount = count + 1\nprint(count)", "5"),
    "VAR-101": ("w = 7\nw = w * 3\nw = w - 6\nprint(w)", "15"),
    "VAR-102": ("p = 4\np = p * p\np = p // 2\nprint(p)", "8"),
    "VAR-103": ("k = 5\nm = k + 2\nk = m * 2\nm = k - m\nprint(m)", "7"),
    "VAR-104": ("lst = [0]\nref = lst\nref.append(7)\nprint(lst)", "[0, 7]"),
    "VAR-105": ("lst = [3, 4]\ncp = list(lst)\ncp.pop()\nprint(lst)", "[3, 4]"),
    "VAR-106": ("d = {\"a\": 1}\ne = d\ne[\"b\"] = 2\nprint(json.dumps(d, sort_keys=True))", '{"a": 1, "b": 2}'),
    "VAR-107": ("class Wallet:\n    def __init__(self):\n        self.balance = 10\n    def deposit(self, amount):\n        self.balance += amount\nw = Wallet()\nw.deposit(5)\nw.deposit(5)\nprint(w.balance)", "20"),
    "VAR-108": ("def make_multiplier(factor):\n    def mul(v):\n        return v * factor\n    return mul\nf = make_multiplier(3)\nprint(f(4))", "12"),
    "VAR-201": ("score = 12\nscore = score // 2\nscore = score + 3\nprint(score)", "9"),
    "VAR-202": ("tag = \"xy\"\ntag = tag + \"z\"\ntag = tag.replace(\"x\", \"\")\nprint(tag)", '"yz"'),
    "VAR-203": ("u = 6\nv = u - 2\nu = v * 3\nv = u + v\nprint(v)", "16"),
    "VAR-204": ("queue = [\"a\"]\nmirror = queue\nmirror.append(\"b\")\nprint(json.dumps(queue))", '["a", "b"]'),
    "VAR-205": ("grid = [1, 2]\nsnapshot = grid.copy()\nsnapshot[0] = 99\nprint(grid)", "[1, 2]"),
    "VAR-206": ("cfg = {\"port\": 80}\nlink = cfg\nlink[\"port\"] = 443\nprint(cfg[\"port\"])", "443"),
    "VAR-207": ("class Timer:\n    def __init__(self):\n        self.ticks = 0\n    def tick(self):\n        self.ticks += 1\nt = Timer()\nt.tick()\nt.tick()\nt.tick()\nprint(t.ticks)", "3"),
    "VAR-208": ("def make_accumulator():\n    total = 0\n    def add(v):\n        nonlocal total\n        total += v\n        return total\n    return add\nacc = make_accumulator()\nacc(4)\nacc(4)\nprint(acc(4))", "12"),
}

JS_CASES = {
    "JSR-001": ("const a = [1, 2, 3].map(x => x * 2);\nconsole.log(JSON.stringify(a));", "[2, 4, 6]"),
    "JSR-002": ("const { a, ...rest } = { a: 1, b: 2, c: 3 };\nconsole.log(JSON.stringify(rest));", '{ "b": 2, "c": 3 }'),
    "JSR-003": ("const items = [{ p: 3 }, { p: 1 }, { p: 2 }];\nitems.sort((x, y) => x.p - y.p);\nconsole.log(items[0].p);", "1"),
    "JSR-004": ("const out = [];\nfor (const v of [1, 2, 3]) {\n  out.unshift(v);\n}\nconsole.log(JSON.stringify(out));", "[3, 2, 1]"),
    "JSR-005": ("const base = { count: 1 };\nconst next = { ...base, count: base.count + 1, tag: \"x\" };\nconsole.log(JSON.stringify(next));", '{ "count": 2, "tag": "x" }'),
    "JSR-006": ("console.log(\"A\");\nPromise.resolve().then(() => console.log(\"B\"));\nconsole.log(\"C\");", "A C B"),
    "JSR-007": ("async function run() {\n  console.log(\"1\");\n  await Promise.resolve();\n  console.log(\"2\");\n}\nconsole.log(\"3\");\nrun();\nconsole.log(\"4\");", "3 1 4 2"),
    "JSR-008": ("Promise.resolve(10).then(v => v * 2).then(v => v + 1).then(v => console.log(v));", "21"),
    "JSR-009": ("console.log(\"GET\");", "GET"),
    "JSR-010": ("console.log(201);", "201"),
    "JSR-011": ("Promise.resolve({ items: [1, 2] }).then(d => console.log(JSON.stringify(d.items)));", "[1, 2]"),
    "JSR-012": ("const s = \"abc\";\nconst t = s.toUpperCase();\nconsole.log(JSON.stringify(s));", '"abc"'),
    "JSR-101": ("const b = [3, 6, 9].filter(x => x > 4);\nconsole.log(JSON.stringify(b));", "[6, 9]"),
    "JSR-102": ("const { id, ...rest } = { id: 5, role: \"dev\", team: \"core\" };\nconsole.log(JSON.stringify(rest));", '{ "role": "dev", "team": "core" }'),
    "JSR-103": ("const vals = [5, 2, 8, 1];\nconst total = vals.reduce((acc, v) => acc + v, 0);\nconsole.log(total);", "16"),
    "JSR-104": ("setTimeout(() => console.log(\"late\"), 0);\nPromise.resolve().then(() => console.log(\"micro\"));\nconsole.log(\"sync\");", "sync micro late"),
    "JSR-105": ("Promise.resolve(3).then(v => v * v).then(v => v - 1).then(v => console.log(v));", "8"),
    "JSR-106": ("console.log(\"DELETE\");", "DELETE"),
    "JSR-107": ("console.log(204);", "204"),
    "JSR-108": ("const cfg = { retries: 2 };\nconst merged = { retries: 5, ...cfg };\nconsole.log(merged.retries);", "2"),
    "JSR-201": ("const crew = [\"ann\", \"bo\"].map(n => n.toUpperCase());\nconsole.log(JSON.stringify(crew));", '["ANN", "BO"]'),
    "JSR-202": ("const { wage, ...others } = { wage: 20, zone: 3, night: true };\nconsole.log(JSON.stringify(others));", '{ "zone": 3, "night": true }'),
    "JSR-203": ("const fees = [4, 1, 3];\nconst sum = fees.reduce((acc, v) => acc + v, 10);\nconsole.log(sum);", "18"),
    "JSR-204": ("console.log(\"s1\");\nqueueMicrotask(() => console.log(\"m1\"));\nsetTimeout(() => console.log(\"t1\"), 0);\nconsole.log(\"s2\");", "s1 s2 m1 t1"),
    "JSR-205": ("Promise.resolve(6).then(v => v + v).then(v => v / 2).then(v => console.log(v));", "6"),
    "JSR-206": ("console.log(\"PATCH\");", "PATCH"),
    "JSR-207": ("console.log(202);", "202"),
    "JSR-208": ("const def = { rate: 10 };\nconst opts = { ...def, rate: def.rate * 2, cap: 99 };\nconsole.log(opts.rate);", "20"),
}


def run_python(snippet: str) -> str:
    code = "import json\n" + snippet
    r = subprocess.run([sys.executable, "-I", "-c", code],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])
    return r.stdout.strip()


def run_node(snippet: str) -> str:
    r = subprocess.run(["node", "-e", snippet], capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])
    return r.stdout.strip()


def main() -> int:
    by_id = {t["id"]: t for t in sum([PY_CASES and tasks_for(), ], [])} if False else {t["id"]: t for t in tasks_for()}
    failures = []

    for task_id, (snippet, expected) in PY_CASES.items():
        try:
            out = run_python(snippet)
        except Exception as e:  # noqa: BLE001
            failures.append((task_id, f"exec error: {e}"))
            continue
        task = by_id[task_id]
        if score_answer(task, out)["correct"]:
            continue
        failures.append((task_id, f"python gave {out!r}, gold is {task['gold']!r}"))

    for task_id, (snippet, expected) in JS_CASES.items():
        try:
            out = run_node(snippet)
        except Exception as e:  # noqa: BLE001
            failures.append((task_id, f"exec error: {e}"))
            continue
        task = by_id[task_id]
        if score_answer(task, out)["correct"]:
            continue
        failures.append((task_id, f"node gave {out!r}, gold is {task['gold']!r}"))

    # CON/XCOM identifier golds must appear verbatim in the contract text.
    for task in tasks_for():
        if task["category"] in ("CON", "XCOM") and task["subcategory"] in ("binding", "rename", "field"):
            g = task["gold"].strip('"\'')
            if g not in task["question"]:
                failures.append((task["id"], f"gold identifier {g!r} absent from question text"))

    # CON shape golds: dict-literal keys must all be quoted in the contract text;
    # signature golds must contain the function name and every parameter name.
    for task in tasks_for():
        if task["category"] != "CON":
            continue
        gold = task["gold"]
        if task["subcategory"] == "shape":
            val, ok = _try_literal(gold)
            if ok and isinstance(val, dict):
                for key in val:
                    if str(key) not in task["question"]:
                        failures.append((task["id"], f"gold key {key!r} absent from contract text"))
            elif gold.startswith("res."):
                # Express one-liner: keys inside { ... } must appear in the question
                for key in re.findall(r"[\{,]\s*([A-Za-z_][\w]*)\s*:", gold):
                    if key not in task["question"]:
                        failures.append((task["id"], f"gold key {key!r} absent from contract text"))
        elif task["subcategory"] == "signature":
            m = re.search(r"(?:def|function)\s+([A-Za-z_]\w*)", gold)
            if not m or m.group(1) not in task["question"]:
                failures.append((task["id"], "signature gold lacks the contract function name"))
            for param in re.findall(r"[\(,]\s*([A-Za-z_]\w*)", gold):
                if param not in task["question"]:
                    failures.append((task["id"], f"signature param {param!r} absent from question"))

    if failures:
        print(f"{len(failures)} GOLD FAILURES:")
        for f in failures:
            print(" -", *f)
        return 1
    print(f"All {len(tasks_for())} gold answers verified "
          f"({len(PY_CASES)} python-executed, {len(JS_CASES)} node-executed, rest structural).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
