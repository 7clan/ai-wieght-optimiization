"""Live HTTP integration smoke checks against the Dockerized real application."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request(base, path, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(base + path, data=data, method=method,
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=6) as result:
        return json.load(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:3000")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--check-persistence", action="store_true")
    args = parser.parse_args()
    for attempt in range(40):
        try:
            assert request(args.base, "/api/health")["ok"]
            break
        except (URLError, AssertionError):
            if attempt == 39:
                raise
            time.sleep(1)

    if args.check_persistence:
        saved = json.loads(args.state.read_text(encoding="utf-8"))
        after = request(args.base, "/api/overview")["data"]
        assert any(p["id"] == saved["project_id"] for p in after["projects"])
        assert any(t["id"] == saved["task_id"] and t["status"] == "done"
                   for t in after["tasks"])
        deleted = request(args.base, "/api/projects/" + saved["project_id"], "DELETE")
        assert deleted["data"]["deleted"] == saved["project_id"]
        assert not request(args.base, "/api/overview")["data"]["tasks"]
        print("Persistence across Docker restart and deletion/cascade: PASS")
        return

    index = urlopen(args.base + "/", timeout=6)
    assert index.status == 200 and "text/html" in index.headers["Content-Type"]
    project = request(args.base, "/api/projects", "POST",
                      {"name": "Live Demo", "description": "End-to-end integration test"})["data"]
    task = request(args.base, "/api/tasks", "POST",
                   {"project_id": project["id"], "title": "Ship Orbit",
                    "priority": "high", "due_date": "2026-12-15"})["data"]
    edited = request(args.base, "/api/tasks/" + task["id"], "PATCH", {"status": "done"})["data"]
    assert edited["status"] == "done" and edited["priority"] == "high"
    overview = request(args.base, "/api/overview")["data"]
    assert len(overview["projects"]) == 1 and len(overview["tasks"]) == 1
    try:
        request(args.base, "/api/tasks", "POST",
                {"project_id": project["id"], "title": "Bad", "priority": "wrong"})
        raise AssertionError("Expected HTTP 400 for invalid priority")
    except HTTPError as error:
        assert error.code == 400
    args.state.write_text(json.dumps({"project_id": project["id"],
                                       "task_id": task["id"]}), encoding="utf-8")
    print("HTTP API + React index + validation + project/task CRUD: PASS")


if __name__ == "__main__":
    main()
