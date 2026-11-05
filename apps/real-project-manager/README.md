# Orbit — Real Project Manager (Full-Stack Reference)

**This is a fully runnable project-manager reference app, not model-generated
output.** It provides a real target for the Qwen2.5-Coder-0.5B autonomous
full-stack generation experiment. We must not attribute this trusted reference
implementation or its tests to the small model.

### What it does

- Add and delete projects, assign a project color and description.
- Add tasks, set priority and due date, change status between To do,
  In progress and Completed, search tasks, and delete them.
- View per-project or all-project task counts and completion percentage.
- Save all records in SQLite. Data persists across application restarts.
- Run a real React frontend, Express API and Python database bridge.

### Run in Docker

```bash
docker compose up --build
```

Open **http://localhost:3000**. The `project_manager_data` named volume
contains the database, so rebuilding/restarting does not reset records.

### Run locally

Requires Node.js 22+ and Python 3.11+:

```bash
npm install
npm run build
PROJECT_DB_PATH=./data/project-manager.sqlite npm start
```

Open **http://localhost:3000**. On Windows PowerShell, set the database
environment variable using `$env:PROJECT_DB_PATH` before starting.

### API

| Method | Endpoint | Action |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET | `/api/overview` | Projects and tasks |
| POST | `/api/projects` | Create project |
| PATCH | `/api/projects/:id` | Update project |
| DELETE | `/api/projects/:id` | Delete project and tasks |
| POST | `/api/tasks` | Create task |
| PATCH | `/api/tasks/:id` | Update task |
| DELETE | `/api/tasks/:id` | Delete task |

Run `npm run test:python` for database tests. CI also builds the Docker
image, tests the API and verifies that data persists after restarting the
container.

### Scope and safety

This is a **prototype**, not a production SaaS. It does not include
authentication, authorization, multi-user isolation, backup management,
rate limiting or a security audit. Do not put personal or sensitive data
in a publicly exposed instance. In a GitHub Codespace, keep forwarded port
visibility **private**.

### Research interpretation

The reference app is built by the coding assistant as infrastructure for
the experiment. A later independent track will ask the untouched 0.5B model
to produce its own app files, run this feature checklist without privileged
source access, and compare test results. A reference app passing all tests
does **not** establish that Qwen0.5B can build a full-stack app.
