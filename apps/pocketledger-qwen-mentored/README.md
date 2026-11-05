# PocketLedger: Qwen + teacher corrections

**Full-stack application. Not Qwen-only.** The Python calculation and CSS are
exact model-generated source from Session028. An agent teacher rewrote Node JSON
storage, Express routes and the React client after inspecting Qwen's failures.
The adapter files, build command and Python-to-Express bridge are trusted tools.

Session029 verifies full CRUD persistence, API envelopes, Python aggregation,
and server-rendered React plus event/fetch source wiring using isolated Docker.
It **does not** prove a real browser click path or production security.

## Try the app in your own Codespace

Requires Node.js 22+ and Python 3.11+. In this directory:

```bash
npm install
npm start
```

Open port **3000** using Codespaces' **Ports** tab (keep private).
Try adding an expense, reloading the page, checking category totals, deleting
it, and reloading again.

To run the API smoke test from another terminal:

```bash
curl http://localhost:3000/api/expenses
curl http://localhost:3000/api/summary
```

This is a user-operated development build. Generated app source was *not*
executed outside restricted Docker by the experiment runners. Review it
before exposing any port. Never assume a Codespaces URL is a public deployment.
