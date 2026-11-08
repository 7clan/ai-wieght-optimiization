// SESSION 036 — PHASE 1 STRUCTURAL VERIFICATION (TRUSTED-SCAFFOLD).
// TypeScript-AST analysis replacing Session 035's text/substring gates.
//
// Design goals (from the Session 035 false-acceptance postmortem):
//  - required expressions must exist as AST nodes (comments and string
//    literals can never satisfy an expression gate);
//  - route files must actually export function-like HTTP handlers
//    (import-only "anchor" files can never pass);
//  - code after an unconditional return/throw, or inside constant-false
//    branches, is UNREACHABLE and cannot satisfy any gate;
//  - instruction/spec echo is detected on comment+string content, and the
//    bulk of a file being echo is a rejection even when some code exists;
//  - parse errors (truncation) reject up front.
//
// No application bytes live here; this is test tooling only.

import ts from 'typescript';

export function parseSource(code, fileName = 'file.ts') {
  const kind = fileName.endsWith('.tsx') ? ts.ScriptKind.TSX
    : fileName.endsWith('.jsx') ? ts.ScriptKind.JSX
    : fileName.endsWith('.js') || fileName.endsWith('.mjs')
      ? ts.ScriptKind.JS : ts.ScriptKind.TS;
  const sf = ts.createSourceFile(fileName, code, ts.ScriptTarget.Latest,
    /*setParentNodes*/ true, kind);
  const diagnostics = sf.parseDiagnostics || [];
  const syntaxErrors = diagnostics.map(d => ({
    message: ts.flattenDiagnosticMessageText(d.messageText, ' '),
    start: d.start, length: d.length,
  }));
  return { sf, syntaxErrors };
}

// ---------------------------------------------------------------- helpers

function makeChainName(sf) {
  function chainName(node) {
    if (ts.isIdentifier(node)) return node.text;
    if (ts.isPropertyAccessExpression(node)) {
      const base = chainName(node.expression);
      return base === null ? null : `${base}.${node.name.text}`;
    }
    if (ts.isElementAccessExpression(node)
      && node.argumentExpression && ts.isNumericLiteral(node.argumentExpression)) {
      const base = chainName(node.expression);
      return base === null ? null : `${base}[${node.argumentExpression.text}]`;
    }
    return null;
  }
  return chainName;
}

function isTruthyConst(cond) {
  if (!cond) return null;
  if (cond.kind === ts.SyntaxKind.TrueKeyword) return true;
  if (cond.kind === ts.SyntaxKind.FalseKeyword) return false;
  if (ts.isNumericLiteral(cond)) return Number(cond.text) !== 0;
  if (cond.kind === ts.SyntaxKind.PrefixUnaryExpression
    && cond.operator === ts.SyntaxKind.ExclamationToken) {
    const inner = isTruthyConst(cond.operand);
    return inner === null ? null : !inner;
  }
  return null;
}

// ---------------------------------------------------------------- analysis

export function analyze(sourceFile, code) {
  const sf = sourceFile;
  const chainName = makeChainName(sf);
  const out = {
    exports: [],
    callChains: new Set(),
    accessChains: new Set(),
    exprs: new Set(),
    stringLiterals: [],
    jsxTexts: [],
    comments: [],
    unreachableRanges: [],
    imports: [],
    astNodeCount: 0,
  };

  // -- comments via scanner (skipTrivia=false so comment tokens EMIT;
  // Session-036 fix: with skipTrivia=true the echo gate was blind)
  const commentRanges = [];
  const scanner = ts.createScanner(sf.languageVersion, /*skipTrivia*/ false,
    ts.LanguageVariant.Standard, code);
  let token = scanner.scan();
  while (token !== ts.SyntaxKind.EndOfFileToken) {
    const t = token;
    if (t === ts.SyntaxKind.SingleLineCommentTrivia
      || t === ts.SyntaxKind.MultiLineCommentTrivia) {
      const text = scanner.getTokenText();
      commentRanges.push({
        start: scanner.getTokenStart(),
        end: scanner.getTokenStart() + text.length,
        text,
      });
    }
    token = scanner.scan();
  }
  out.comments = commentRanges.map(r =>
    r.text.replace(/^\/\/+|^\/\*+|\*\/$/g, '').trim());

  // -- symbol tables for resolution
  const localFunctions = new Set();
  const importedBindings = new Set();
  const identifiers = [];
  const declaredNames = new Set();
  const varInitializers = new Map(); // name -> {initKind, referenced:[]}

  function prepass(n) {
    if (ts.isImportDeclaration(n) && n.importClause) {
      const c = n.importClause;
      const bindings = [];
      if (c.name) { importedBindings.add(c.name.text); bindings.push({ name: c.name.text, kind: 'default' }); }
      if (c.namedBindings && ts.isNamedImports(c.namedBindings)) {
        for (const el of c.namedBindings.elements) {
          importedBindings.add((el.propertyName || el.name).text);
          bindings.push({ name: (el.propertyName || el.name).text, kind: 'named' });
        }
      }
      if (ts.isStringLiteral(n.moduleSpecifier)) {
        out.imports.push({ module: n.moduleSpecifier.text, bindings });
      }
    }
    if (ts.isFunctionDeclaration(n) && n.name) {
      localFunctions.add(n.name.text);
      declaredNames.add(n.name.text);
    }
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name)) {
      declaredNames.add(n.name.text);
      if (n.initializer && (ts.isArrowFunction(n.initializer)
        || ts.isFunctionExpression(n.initializer))) {
        localFunctions.add(n.name.text);
      }
    }
    if (ts.isIdentifier(n)) identifiers.push(n);
    n.forEachChild(prepass);
  }
  prepass(sf);

  function isIdentifierReferenced(name) {
    return identifiers.some(i =>
      i.text === name && !ts.isDeclarationName(i));
  }

  function isUsedPosition(node) {
    let p = node.parent, depth = 0;
    while (p && depth < 8) {
      if (ts.isJsxElement(p) || ts.isJsxSelfClosingElement(p)
        || ts.isJsxAttribute(p) || ts.isJsxExpression(p)
        || ts.isCallExpression(p) || ts.isNewExpression(p)
        || ts.isTemplateExpression(p) || ts.isPropertyAssignment(p)) return true;
      if (ts.isVariableDeclaration(p) && ts.isIdentifier(p.name)) {
        return isIdentifierReferenced(p.name.text);
      }
      p = p.parent; depth += 1;
    }
    return false;
  }

  const markUnreachable = (node, reason) => {
    out.unreachableRanges.push({
      start: node.getStart(sf), end: node.getEnd(), reason });
  };
  const inUnreachable = (node) => {
    const s = node.getStart(sf);
    return out.unreachableRanges.some(r => s >= r.start && s < r.end);
  };

  function hasExportMod(node) {
    return !!(node.modifiers && node.modifiers.some(
      mo => mo.kind === ts.SyntaxKind.ExportKeyword));
  }
  function hasDefaultMod(node) {
    return !!(node.modifiers && node.modifiers.some(
      mo => mo.kind === ts.SyntaxKind.DefaultKeyword));
  }

  function walk(node, unreachable) {
    out.astNodeCount += 1;

    if (ts.isFunctionDeclaration(node) && node.name && hasExportMod(node)) {
      out.exports.push({
        name: node.name.text, kind: 'function', functionLike: true,
        resolvable: true, pos: { start: node.getStart(sf), end: node.getEnd() },
      });
      // `export default function Home()` exports BOTH the name and default
      if (hasDefaultMod(node)) {
        out.exports.push({
          name: 'default', kind: 'default', functionLike: true,
          resolvable: true,
        });
      }
    }
    if (ts.isClassDeclaration(node) && node.name && hasExportMod(node)) {
      out.exports.push({
        name: node.name.text, kind: 'class', functionLike: false,
        resolvable: true,
      });
      if (hasDefaultMod(node)) {
        out.exports.push({ name: 'default', kind: 'default', functionLike: false,
          resolvable: true });
      }
    }
    if (ts.isVariableStatement(node) && hasExportMod(node)) {
      for (const d of node.declarationList.declarations) {
        if (ts.isIdentifier(d.name) && d.initializer) {
          const init = d.initializer;
          const initIsFn = ts.isArrowFunction(init) || ts.isFunctionExpression(init);
          const initIsResolvableIdent = ts.isIdentifier(init)
            && (localFunctions.has(init.text) || importedBindings.has(init.text));
          out.exports.push({
            name: d.name.text, kind: 'const',
            functionLike: !!(initIsFn || initIsResolvableIdent),
            resolvable: true,
            initKind: ts.SyntaxKind[init.kind],
            pos: { start: node.getStart(sf), end: node.getEnd() },
          });
        }
      }
    }
    // export default <expr>
    if (hasExportMod(node) && hasDefaultMod(node)
      && !ts.isFunctionDeclaration(node) && !ts.isClassDeclaration(node)) {
      const fn = ts.isFunctionExpression(node) || ts.isArrowFunction(node)
        || (ts.isIdentifier(node) && (localFunctions.has(node.text)
          || importedBindings.has(node.text)));
      out.exports.push({
        name: 'default', kind: 'default', functionLike: !!fn, resolvable: true,
      });
    }
    if (ts.isExportDeclaration(node) && node.exportClause
      && ts.isNamedExports(node.exportClause)) {
      for (const el of node.exportClause.elements) {
        out.exports.push({
          name: (el.propertyName || el.name).text, kind: 'reexport',
          functionLike: false, resolvable: false, reexport: true,
        });
      }
    }
    if (ts.isInterfaceDeclaration(node) && hasExportMod(node)) {
      const members = {};
      for (const mem of node.members) {
        if (ts.isPropertySignature(mem) && ts.isIdentifier(mem.name)) {
          members[mem.name.text] = mem.type
            ? mem.type.getText(sf).replace(/\s+/g, ' ') : 'unknown';
        }
      }
      out.exports.push({
        name: node.name.text, kind: 'interface', functionLike: false,
        resolvable: true, members,
      });
    }
    if (ts.isTypeAliasDeclaration(node) && hasExportMod(node)) {
      out.exports.push({
        name: node.name.text, kind: 'type', functionLike: false,
        resolvable: true,
      });
    }

    if (!unreachable) {
      if (ts.isCallExpression(node)) {
        const chain = chainName(node.expression);
        if (chain) out.callChains.add(chain);
      }
      if (ts.isPropertyAccessExpression(node)
        || ts.isElementAccessExpression(node)) {
        const chain = chainName(node);
        if (chain) out.accessChains.add(chain);
      }
      if (ts.isBinaryExpression(node)) {
        // normalized comparison/arithmetic expression (no spaces) so
        // expected semantics like a.quantity<=a.minQuantity are gated
        // on AST structure, never on substrings
        try {
          const norm = node.getText(sf).replace(/\s+/g, '');
          if (norm.length <= 80) out.exprs.add(norm);
        } catch { /* positionless node */ }
      }
      if (ts.isStringLiteral(node)
        || ts.isNoSubstitutionTemplateLiteral(node)) {
        out.stringLiterals.push({ value: node.text, used: isUsedPosition(node) });
      }
      if (ts.isJsxText(node)) out.jsxTexts.push({ value: node.text.trim() });
    } else if (ts.isStringLiteral(node)
      || ts.isNoSubstitutionTemplateLiteral(node)) {
      out.stringLiterals.push({
        value: node.text, used: false, unreachable: true });
    }

    // reachability rules
    if (ts.isIfStatement(node)) {
      const tv = isTruthyConst(node.expression);
      if (tv === false) markUnreachable(node.thenStatement, 'if(false) branch');
      else if (tv === true && node.elseStatement) {
        markUnreachable(node.elseStatement, 'else of if(true)');
      }
    }
    if (ts.isWhileStatement(node)
      && isTruthyConst(node.expression) === false) {
      markUnreachable(node.statement, 'while(false) body');
    }
    if (ts.isBlock(node)) {
      const stmts = node.statements;
      for (let i = 0; i < stmts.length; i++) {
        const s = stmts[i];
        if (ts.isReturnStatement(s) || ts.isThrowStatement(s)) {
          for (let j = i + 1; j < stmts.length; j++) {
            markUnreachable(stmts[j],
              `statement after unconditional ${ts.isReturnStatement(s) ? 'return' : 'throw'}`);
          }
          break;
        }
      }
    }

    node.forEachChild(child => walk(child,
      unreachable || inUnreachable(child)));
  }

  walk(sf, false);

  return {
    exports: out.exports,
    callChains: [...out.callChains],
    accessChains: [...out.accessChains],
    exprs: [...out.exprs],
    stringLiterals: out.stringLiterals,
    jsxTexts: out.jsxTexts,
    comments: out.comments,
    commentRanges,
    unreachableRanges: out.unreachableRanges,
    imports: out.imports,
    astNodeCount: out.astNodeCount,
    hasTodo: /\b(TODO|FIXME|XXX|implementation omitted)\b/i.test(code),
  };
}

export function parseAndAnalyze(code, fileName = 'file.ts') {
  const { sf, syntaxErrors } = parseSource(code, fileName);
  if (syntaxErrors.length) {
    return { ok: false, syntaxErrors, analysis: null };
  }
  return { ok: true, syntaxErrors: [], analysis: analyze(sf, code) };
}

// ---------------------------------------------------------------- echo

export function ngrams(text, n = 8) {
  const toks = text.toLowerCase().replace(/\s+/g, ' ').trim().split(' ');
  if (toks.length < n) return toks.length ? [toks.join(' ')] : [];
  const out = [];
  for (let i = 0; i + n <= toks.length; i++) {
    out.push(toks.slice(i, i + n).join(' '));
  }
  return out;
}

export function echoFraction(analysis, instructionText) {
  const content = [
    ...analysis.comments,
    ...analysis.stringLiterals.map(s => s.value),
    ...analysis.jsxTexts.map(s => s.value),
  ].join('\n');
  const grams = ngrams(content);
  if (!grams.length) return 0;
  const instr = new Set(ngrams(instructionText, 8));
  const instrTokens = new Set(
    instructionText.toLowerCase().replace(/\s+/g, ' ').trim().split(' '));
  let hits = 0;
  for (const g of grams) {
    if (instr.has(g)) { hits++; continue; }
    const gt = g.split(' ');
    if (gt.length < 8) {
      const inInstr = gt.filter(t => instrTokens.has(t)).length / gt.length;
      if (inInstr >= 0.8) hits++;
    }
  }
  return hits / grams.length;
}
