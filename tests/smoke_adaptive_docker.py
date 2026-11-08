"""Opt-in real Docker smoke: safe, author-controlled sample programs only.

Run on a Docker-capable Linux host, e.g. the branch-specific GitHub workflow.
Never run untrusted generated code outside the DockerSandbox.
"""

from adaptive_agent import Task
from adaptive_agent.docker_sandbox import DockerSandbox, PublicFixture, require_docker


def main() -> None:
    require_docker()
    py = Task("py-smoke", "Implement add(a, b)", ("returns arithmetic sum",))
    js = Task("js-smoke", "Implement add(a, b)", ("returns arithmetic sum",))
    sandbox = DockerSandbox({
        py.task_id: PublicFixture("python", (
            "import sys\nsys.path.insert(0, '/app')\n"
            "from solution import add\n"
            "assert add(2, 3) == 5\nassert add(-8, 3) == -5\n"
        )),
        js.task_id: PublicFixture("javascript", (
            "const assert = require('node:assert/strict');\n"
            "const {add} = require('/app/solution.cjs');\n"
            "assert.equal(add(2, 3), 5);\nassert.equal(add(-8, 3), -5);\n"
        )),
    })
    good_py = sandbox.evaluate(py, {"solution.py": "def add(a, b):\n    return a + b\n"})
    bad_py = sandbox.evaluate(py, {"solution.py": "def add(a, b):\n    return a - b\n"})
    good_js = sandbox.evaluate(js, {"solution.cjs": "module.exports.add = (a, b) => a + b;\n"})
    bad_js = sandbox.evaluate(js, {"solution.cjs": "module.exports.add = (a, b) => a - b;\n"})
    assert good_py.passed, f"Python good fixture failed: {good_py.feedback}"
    assert good_js.passed, f"JavaScript good fixture failed: {good_js.feedback}"
    assert not bad_py.passed, "Incorrect Python was accepted"
    assert not bad_js.passed, "Incorrect JS was accepted"
    print("Docker sandbox smoke passed: correct Python and JS accepted; wrong versions rejected")


if __name__ == "__main__":
    main()
