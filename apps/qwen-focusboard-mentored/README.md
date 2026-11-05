# FocusBoard: Qwen0.5B model-assisted full-stack app

This app hosts the **exact** Session023 measured Qwen-generated slots inside a
separately authored functional React/Express/Python/SQLite framework. It is NOT
a fully independent 0.5B model-authored app. Only use it once Session023
reports an integrated holdout pass and the runtime Docker smoke test passes.

From the repository root in Codespaces:

```bash
docker compose -f apps/qwen-focusboard-mentored/compose.yaml up --build
```

Open the privately forwarded port **3000** in your Codespace. Do not expose it
publicly without a separate security review. The data persists in a Docker
named volume. Run with a private Codespaces port and restricted access only.

For an isolated test (no network, temporary data, no exposed port):

```bash
docker build -f apps/qwen-focusboard-mentored/Dockerfile -t qwen-focusboard-mentored .
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 128 --memory 1024m \
  --user 65534:65534 --tmpfs /tmp:rw,nosuid,size=64m \
  --tmpfs /data:rw,nosuid,size=64m,uid=65534,gid=65534,mode=0755 \
  qwen-focusboard-mentored node server/smoke.js
```

The real generated Python, Express routes and React TaskItem are included in
the image. The SQLite bridge, React state management, build and deployment
infrastructure are human/agent-authored trusted scaffolding.
