// SESSION 036 — PHASE 1 (TRUSTED-SCAFFOLD).
// ADVERSARIAL EVALUATOR TESTS — "test the evaluator itself before
// allowing it to judge Qwen."
//
// Every fixture below reproduces a documented Session-035 false
// acceptance (or false rejection) and asserts the structural gate makes
// the OPPOSITE call.  Fixtures marked REAL are bytes from the actual
// archived StockPilot surface and must PASS (false-reject regression).
//
// Run: NODE_PATH=<sandbox node_modules> node adversarial.test.mjs

import { verifyRoute, verifyComponent, verifyTypes, verifyPrisma }
  from './gates.mjs';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = '/home/z/my-project';
let pass = 0, fail = 0;
function expect(name, verdict, wantPass, extra) {
  const ok = verdict.pass === wantPass
    && (wantPass || verdict.failures.length > 0);
  if (ok) { pass++; console.log(`  PASS ${name}`); }
  else {
    fail++;
    console.log(`  FAIL ${name} — expected ${wantPass ? 'ACCEPT' : 'REJECT'}, `
      + `got ${verdict.pass ? 'ACCEPT' : 'REJECT'} `
      + `${JSON.stringify(verdict.failures).slice(0, 240)}`);
  }
}

console.log('== A. import-only route (Session-035 anchor-only false accept) ==');

// A1: the exact failure shape that passed tsc+eslint in Session 035 —
// imports and a comment, no handlers.
const importOnly = `import { NextResponse } from 'next/server';
import { db } from '@/lib/db';

// GET returns the list of inventory items.
// POST creates a new item with name, category, sku, quantity, minQuantity.
// PUT updates an item. DELETE removes an item.
export {};
`;
expect('A1 import-only route rejected',
  verifyRoute(importOnly, {
    kind: 'route', handlers: ['GET', 'POST'],
    calls: ['NextResponse.json'], accesses: ['db.inventoryItem'],
  }, 'route.ts'), false);

// A2: same file with an unused handler-shaped const that is NOT exported.
const notExported = `import { NextResponse } from 'next/server';
const GET = async () => NextResponse.json({ items: [] });
`;
expect('A2 unexported handler rejected',
  verifyRoute(notExported, {
    kind: 'route', handlers: ['GET'],
  }, 'route.ts'), false);

// A3: handler exported but assigned a non-function.
const constNotFn = `import { NextResponse } from 'next/server';
export const GET = 'handler goes here';
`;
expect('A3 non-function export rejected',
  verifyRoute(constNotFn, { kind: 'route', handlers: ['GET'] }, 'route.ts'),
  false);

// A4: re-export masquerading as a handler.
const reexport = `export { GET, POST } from './other';
`;
expect('A4 re-export rejected',
  verifyRoute(reexport, { kind: 'route', handlers: ['GET', 'POST'] },
    'route.ts'), false);

console.log('== B. echo false accepts (instruction/spec/comment/strings) ==');

const INSTRUCTION = `Write the GET handler for the inventory list route.
Read query params q, category, status, sort, order. Filter with
db.inventoryItem.findMany. Use Number.isInteger to validate quantity.
Return NextResponse.json with items and total.`;

// B1: required expression present ONLY in a comment (Session-035 bug #7:
// "substring expects satisfiable by instruction echoes").
const commentEcho = `import { NextResponse } from 'next/server';
import { db } from '@/lib/db';

export async function GET() {
  // Number.isInteger(quantity) must be used to validate quantity
  const rows = await db.inventoryItem.findMany();
  return NextResponse.json({ items: rows, total: rows.length });
}
`;
expect('B1 comment-only expression rejected',
  verifyRoute(commentEcho, {
    kind: 'route', handlers: ['GET'], calls: ['Number.isInteger'],
  }, 'route.ts'), false);

// B2: required string in an UNREFERENCED constant (item-table false
// accept shape: spec strings present but never rendered).
const unusedConst = `import { Badge } from '@/components/ui/badge';

export function Toolbar() {
  const noMatch = 'No items match your filters';
  return <div className="toolbar"><input aria-label="Search" /></div>;
}
`;
expect('B2 unreferenced string constant rejected',
  verifyComponent(unusedConst, {
    kind: 'component', exports: ['Toolbar'],
    uiStrings: ['No items match your filters'],
  }, 'toolbar.tsx'), false);

// B3: the same string actually rendered in JSX must PASS (no false reject).
const usedString = `export function Toolbar() {
  return <div className="toolbar"><p>No items match your filters</p></div>;
}
`;
expect('B3 rendered string accepted',
  verifyComponent(usedString, {
    kind: 'component', exports: ['Toolbar'],
    uiStrings: ['No items match your filters'],
  }, 'toolbar.tsx'), true);

// B4: bulk-echo file (the "documentation-only completion" shape: mostly
// the instruction back as comments around a token body).
const bulkEcho = `// Write the GET handler for the inventory list route.
// Read query params q, category, status, sort, order. Filter with
// db.inventoryItem.findMany. Use Number.isInteger to validate quantity.
// Return NextResponse.json with items and total.
import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({ ok: true });
}
`;
expect('B4 bulk instruction echo rejected',
  verifyRoute(bulkEcho, {
    kind: 'route', handlers: ['GET'], instruction: INSTRUCTION,
  }, 'route.ts'), false);

console.log('== C. unreachable validation logic ==');

// C1: validation after an unconditional return (Session-036 brief).
const afterReturn = `import { NextResponse } from 'next/server';

export async function POST(req) {
  const body = await req.json();
  return NextResponse.json({ created: body });
  // unreachable:
  if (!Number.isInteger(body.quantity)) {
    return NextResponse.json({ error: 'quantity must be an integer' }, { status: 400 });
  }
}
`;
const c1 = verifyRoute(afterReturn, {
  kind: 'route', handlers: ['POST'], calls: ['Number.isInteger'],
}, 'route.ts');
expect('C1 code after return rejected', c1, false);
if (!c1.failures.some(f => f.startsWith('reachability'))) {
  fail++; console.log('  FAIL C1a — rejection was not via reachability gate: '
    + JSON.stringify(c1.failures));
} else { pass++; console.log('  PASS C1a reachability reason recorded'); }

// C2: validation inside if(false).
const ifFalse = `import { NextResponse } from 'next/server';

export async function POST(req) {
  const body = await req.json();
  if (false) {
    if (!Number.isInteger(body.quantity)) {
      return NextResponse.json({ error: 'bad' }, { status: 400 });
    }
  }
  return NextResponse.json({ created: body });
}
`;
expect('C2 if(false) validation rejected',
  verifyRoute(ifFalse, {
    kind: 'route', handlers: ['POST'], calls: ['Number.isInteger'],
  }, 'route.ts'), false);

// C3: reachable validation must PASS.
const validValidation = `import { NextResponse } from 'next/server';

export async function POST(req) {
  const body = await req.json();
  if (!Number.isInteger(body.quantity)) {
    return NextResponse.json({ error: 'quantity must be an integer' }, { status: 400 });
  }
  return NextResponse.json({ created: body });
}
`;
expect('C3 reachable validation accepted',
  verifyRoute(validValidation, {
    kind: 'route', handlers: ['POST'], calls: ['Number.isInteger'],
  }, 'route.ts'), true);

console.log('== D. truncation / incompleteness ==');

const truncated = `import { NextResponse } from 'next/server';
import { db } from '@/lib/db';

export async function GET() {
  const rows = await db.inventoryItem.findMany({
    where: {
`;
expect('D1 truncated body rejected',
  verifyRoute(truncated, {
    kind: 'route', handlers: ['GET'],
  }, 'route.ts'), false);

const truncatedJsx = `export function Toolbar() {
  return <div className="toolbar"><input aria-label="Search" valu
`;
expect('D2 truncated JSX rejected',
  verifyComponent(truncatedJsx, {
    kind: 'component', exports: ['Toolbar'],
  }, 'toolbar.tsx'), false);

const todoBody = `export async function GET() {
  // TODO implement
  return null;
}
`;
expect('D3 TODO marker rejected',
  verifyRoute(todoBody, { kind: 'route', handlers: ['GET'] }, 'route.ts'),
  false);

console.log('== E. prisma schema gates ==');

const schemaWrongNull = `model InventoryItem {
  id          String   @id @default(cuid())
  name        String
  category    String
  sku         String
  quantity    Int
  minQuantity Int
}
`;
expect('E1 wrong nullability rejected',
  verifyPrisma(schemaWrongNull, {
    kind: 'prisma',
    models: [{ name: 'InventoryItem', fields: [
      { name: 'sku', type: 'String', optional: true },
    ] }],
  }), false);

const schemaOk = `model InventoryItem {
  id          String    @id @default(cuid())
  name        String
  category    String
  sku         String?
  quantity    Int
  minQuantity Int
  updatedAt   DateTime  @updatedAt
}
`;
expect('E2 correct schema accepted',
  verifyPrisma(schemaOk, {
    kind: 'prisma',
    models: [{ name: 'InventoryItem', fields: [
      { name: 'sku', type: 'String', optional: true },
      { name: 'quantity', type: 'Int' },
      { name: 'id', type: 'String', attrsIncludes: ['@id'] },
    ] }],
  }), true);

// E3: field only in a COMMENT must not count (comment-safe parser).
const schemaComment = `model InventoryItem {
  id   String @id
  name String
  // sku String?
}
`;
expect('E3 comment-only field rejected',
  verifyPrisma(schemaComment, {
    kind: 'prisma',
    models: [{ name: 'InventoryItem', fields: [
      { name: 'sku', type: 'String', optional: true }] }],
  }), false);

// E4: truncated schema (unclosed model) rejected.
expect('E4 truncated schema rejected',
  verifyPrisma(`model InventoryItem {
  id String @id
`, { kind: 'prisma', models: [{ name: 'InventoryItem' }] }), false);

console.log('== F. types contracts ==');

const typesOk = `export interface InventoryItem {
  id: string;
  name: string;
  category: string;
  sku: string | null;
  quantity: number;
  minQuantity: number;
}
`;
expect('F1 correct interface accepted',
  verifyTypes(typesOk, {
    kind: 'types',
    interfaces: [{ name: 'InventoryItem', members: {
      sku: 'string | null', quantity: 'number' } }],
  }, 'types.ts'), true);

expect('F2 wrong member type rejected',
  verifyTypes(typesOk, {
    kind: 'types',
    interfaces: [{ name: 'InventoryItem', members: { sku: 'string' } }],
  }, 'types.ts'), false);

expect('F3 missing interface rejected',
  verifyTypes(typesOk, {
    kind: 'types',
    interfaces: [{ name: 'Reservation', members: {} }],
  }, 'types.ts'), false);

console.log('== G. REAL archived StockPilot files (false-reject regression) ==');

const read = p => fs.readFileSync(path.join(root, p), 'utf8');
try {
  expect('G1 real items route accepted',
    verifyRoute(read('src/app/api/items/route.ts'), {
      kind: 'route', handlers: ['GET', 'POST'],
      calls: ['NextResponse.json'],
      accesses: ['db.inventoryItem'],
    }, 'route.ts'), true);

  expect('G2 real [id] route accepted',
    verifyRoute(read('src/app/api/items/[id]/route.ts'), {
      kind: 'route', handlers: ['GET', 'PUT', 'DELETE'],
      calls: ['NextResponse.json'],
      accesses: ['db.inventoryItem'],
    }, 'route.ts'), true);

  expect('G3 real types.ts accepted',
    verifyTypes(read('src/lib/inventory/types.ts'), {
      kind: 'types',
      interfaces: [{ name: 'InventoryItem', members: {
        name: 'string', quantity: 'number' } }],
    }, 'types.ts'), true);

  expect('G4 real schema.prisma accepted',
    verifyPrisma(read('prisma/schema.prisma'), {
      kind: 'prisma',
      models: [{ name: 'InventoryItem', fields: [
        { name: 'sku', type: 'String', optional: true },
        { name: 'quantity', type: 'Int' },
      ] }],
    }), true);

  expect('G5 real states.tsx accepted',
    verifyComponent(read('src/components/stockpilot/states.tsx'), {
      kind: 'component',
      uiStrings: ['No items yet'],
    }, 'states.tsx'), true);

  expect('G6 real page.tsx accepted (page contract, default export)',
    verifyComponent(read('src/app/page.tsx'), {
      kind: 'page', exports: ['default'],
      accesses: ['useInventory'],
    }, 'page.tsx'), true);
} catch (e) {
  fail++;
  console.log(`  FAIL G — real-file regression could not run: ${e}`);
}

console.log(`\nadversarial suite: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
