"""Trusted reference persistence tests (no generated code)."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from storage import execute


class SqliteProjectManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "data.sqlite"

    def tearDown(self):
        self.temp.cleanup()

    def action(self, operation, **payload):
        return execute({"action": operation, "payload": payload}, self.database)

    def test_project_and_tasks_persist_across_connections(self):
        p = self.action("create_project", name="Web launch", description="First release")
        t = self.action("create_task", project_id=p["id"], title="Create dashboard")
        self.assertEqual(t["status"], "todo")
        view = self.action("overview")
        self.assertEqual(view["projects"][0]["name"], "Web launch")
        self.assertEqual(view["tasks"][0]["title"], "Create dashboard")

    def test_can_move_task_and_update_project(self):
        p = self.action("create_project", name="Backlog")
        t = self.action("create_task", project_id=p["id"], title="Write tests")
        changed = self.action("update_task", id=t["id"], status="done", priority="high")
        self.assertEqual((changed["status"], changed["priority"]), ("done", "high"))
        renamed = self.action("update_project", id=p["id"], name="Launch")
        self.assertEqual(renamed["name"], "Launch")

    def test_delete_project_cascades_all_tasks(self):
        p = self.action("create_project", name="Disposable")
        self.action("create_task", project_id=p["id"], title="One")
        self.action("delete_project", id=p["id"])
        self.assertEqual(self.action("overview"), {"projects": [], "tasks": []})

    def test_validation_rejects_invalid_payloads(self):
        with self.assertRaises(ValueError):
            self.action("create_project", name=" ")
        with self.assertRaises(ValueError):
            self.action("create_project", name="Unsafe", color="red")
        p = self.action("create_project", name="Safe")
        with self.assertRaises(ValueError):
            self.action("create_task", project_id=p["id"], title="Test", priority="critical")

    def test_delete_task_and_missing_id(self):
        p = self.action("create_project", name="Gamma")
        t = self.action("create_task", project_id=p["id"], title="Task")
        self.action("delete_task", id=t["id"])
        with self.assertRaises(LookupError):
            self.action("update_task", id=t["id"], status="done")


if __name__ == "__main__":
    unittest.main()
