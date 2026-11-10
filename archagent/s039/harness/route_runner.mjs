// Trusted Session-039 GET/POST route contract evaluator. Executes only
// inside the Docker-only runner, never on the host with generated source
// code (the optional S039_* path environment variables exist solely so the
// trusted harness itself can be smoke-tested outside Docker with trusted
// control fixtures; the Docker invocation never sets them and gets the
// hardcoded container defaults). Stages a fresh Prisma+SQLite fixture,
// redirects the candidate's database import to the trusted provider,
// invokes the exported Next.js style GET/POST handler functions with
// standard Request objects and checks the frozen oracle cases. POST cases
// each start from a freshly reseeded fixture so per-case persistence
// deltas stay well defined. Emits exactly one machine-readable verdict
// line; any failure is fail-closed.
import { execFile } from 'node:child_process';
import { copyFile, mkdir, readFile } from 'node:fs/promises';
import { registerHooks } from 'node:module';
import { pathToFileURL } from 'node:url';
import { promisify } from 'node:util';

const run = promisify(execFile);
const WORK = process.env.S039_WORK ?? '/work';
const HARNESS = process.env.S039_HARNESS ?? '/harness';
const CANDIDATE = process.env.S039_CANDIDATE ?? '/candidate/output.ts';
const MARK = 'S039-RESULT ';
// Bind the real stdout write before any candidate code can monkey-patch
// process.stdout.write to suppress the genuine verdict or spoof a fake one.
// Candidate-written extra marker lines fail closed upstream as
// NO_UNAMBIGUOUS_VERDICT.
const stdoutWrite = process.stdout.write.bind(process.stdout);
const emit = (record) => stdoutWrite(MARK + JSON.stringify(record) + '\n');

const fail = (name) => {
  emit({ pass: false, checks: [{ name, passed: false }] });
  process.exitCode = 1;
};

const PROBE_TIMEOUT_MS = 10_000;
const withTimeout = (promise) => Promise.race([
  promise,
  new Promise((resolve) => setTimeout(() => resolve(null), PROBE_TIMEOUT_MS)),
]);

async function prismaStep(args) {
  await run('prisma', args, {
    cwd: WORK,
    env: {
      ...process.env,
      PRISMA_HIDE_UPDATE_MESSAGE: '1',
      PRISMA_SKIP_POSTINSTALL_GENERATE: '1',
    },
  });
}

try {
  const spec = JSON.parse(await readFile(`${HARNESS}/task.json`, 'utf8'));
  const isGet = spec.skill === 'api-get-filter';
  const isPost = spec.skill === 'api-post-validation';
  if (!isGet && !isPost) {
    fail('trusted-fixture-invalid-skill');
  } else if (
    typeof spec.route_path !== 'string' || !spec.route_path.startsWith('/api/') ||
    !spec.entities || typeof spec.entities.child_client !== 'string' ||
    !Array.isArray(spec.cases) || spec.cases.length === 0 ||
    (isGet && typeof spec.envelope_key !== 'string') ||
    !Array.isArray(spec.db_alias_specifiers) || spec.db_alias_specifiers.length === 0
  ) {
    fail('trusted-fixture-invalid');
  } else {
    // 1. Stage the trusted Prisma fixture inside the writable workspace.
    await mkdir(`${WORK}/lib`, { recursive: true });
    await copyFile(`${HARNESS}/schema.prisma`, `${WORK}/schema.prisma`);
    await copyFile(`${HARNESS}/db.ts`, `${WORK}/lib/db.ts`);
    await copyFile(`${HARNESS}/fixture.mjs`, `${WORK}/fixture.mjs`);
    await copyFile(`${HARNESS}/seed.mjs`, `${WORK}/seed.mjs`);
    await prismaStep(['db', 'push', '--schema', `${WORK}/schema.prisma`,
                      '--skip-generate', '--accept-data-loss']);
    await prismaStep(['generate', '--schema', `${WORK}/schema.prisma`]);
    await run('node', [`${WORK}/seed.mjs`], { cwd: WORK });

    // 2. Redirect only the conventional database import specifiers of the
    //    candidate to the trusted provider; every other specifier resolves
    //    normally (and fails closed if the candidate imports anything the
    //    pinned image does not provide). Candidate bytes are never edited.
    const dbAliases = new Set(spec.db_alias_specifiers);
    const dbUrl = pathToFileURL(`${WORK}/lib/db.ts`).href;
    registerHooks({
      resolve(specifier, context, nextResolve) {
        if (dbAliases.has(specifier)) {
          return { url: dbUrl, shortCircuit: true };
        }
        return nextResolve(specifier, context);
      },
    });

    // 3. Import the model-generated candidate exactly as staged, read-only.
    const mod = await import(pathToFileURL(CANDIDATE).href);
    const handlerName = isGet ? 'GET' : 'POST';
    const handler = mod[handlerName];
    const checks = [];
    if (typeof handler !== 'function') {
      checks.push({ name: `export-${handlerName}-present`, passed: false });
    } else {
      checks.push({ name: `export-${handlerName}-present`, passed: true });

      // The trusted fixture module and the candidate share one database
      // instance through the redirected provider module.
      const { db } = await import(dbUrl);
      const { seedFixture } = await import(pathToFileURL(`${WORK}/fixture.mjs`).href);
      const childModel = db[spec.entities.child_client];
      if (!childModel) {
        checks.push({ name: 'trusted-db-model-present', passed: false });
      } else {
        checks.push({ name: 'trusted-db-model-present', passed: true });
        const base = new URL(spec.route_path, 'http://127.0.0.1:3000');

        if (isGet) {
          for (const c of spec.cases) {
            const url = new URL(base);
            for (const [key, value] of Object.entries(c.params ?? {})) {
              url.searchParams.set(key, String(value));
            }
            let passed = false;
            const res = await withTimeout(handler(new Request(url)));
            if (res && res.status === c.expected_status) {
              try {
                const body = await withTimeout(res.json());
                const rows = body?.[spec.envelope_key];
                const titles = Array.isArray(rows)
                  ? rows.map((row) => row?.[spec.label_field])
                  : null;
                passed = Array.isArray(rows)
                  && JSON.stringify(titles) === JSON.stringify(c.expected_titles)
                  && body?.total === c.expected_total;
              } catch (_) { /* fail closed */ }
            }
            checks.push({ name: String(c.name).slice(0, 80), passed });
          }
        } else {
          for (const c of spec.cases) {
            // Each POST case starts from the pristine frozen fixture so the
            // per-case persistence deltas of the frozen plan stay exact.
            let reseeded = false;
            try {
              await withTimeout(seedFixture(db));
              reseeded = true;
            } catch (_) { /* fail closed below */ }
            let passed = false;
            if (reseeded) {
              let before = null;
              try {
                before = await withTimeout(childModel.count());
              } catch (_) { /* fail closed below */ }
              if (typeof before === 'number') {
                const res = await withTimeout(handler(new Request(base, {
                  method: 'POST',
                  headers: { 'content-type': 'application/json' },
                  body: JSON.stringify(c.body ?? {}),
                })));
                let after = null;
                try {
                  after = await withTimeout(childModel.count());
                } catch (_) { /* fail closed below */ }
                passed = !!res && res.status === c.expected_status
                  && typeof after === 'number'
                  && after - before === c.expected_persist_delta;
              }
            }
            checks.push({ name: String(c.name).slice(0, 80), passed });
          }
        }
        await db.$disconnect().catch(() => {});
      }
    }
    emit({ pass: checks.every((x) => x.passed), checks });
  }
} catch (_) {
  // Never forward candidate tracebacks; a trusted-side preparation failure or
  // a candidate import crash is simply a fail-closed verdict.
  fail('runtime-or-fixture-error');
}
