// SESSION 036 — PHASE 1 (TRUSTED-SCAFFOLD).
// Structural gate engine.  A *contract* is a JSON description of what a
// file must contain; verification is AST-based, never substring-based.
//
// Contract kinds:
//  route      — Next.js API route: required exported HTTP handlers,
//               required call/access chains in reachable code
//  component  — React component: required exported names, required UI
//               strings in *used* literal positions
//  types      — required exported interfaces with member types
//  hook       — required exported function using given call chains
//  page       — default-exported component referencing given imports
//  prisma     — schema model/field expectations (see prisma_schema.mjs)
//  interfaces — cross-file: imports resolve, db.<model> exists in schema,
//               imported types exist in the types module
//
// Every gate failure carries a machine-readable reason.  The engine also
// runs an echo analysis against the instruction text when provided.

import { parseAndAnalyze, echoFraction } from './parse.mjs';
import { parsePrismaSchema, checkSchema } from './prisma_schema.mjs';
import fs from 'node:fs';
import path from 'node:path';

function collectReachableChains(a) {
  // chains already exclude unreachable positions by construction
  return { calls: new Set(a.callChains), accesses: new Set(a.accessChains) };
}

function chainSatisfied(set, expected) {
  // expected 'db.inventoryItem.findMany' is satisfied by an exact chain or
  // by a longer chain containing it as prefix path, e.g. access
  // 'db.inventoryItem' satisfied by 'db.inventoryItem.findMany'.
  for (const c of set) {
    if (c === expected) return true;
    if (c.startsWith(expected + '.')) return true;
  }
  return false;
}

export function verifyRoute(code, contract, fileName) {
  const failures = [];
  const { ok, syntaxErrors, analysis } = parseAndAnalyze(code, fileName);
  if (!ok) {
    return { pass: false, failures: ['parse: syntax errors — '
      + syntaxErrors.slice(0, 2).map(e => e.message.slice(0, 100)).join(' | ')] };
  }
  const a = analysis;

  // 1. required exported handlers, function-like
  for (const h of contract.handlers || []) {
    const ex = a.exports.find(e => e.name === h);
    if (!ex) {
      failures.push(`exports: HTTP handler '${h}' not exported `
        + `(found: ${a.exports.map(e => e.name).join(', ') || 'none'})`);
      continue;
    }
    if (ex.reexport) {
      failures.push(`exports: '${h}' is a re-export, not a handler definition`);
      continue;
    }
    if (!ex.functionLike) {
      failures.push(`exports: handler '${h}' is not function-like `
        + `(${ex.kind}${ex.initKind ? ' init=' + ex.initKind : ''}) — `
        + `import-only/anchor files never pass this gate`);
    }
  }

  // 2. required call chains in REACHABLE, executed positions
  const { calls } = collectReachableChains(a);
  for (const c of contract.calls || []) {
    if (!chainSatisfied(calls, c)) {
      failures.push(`calls: '${c}' not found as a reachable call expression `
        + `(comments/strings/unreachable code never satisfy this gate)`);
    }
  }
  // 3. required access chains (e.g. db.inventoryItem) in reachable code
  const { accesses } = collectReachableChains(a);
  for (const c of contract.accesses || []) {
    if (!chainSatisfied(accesses, c) && !chainSatisfied(calls, c)) {
      failures.push(`accesses: '${c}' not found in reachable code`);
    }
  }
  // 3b. required EXPRESSIONS (normalized, AST binary nodes only —
  // comments/strings/unreachable regions can never satisfy these)
  const exprSet = new Set(a.exprs.map(e => e.replace(/\s+/g, '')));
  for (const e of contract.exprs || []) {
    const want = e.replace(/\s+/g, '');
    if (![...exprSet].some(got => got === want || got.includes(want))) {
      failures.push(`exprs: '${e}' not found as a reachable AST expression`);
    }
  }

  // 4. unreachable-code rejection
  if (contract.noUnreachable !== false && a.unreachableRanges.length) {
    failures.push(`reachability: ${a.unreachableRanges.length} unreachable `
      + `region(s): ${a.unreachableRanges[0].reason}`);
  }
  // expressions required to be OUTSIDE unreachable regions are enforced by
  // construction (chains are only collected from reachable nodes).

  // 5. completeness markers
  if (a.hasTodo && contract.rejectTodo !== false) {
    failures.push('incomplete: TODO/FIXME marker present');
  }

  // 6. echo analysis
  if (contract.instruction) {
    const ef = echoFraction(a, contract.instruction);
    if (ef > (contract.echoLimit ?? 0.5)) {
      failures.push(`echo: ${(ef * 100).toFixed(0)}% of comment/string content `
        + `duplicates the instruction (limit ${Math.round((contract.echoLimit ?? 0.5) * 100)}%)`);
    }
  }
  return { pass: failures.length === 0, failures };
}

export function verifyComponent(code, contract, fileName) {
  const failures = [];
  const { ok, syntaxErrors, analysis } = parseAndAnalyze(code, fileName);
  if (!ok) {
    return { pass: false, failures: ['parse: syntax errors — '
      + syntaxErrors.slice(0, 2).map(e => e.message.slice(0, 100)).join(' | ')] };
  }
  const a = analysis;

  for (const name of contract.exports || []) {
    const ex = a.exports.find(e => e.name === name
      || (name === 'default' && e.kind === 'default'));
    if (!ex) {
      failures.push(`exports: '${name}' not exported (found: ${
        a.exports.map(e => e.name).join(', ') || 'none'})`);
    }
  }

  // required UI strings must be in USED literal positions (JSX text,
  // JSX attribute, call argument, or referenced const initializer) —
  // never comments, never unreferenced constants.
  for (const s of contract.uiStrings || []) {
    const hit = a.jsxTexts.some(j => j.value.includes(s))
      || a.stringLiterals.some(l => l.used && l.value.includes(s));
    if (!hit) {
      failures.push(`uiStrings: '${s}' not found in a used string/JSX position `
        + `(comments and unreferenced constants never satisfy this gate)`);
    }
  }

  const { calls } = collectReachableChains(a);
  for (const c of contract.calls || []) {
    if (!chainSatisfied(calls, c)) {
      failures.push(`calls: '${c}' not found as a reachable call expression`);
    }
  }
  if (a.unreachableRanges.length && contract.noUnreachable !== false) {
    failures.push(`reachability: ${a.unreachableRanges.length} unreachable region(s)`);
  }
  if (a.hasTodo && contract.rejectTodo !== false) {
    failures.push('incomplete: TODO/FIXME marker present');
  }
  if (contract.instruction) {
    const ef = echoFraction(a, contract.instruction);
    if (ef > (contract.echoLimit ?? 0.5)) {
      failures.push(`echo: ${(ef * 100).toFixed(0)}% of comment/string content duplicates the instruction`);
    }
  }
  return { pass: failures.length === 0, failures };
}

// glob match: '*' is wildcard, everything else literal (Session-036 fix:
// the previous regex-escape approach re-escaped its own escape sequences)
function globMatch(pattern, text) {
  if (!pattern.includes('*')) return pattern === text;
  const parts = pattern.split('*');
  let pos = 0;
  for (let i = 0; i < parts.length; i++) {
    if (i === 0) {
      if (!text.startsWith(parts[i])) return false;
      pos = parts[i].length;
    } else if (i === parts.length - 1) {
      return text.endsWith(parts[i])
        && pos <= text.length - parts[i].length;
    } else {
      const found = text.indexOf(parts[i], pos);
      if (found === -1) return false;
      pos = found + parts[i].length;
    }
  }
  return true;
}

export function verifyTypes(code, contract, fileName) {
  const failures = [];
  const { ok, syntaxErrors, analysis } = parseAndAnalyze(code, fileName);
  if (!ok) {
    return { pass: false, failures: ['parse: syntax errors — '
      + syntaxErrors.slice(0, 2).map(e => e.message.slice(0, 100)).join(' | ')] };
  }
  const a = analysis;
  for (const want of contract.interfaces || []) {
    const ex = a.exports.find(e => e.name === want.name && e.kind === 'interface');
    if (!ex) {
      failures.push(`types: interface '${want.name}' not exported (found: ${
        a.exports.map(e => `${e.name}:${e.kind}`).join(', ') || 'none'})`);
      continue;
    }
    for (const [member, typePat] of Object.entries(want.members || {})) {
      const got = ex.members?.[member];
      if (got === undefined) {
        failures.push(`types: ${want.name}.${member} missing`);
      } else if (typePat && typePat !== '*'
        && !globMatch(typePat, got)) {
        failures.push(`types: ${want.name}.${member} is '${got}' (want ~'${typePat}')`);
      }
    }
  }
  if (contract.instruction) {
    const ef = echoFraction(a, contract.instruction);
    if (ef > (contract.echoLimit ?? 0.5)) {
      failures.push(`echo: ${(ef * 100).toFixed(0)}% content duplicates instruction`);
    }
  }
  return { pass: failures.length === 0, failures };
}

export function verifyInterfaces(root, checks) {
  // Cross-file interface validation.
  const failures = [];
  for (const c of checks) {
    try {
      const routePath = path.join(root, c.file);
      const code = fs.readFileSync(routePath, 'utf8');
      const { ok, analysis } = parseAndAnalyze(code, c.file);
      if (!ok) { failures.push(`interfaces: ${c.file} does not parse`); continue; }
      const a = analysis;

      if (c.importsFrom) {
        for (const spec of c.importsFrom) {
          const has = a.imports.some(i => i.module === spec.module
            && (spec.bindings ? spec.bindings.every(b =>
              i.bindings.some(ib => ib.name === b)) : true));
          if (!has) {
            failures.push(`interfaces: ${c.file} does not import ${
              spec.bindings ? spec.bindings.join(',') + ' from ' : ''}${spec.module}`);
          }
        }
      }
      if (c.usesModel) {
        // every db.<model> access in the file must exist in the schema
        const schemaPath = path.join(root,
          c.schema || 'prisma/schema.prisma');
        const schema = parsePrismaSchema(
          fs.readFileSync(schemaPath, 'utf8'));
        const used = new Set();
        for (const ch of a.accessChains.concat(a.callChains)) {
          const m = ch.match(/^db\.([a-zA-Z_]\w*)/);
          if (m) used.add(m[1]);
        }
        for (const u of used) {
          // prisma client exposes camelCase model accessors
          const model = u.charAt(0).toUpperCase() + u.slice(1);
          if (!schema.models[model]) {
            failures.push(`interfaces: ${c.file} uses db.${u} but model '${model}' `
              + `is not in the schema (models: ${
                Object.keys(schema.models).join(', ') || 'none'})`);
          }
        }
        if (c.usesModel === true && used.size === 0) {
          failures.push(`interfaces: ${c.file} never accesses any db.<model>`);
        }
      }
      if (c.exportsCallable) {
        for (const name of c.exportsCallable) {
          const ex = a.exports.find(e => e.name === name);
          if (!ex || !ex.functionLike) {
            failures.push(`interfaces: ${c.file} export '${name}' is not callable`);
          }
        }
      }
    } catch (e) {
      failures.push(`interfaces: ${c.file} — harness error ${String(e).slice(0, 120)}`);
    }
  }
  return { pass: failures.length === 0, failures };
}

export function verifyPrisma(schemaText, contract) {
  const parsed = parsePrismaSchema(schemaText);
  const failures = checkSchema(parsed, contract);
  return { pass: failures.length === 0, failures, parsed };
}

// SESSION 037 — invariant predicate gate (structural pre-filter; the
// behavioral oracle in archagent/generalize/probe.py does the semantic
// work).  A comment/string can never satisfy the exprs check because
// exprs are collected from AST binary nodes in reachable positions only.
export function verifyInvariant(code, contract, fileName) {
  const failures = [];
  const { ok, syntaxErrors, analysis } = parseAndAnalyze(code, fileName);
  if (!ok) {
    return { pass: false, failures: ['parse: syntax errors — '
      + syntaxErrors.slice(0, 2).map(e => e.message.slice(0, 100)).join(' | ')] };
  }
  const a = analysis;
  const name = contract.function;
  const ex = a.exports.find(e => e.name === name);
  if (!ex) {
    failures.push(`invariant: function '${name}' not exported (found: ${
      a.exports.map(e => e.name).join(', ') || 'none'})`);
  } else if (!ex.functionLike) {
    failures.push(`invariant: '${name}' is not function-like (${ex.kind})`);
  }
  // at least one comparison/logical binary expression (reachable AST)
  const hasBoolish = [...a.exprs].some(e =>
    /(<=|>=|<|>|&&|\|\||===|!==)/.test(e));
  if (!hasBoolish) {
    failures.push("invariant: no reachable comparison/logical expression "
      + '(a predicate must compare or combine booleans)');
  }
  if (a.unreachableRanges.length) {
    failures.push(`reachability: ${a.unreachableRanges.length} unreachable `
      + `region(s): ${a.unreachableRanges[0].reason}`);
  }
  if (a.hasTodo && contract.rejectTodo !== false) {
    failures.push('incomplete: TODO/FIXME marker present');
  }
  return { pass: failures.length === 0, failures };
}

// ---------------------------------------------------------------- dispatch

export function verifyFile(code, contract, fileName) {
  switch (contract.kind) {
    case 'route': return verifyRoute(code, contract, fileName);
    case 'component': return verifyComponent(code, contract, fileName);
    case 'types': return verifyTypes(code, contract, fileName);
    case 'hook': return verifyRoute(code, {
      ...contract, handlers: contract.exports, accesses: contract.accesses,
    }, fileName);
    case 'page': {
      const c = { ...contract };
      const r = verifyComponent(code, {
        ...c, exports: c.exports || ['default'],
      }, fileName);
      // page must default-export a component (function-like not required —
      // it can be a forwardRef/HOC result; parse + reference checks suffice)
      return r;
    }
    case 'prisma': return verifyPrisma(code, contract);
    case 'invariant': return verifyInvariant(code, contract, fileName);
    default:
      return { pass: false, failures: [`unknown contract kind ${contract.kind}`] };
  }
}
