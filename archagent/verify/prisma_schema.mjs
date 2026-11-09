// SESSION 036 — PHASE 1 (TRUSTED-SCAFFOLD).
// Structural Prisma schema parser: model blocks, fields, types,
// nullability, attributes.  Comment-safe and truncation-safe.

export function parsePrismaSchema(text) {
  const models = {};
  const enums = {};
  const errors = [];

  // strip comments but remember their ranges so "expressions in comments"
  // can never satisfy field requirements
  const clean = text.replace(/\/\/[^\n]*/g, m => ' '.repeat(m.length))
    .replace(/\/\*[\s\S]*?\*\//g, m => m.replace(/[^\n]/g, ' '));

  const modelRe = /model\s+([A-Za-z_][\w]*)\s*\{/g;
  let m;
  while ((m = modelRe.exec(clean))) {
    const name = m[1];
    const bodyStart = m.index + m[0].length;
    // brace matching (string-aware-lite: prisma has no braces in strings)
    let depth = 1, i = bodyStart;
    while (i < clean.length && depth > 0) {
      if (clean[i] === '{') depth++;
      else if (clean[i] === '}') depth--;
      i++;
    }
    if (depth !== 0) {
      errors.push(`model ${name}: unbalanced braces (truncated schema?)`);
      continue;
    }
    const body = clean.slice(bodyStart, i - 1);
    const fields = [];
    const attrs = [];
    for (const rawLine of body.split('\n')) {
      const line = rawLine.trim();
      if (!line) continue;
      // block attribute @@...
      const ba = line.match(/^@@(\w+)\s*(\([\s\S]*\))?$/);
      if (ba) { attrs.push(`@@${ba[1]}`); continue; }
      // field: name Type modifiers...
      const fa = line.match(/^([A-Za-z_][\w]*)\s+([A-Za-z_][\w]*)(\[\])?(\?)?\s*(.*)$/);
      if (fa) {
        fields.push({
          name: fa[1],
          type: fa[2] + (fa[3] || ''),
          optional: fa[4] === '?',
          isList: !!fa[3],
          attrs: (fa[5].match(/@\w+/g) || []),
          // SESSION 037: full attribute text (e.g. "@relation(fields: [x],
          // references: [id], onDelete: Cascade)") so expectation
          // substrings like 'onDelete: Cascade' can be gated.
          attrsFull: (fa[5].match(/@\w+\([^)]*\)/g) || []),
        });
        continue;
      }
      // anything else inside a model that isn't blank is suspicious
      if (!/^@/.test(line)) {
        errors.push(`model ${name}: unparsable line: ${line.slice(0, 60)}`);
      }
    }
    models[name] = { fields, attrs };
  }

  const enumRe = /enum\s+([A-Za-z_][\w]*)\s*\{/g;
  while ((m = enumRe.exec(clean))) {
    const name = m[1];
    const bodyStart = m.index + m[0].length;
    let depth = 1, i = bodyStart;
    while (i < clean.length && depth > 0) {
      if (clean[i] === '{') depth++;
      else if (clean[i] === '}') depth--;
      i++;
    }
    if (depth !== 0) { errors.push(`enum ${name}: unbalanced braces`); continue; }
    const values = clean.slice(bodyStart, i - 1).split('\n')
      .map(l => l.trim()).filter(l => l && !l.startsWith('//'));
    enums[name] = values;
  }

  return { models, enums, errors };
}

// Expectation format:
//   models: [{ name, fields: [{name, type, optional?, isList?, attrsIncludes?}] }]
export function checkSchema(parsed, expect) {
  const failures = [];
  for (const want of expect.models || []) {
    const got = parsed.models[want.name];
    if (!got) {
      failures.push(`schema: model '${want.name}' missing (found: ${
        Object.keys(parsed.models).join(', ') || 'none'})`);
      continue;
    }
    for (const wf of want.fields || []) {
      const gf = got.fields.find(f => f.name === wf.name);
      if (!gf) {
        failures.push(`schema: ${want.name}.${wf.name} missing`);
        continue;
      }
      // SESSION 037 FIX (false-reject bug found in the 036 archives):
      // the parser stores the list marker INSIDE type ("Album[]"),
      // while the contract format expresses lists as {type:'Album',
      // isList:true}.  Session 036 compared verbatim, so every
      // correctly-typed list relation field was rejected with
      // "type Album[] != Album" — visible in the archived ledgers
      // (trackB/trackC schema attempts, 2 such rejects each).
      // Normalize before comparing.
      const gotType = String(gf.type).replace(/\[\]$/, '');
      const gotIsList = String(gf.type).endsWith('[]');
      if (wf.type && gotType !== wf.type) {
        failures.push(`schema: ${want.name}.${wf.name} type ${gotType} != ${wf.type}`);
      }
      if (wf.optional !== undefined && gf.optional !== wf.optional) {
        failures.push(`schema: ${want.name}.${wf.name} optional=${gf.optional} != ${wf.optional}`);
      }
      if (wf.isList !== undefined && gotIsList !== wf.isList) {
        failures.push(`schema: ${want.name}.${wf.name} isList mismatch`);
      }
      if (wf.attrsIncludes && !wf.attrsIncludes.every(a => gf.attrs.includes(a)
        || (gf.attrsFull || []).some(f => f.includes(a)))) {
        failures.push(`schema: ${want.name}.${wf.name} attrs ${gf.attrs} missing ${wf.attrsIncludes}`);
      }
    }
  }
  for (const e of parsed.errors) failures.push(`schema: ${e}`);
  return failures;
}
