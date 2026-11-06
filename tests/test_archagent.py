"""archagent protocol tests: the evaluator must accept correct modules and
reject broken ones, so the development loop has valid signal.

The reference modules here are TRUSTED-SCAFFOLD fixtures used ONLY to
validate the worker; they are never shown to the model and never become
part of the application.  Model-generated code is not executed by these
tests.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from archagent import contracts  # noqa: E402
from archagent.runner import (evaluate_module, score_stage_a,  # noqa: E402
                              _post_process, splice, fim_window)

NODE_PATH = os.environ.get("ARCHAGENT_NODE_PATH",
                           "/home/z/my-project/evalenv/node_modules")

REF_LOGIC = '''
def summarize_project(payload):
    tasks = payload.get("tasks", [])
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("status") == "done")
    by_priority = {"low": 0, "medium": 0, "high": 0}
    by_status = {"todo": 0, "doing": 0, "done": 0}
    for t in tasks:
        p = t.get("priority")
        if p in by_priority:
            by_priority[p] += 1
        s = t.get("status")
        if s in by_status:
            by_status[s] += 1
    percent = round(100 * done / total) if total else 0
    return {"total": total, "done": done, "remaining": total - done,
            "percent": percent, "by_priority": by_priority,
            "by_status": by_status}
'''

REF_STORE = '''
const fs = require('node:fs');
function createStore(filePath) {
  let projects = [];
  let tasks = [];
  let pnext = 1;
  let tnext = 1;
  if (fs.existsSync(filePath)) {
    const raw = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    projects = raw.projects || [];
    tasks = raw.tasks || [];
    for (const p of projects) {
      const n = parseInt(String(p.id).slice(1), 10);
      if (n >= pnext) pnext = n + 1;
    }
    for (const t of tasks) {
      const n = parseInt(String(t.id).slice(1), 10);
      if (n >= tnext) tnext = n + 1;
    }
  }
  function persist() {
    fs.writeFileSync(filePath, JSON.stringify({projects, tasks}));
  }
  function validName(v) { return typeof v === 'string' && v.length > 0; }
  function findProject(id) {
    const p = projects.find(x => x.id === String(id));
    if (!p) throw Error('project not found: ' + id);
    return p;
  }
  function findTask(id) {
    const t = tasks.find(x => x.id === String(id));
    if (!t) throw Error('task not found: ' + id);
    return t;
  }
  return {
    listProjects() { return projects.map(p => ({...p})); },
    createProject(body) {
      if (!body || !validName(body.name)) throw Error('invalid name');
      const p = {id: 'p' + (pnext++), name: body.name,
                 createdAt: '2026-11-07'};
      projects.push(p); persist();
      return {...p};
    },
    updateProject(id, body) {
      const p = findProject(id);
      if (body && body.name !== undefined && !validName(body.name))
        throw Error('invalid name');
      if (body && body.name !== undefined) p.name = body.name;
      persist();
      return {...p};
    },
    deleteProject(id) {
      findProject(id);
      projects = projects.filter(x => x.id !== String(id));
      tasks = tasks.filter(t => t.projectId !== String(id));
      persist();
      return true;
    },
    listTasks(filter) {
      filter = filter || {};
      let out = tasks;
      if (filter.projectId !== undefined && filter.projectId !== null)
        out = out.filter(t => t.projectId === String(filter.projectId));
      if (filter.status !== undefined && filter.status !== null)
        out = out.filter(t => t.status === filter.status);
      if (filter.q !== undefined && filter.q !== null && filter.q !== '')
        out = out.filter(t => t.title.toLowerCase()
                         .includes(String(filter.q).toLowerCase()));
      return out.map(t => ({...t}));
    },
    createTask(body) {
      if (!body) throw Error('invalid task');
      findProject(body.projectId);
      if (!validName(body.title)) throw Error('invalid title');
      const priority = body.priority === undefined ? 'medium' : body.priority;
      const status = body.status === undefined ? 'todo' : body.status;
      if (!['low', 'medium', 'high'].includes(priority))
        throw Error('invalid priority');
      if (!['todo', 'doing', 'done'].includes(status))
        throw Error('invalid status');
      const t = {id: 't' + (tnext++), projectId: String(body.projectId),
                 title: body.title, priority, status,
                 createdAt: '2026-11-07'};
      tasks.push(t); persist();
      return {...t};
    },
    updateTask(id, body) {
      const t = findTask(id);
      if (body && body.title !== undefined && !validName(body.title))
        throw Error('invalid title');
      if (body && body.priority !== undefined &&
          !['low', 'medium', 'high'].includes(body.priority))
        throw Error('invalid priority');
      if (body && body.status !== undefined &&
          !['todo', 'doing', 'done'].includes(body.status))
        throw Error('invalid status');
      if (body && body.title !== undefined) t.title = body.title;
      if (body && body.priority !== undefined) t.priority = body.priority;
      if (body && body.status !== undefined) t.status = body.status;
      persist();
      return {...t};
    },
    deleteTask(id) {
      findTask(id);
      tasks = tasks.filter(x => x.id !== String(id));
      persist();
      return true;
    },
  };
}
module.exports = createStore;
'''

REF_API = '''
const express = require('express');
function createApi(app, store, processor) {
  app.use(express.json());
  app.get('/api/health', (req, res) => res.status(200).json({ok: true}));
  app.get('/api/projects', (req, res) =>
    res.status(200).json({projects: store.listProjects()}));
  app.post('/api/projects', (req, res) => {
    try {
      const project = store.createProject(req.body);
      res.status(201).json({project});
    } catch (e) { res.status(400).json({error: e.message}); }
  });
  app.put('/api/projects/:id', (req, res) => {
    try {
      const project = store.updateProject(req.params.id, req.body);
      res.status(200).json({project});
    } catch (e) {
      if (String(e.message).includes('not found'))
        res.status(404).json({error: e.message});
      else res.status(400).json({error: e.message});
    }
  });
  app.delete('/api/projects/:id', (req, res) => {
    try {
      store.deleteProject(req.params.id);
      res.status(200).json({deleted: true});
    } catch (e) {
      if (String(e.message).includes('not found'))
        res.status(404).json({error: e.message});
      else res.status(400).json({error: e.message});
    }
  });
  app.get('/api/tasks', (req, res) => {
    const filter = {};
    if (req.query.projectId !== undefined) filter.projectId = req.query.projectId;
    if (req.query.status !== undefined) filter.status = req.query.status;
    if (req.query.q !== undefined) filter.q = req.query.q;
    res.status(200).json({tasks: store.listTasks(filter)});
  });
  app.post('/api/tasks', (req, res) => {
    try {
      const task = store.createTask(req.body);
      res.status(201).json({task});
    } catch (e) { res.status(400).json({error: e.message}); }
  });
  app.put('/api/tasks/:id', (req, res) => {
    try {
      const task = store.updateTask(req.params.id, req.body);
      res.status(200).json({task});
    } catch (e) {
      if (String(e.message).includes('not found'))
        res.status(404).json({error: e.message});
      else res.status(400).json({error: e.message});
    }
  });
  app.delete('/api/tasks/:id', (req, res) => {
    try {
      store.deleteTask(req.params.id);
      res.status(200).json({deleted: true});
    } catch (e) {
      if (String(e.message).includes('not found'))
        res.status(404).json({error: e.message});
      else res.status(400).json({error: e.message});
    }
  });
  app.get('/api/projects/:id/progress', (req, res) => {
    try {
      const project = store.listProjects().find(
        p => p.id === req.params.id);
      if (!project) throw Error('project not found: ' + req.params.id);
      const tasks = store.listTasks({projectId: req.params.id});
      res.status(200).json(processor({project, tasks}));
    } catch (e) {
      if (String(e.message).includes('not found'))
        res.status(404).json({error: e.message});
      else res.status(400).json({error: e.message});
    }
  });
}
module.exports = createApi;
'''

REF_CSS = '''const css = `
.app { display:flex; gap:16px; min-height:100vh; }
.sidebar { width:240px; padding:12px; }
.project-btn { display:block; width:100%; text-align:left; padding:8px; }
.task-row { display:flex; align-items:center; gap:8px; padding:8px; }
.priority-high { color:#b00; }
.priority-medium { color:#980; }
.priority-low { color:#080; }
.progress { background:#eee; border-radius:6px; padding:6px; }
.progress-fill { background:#2a2; height:8px; border-radius:4px; }
.filter-all, .filter-todo, .filter-doing, .filter-done { padding:4px 10px; }
.search { padding:6px; width:200px; }
.offline-badge { background:#c33; color:#fff; padding:4px 8px; }
.add-form { display:flex; gap:8px; }
@media (max-width: 720px) { .app { flex-direction:column; } .sidebar { width:auto; } }
`;
module.exports = css;
'''


def _worker_available() -> bool:
    return Path(NODE_PATH).is_dir()


class TestContractFrozen(unittest.TestCase):
    def test_fingerprint_stable(self):
        self.assertEqual(contracts.fingerprint(),
                         "c39769cd5e046b28ddf4ea329a2b8dd8168125924161e10e73e911cbc117ba9b")

    def test_holdout_disjoint_from_public(self):
        self.assertNotEqual(contracts.LOGIC_PUBLIC, contracts.LOGIC_HOLDOUT)
        self.assertNotEqual(contracts.STORE_SCENARIO_PUBLIC,
                            contracts.STORE_SCENARIO_HOLDOUT)


@unittest.skipUnless(_worker_available(), "evalenv node_modules missing")
class TestEvaluatorAcceptsReferences(unittest.TestCase):

    def test_logic_reference_passes(self):
        r = evaluate_module("logic", REF_LOGIC)
        self.assertTrue(r["passed"], r.get("failures"))

    def test_store_reference_passes(self):
        r = evaluate_module("store", REF_STORE)
        self.assertTrue(r["passed"], r.get("failures"))

    def test_api_reference_passes_with_store(self):
        r = evaluate_module("api", REF_API, store_source=REF_STORE)
        self.assertTrue(r["passed"], r.get("failures"))

    def test_api_reference_with_python_bridge(self):
        r = evaluate_module("api", REF_API, store_source=REF_STORE,
                            logic_source=REF_LOGIC)
        self.assertTrue(r["passed"], r.get("failures"))

    def test_css_reference_passes(self):
        r = evaluate_module("css", REF_CSS)
        self.assertTrue(r["passed"], r.get("failures"))


@unittest.skipUnless(_worker_available(), "evalenv node_modules missing")
class TestEvaluatorUiReference(unittest.TestCase):
    def test_ui_reference_passes(self):
        src = (ROOT / "tests" / "fixtures" / "ref_ui.jsx").read_text()
        r = evaluate_module("ui", src, timeout=60)
        self.assertTrue(r["passed"], r.get("failures"))


@unittest.skipUnless(_worker_available(), "evalenv node_modules missing")
class TestEvaluatorRejectsBroken(unittest.TestCase):

    def test_store_const_bug_detected(self):
        bad = REF_STORE.replace("let projects = []", "const projects = []")
        r = evaluate_module("store", bad)
        self.assertFalse(r["passed"])

    def test_store_missing_persistence_detected(self):
        bad = REF_STORE.replace("fs.writeFileSync(filePath, JSON.stringify({projects, tasks}));",
                                ";")
        r = evaluate_module("store", bad)
        self.assertFalse(r["passed"])

    def test_api_wrong_status_detected(self):
        bad = REF_API.replace("res.status(201).json({project})",
                              "res.status(200).json({project})")
        r = evaluate_module("api", bad, store_source=REF_STORE)
        self.assertFalse(r["passed"])

    def test_logic_wrong_percent_detected(self):
        bad = REF_LOGIC.replace("round(100 * done / total) if total else 0",
                                "100 if total else 0")
        r = evaluate_module("logic", bad)
        self.assertFalse(r["passed"])


class TestPromptProcessing(unittest.TestCase):
    def test_post_process_anchored_completion(self):
        # anchored semantics: input is the completion AFTER the signature
        raw = "Here is the code:\n```js\n  let state = [];\n  return { list: () => state };\n}\nmodule.exports = createStore;\n```\nThanks!"
        out = _post_process("store", raw)
        self.assertTrue(out.startswith("const fs = require('node:fs');\nfunction createStore(filePath) {"))
        self.assertIn("let state", out)
        self.assertNotIn("Thanks", out)
        self.assertNotIn("```", out)
        # trailing prose after the last brace is cut
        raw2 = "  let a = 1;\n  return {};\n}\n\nSome explanation prose."
        out2 = _post_process("store", raw2)
        self.assertNotIn("explanation", out2)
        self.assertTrue(out2.rstrip().endswith("}"))

    def test_post_process_css_closes_template(self):
        out = _post_process("css", ".app { display:flex; }\n.app {")  # unclosed
        self.assertTrue(out.startswith("const css = `"))
        self.assertIn("module.exports = css;", out)

    def test_post_process_logic_keeps_body(self):
        out = _post_process("logic", '  total = len(payload["tasks"])\n  return {"total": total}\n\nProse after.')
        self.assertTrue(out.startswith("def summarize_project(payload):"))
        self.assertNotIn("Prose", out)

    def test_fim_window_and_splice(self):
        src = "\n".join(f"line{i}" for i in range(1, 21))
        prefix, suffix, lo = fim_window(src, 10)  # anchor at line 10
        self.assertTrue(prefix.endswith("line3\n"))   # gap starts line 4
        self.assertTrue(suffix.startswith("line18"))  # gap ends line 17
        spliced = splice(src, "REPLACED", lo, lo + 14)
        self.assertIn("REPLACED", spliced)
        self.assertIn("line20", spliced)
        self.assertIn("line1", spliced)
        self.assertNotIn("line10\n", spliced)

    def test_stage_a_scoring(self):
        good = json.dumps({
            "components": ["project list", "task list", "add project form",
                           "add task form", "filter controls",
                           "search input", "progress display"],
            "entities": ["project", "task"],
            "routes": ["GET /api/projects", "POST /api/projects",
                       "PUT /api/projects/:id", "DELETE /api/projects/:id",
                       "GET /api/tasks", "POST /api/tasks",
                       "PUT /api/tasks/:id", "DELETE /api/tasks/:id",
                       "GET /api/health",
                       "GET /api/projects/:id/progress"],
            "state_transitions": ["todo -> doing", "doing -> done",
                                  "todo -> done"],
            "dependencies": ["express", "react"],
        })
        scored = score_stage_a(good)
        self.assertTrue(scored["valid_json"])
        for k, v in scored["scores"].items():
            self.assertGreaterEqual(v, 0.9, k)
        bad = score_stage_a("not json at all")
        self.assertFalse(bad["valid_json"])


class TestRepairMemory(unittest.TestCase):
    def test_classify_const_bug(self):
        from archagent.repair_memory import classify
        principle, category = classify(
            "threw Assignment to constant variable")
        self.assertEqual(category, "variable_tracking")
        self.assertIn("const", principle)

    def test_record_and_retrieve(self):
        import tempfile
        from archagent.repair_memory import RepairMemory, record_repair
        with tempfile.TemporaryDirectory() as tmp:
            mem = RepairMemory(tmp)
            mem.add(record_repair(
                role="store", requirement="persist",
                failed_source="const x = 1;\nx = 2;",
                failure_detail="Assignment to constant variable",
                repaired_source="let x = 1;\nx = 2;",
                corrected_behavior="checks 3/3"))
            recs = mem.all()
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0]["category"], "variable_tracking")
            block = mem.prompt_block("store",
                                     "Assignment to constant variable")
            self.assertIn("Previously verified correction", block)


class TestModelEnv(unittest.TestCase):
    def test_no_hardcoded_model_default(self):
        from archagent import model
        saved = os.environ.pop("ARCHAGENT_MODEL_DIR", None)
        try:
            with self.assertRaises(RuntimeError):
                model.resolve_model_dir()
        finally:
            if saved is not None:
                os.environ["ARCHAGENT_MODEL_DIR"] = saved
        src = Path(model.__file__).read_text()
        self.assertNotIn("/home/z/models", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
