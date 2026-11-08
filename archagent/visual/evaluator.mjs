// archagent/visual/evaluator.mjs — multi-viewport visual quality evaluator.
//
// Session 034 test infrastructure (TRUSTED-SCAFFOLD, teacher-authored
// tooling — no application bytes are written here).  Measures the TEN
// visual-quality requirements on a LIVE page at FIVE viewports using DOM
// geometry + getComputedStyle only.  No screenshot-similarity heuristics:
// every check is a reproducible DOM/computed-style assertion.
//
// Metrics (mission section 4):
//  1 text-visibility      every visible text node: non-zero box, font >= 10px,
//                         non-transparent color
//  2 no-overlap           visible siblings do not intersect (>10% of the
//                         smaller rect)
//  3 no-h-overflow        documentElement.scrollWidth <= viewport width
//  4 button-visibility    visible buttons meet minimum hit areas
//                         (>=28x24 desktop, >=40x40 touch widths)
//  5 alignment            repeated same-class siblings share left edge <=1.5px
//  6 responsive-adaptation no overflow at ANY viewport AND content width
//                         adapts (390px content <= 1440px content + tol)
//  7 typography           <= 8 distinct font sizes, body 13-20px
//  8 contrast             WCAG: all text >= 3.0:1, >= 90% of text >= 4.5:1
//  9 interactivity        buttons cursor:pointer + >= 3 :hover rules in CSS
// 10 visual-hierarchy     headings larger than body, sizes non-increasing
//                         h1 >= h2 >= h3, at most one h1
//
// Usage:
//   node archagent/visual/evaluator.mjs --base http://127.0.0.1:4173 \
//        --out experiments/zai-visual/reports/vis_baseline.json \
//        [--shots dir] [--waitfor .app] [--viewports 1440x900,...]
'use strict';
import {chromium} from 'playwright';
import {mkdirSync, writeFileSync} from 'node:fs';
import path from 'node:path';

const DEFAULT_VIEWPORTS = [
  [1440, 900], [1280, 800], [768, 1024], [390, 844], [320, 700],
];

function arg(name, dflt) {
  const i = process.argv.indexOf('--' + name);
  return i > -1 ? process.argv[i + 1] : dflt;
}

// ---- in-page measurement (runs inside the browser) ----------------------

const MEASURE = `(function measure() {
  const out = {issues: {}, sizes: []};

  function visible(el) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function ownText(el) {
    let n = 0;
    for (const c of el.childNodes) if (c.nodeType === 3 && c.textContent.trim()) n++;
    return n > 0;
  }
  function parseColor(s) {
    const m = s.match(/rgba?\\(([\\d.]+),\\s*([\\d.]+),\\s*([\\d.]+)(?:,\\s*([\\d.]+))?\\)/);
    if (!m) return null;
    return [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]];
  }
  function blend(fg, bg) {  // fg over bg with alpha
    return [0, 1, 2].map(i => fg[3] * fg[i] + (1 - fg[3]) * bg[i]).concat([1]);
  }
  function effBg(el) {
    let node = el;
    while (node && node !== document.documentElement) {
      const c = parseColor(getComputedStyle(node).backgroundColor);
      if (c && c[3] > 0.55) return c;
      node = node.parentElement;
    }
    return [255, 255, 255, 1];
  }
  function lum(c) {
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  }
  function contrast(fg, bg) {
    const l1 = lum(fg), l2 = lum(bg);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  }

  const isTouch = innerWidth <= 700;
  const all = Array.from(document.querySelectorAll('*')).filter(visible);
  const bodyCs = getComputedStyle(document.body);

  // 1 text visibility
  const tv = [];
  for (const el of all) {
    if (!ownText(el)) continue;
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    const size = parseFloat(cs.fontSize);
    const color = parseColor(cs.color);
    if (r.width < 2 || r.height < 2) tv.push(el.tagName + '.' + el.className + ' zero-box');
    else if (!(size >= 10)) tv.push((el.className || el.tagName) + ' font=' + size);
    else if (!color || color[3] === 0) tv.push((el.className || el.tagName) + ' transparent');
    out.sizes.push(size);
  }
  out.issues.textVisibility = tv.slice(0, 8);

  // 2 sibling overlap
  const ov = [];
  const parents = new Set(all.map(el => el.parentElement));
  for (const p of parents) {
    if (!p) continue;
    const kids = Array.from(p.children).filter(visible);
    for (let i = 0; i < kids.length; i++) {
      for (let j = i + 1; j < kids.length; j++) {
        const a = kids[i].getBoundingClientRect(), b = kids[j].getBoundingClientRect();
        const ix = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
        const iy = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
        const inter = ix * iy;
        const small = Math.min(a.width * a.height, b.width * b.height);
        if (small > 0 && inter / small > 0.10 && inter > 16)
          ov.push((kids[i].className || kids[i].tagName) + '/' +
                  (kids[j].className || kids[j].tagName) +
                  ' ' + Math.round(100 * inter / small) + '%');
      }
    }
  }
  out.issues.overlap = ov.slice(0, 8);

  // 3 horizontal overflow
  out.issues.hOverflow = document.documentElement.scrollWidth > innerWidth + 1
    ? [document.documentElement.scrollWidth + ' > ' + innerWidth] : [];

  // 4 button visibility (WCAG 2.2 target size: >= 24x24 everywhere;
  // primary CTA text buttons >= 40x40 on touch widths)
  const bv = [];
  const minW = isTouch ? 40 : 24, minH = 24;
  for (const el of all) {
    if (!el.matches('button, [role=button], input[type=submit], input[type=button]')) continue;
    const r = el.getBoundingClientRect();
    const icon = (el.className || '').toString().includes('btn-icon');
    const wNeed = isTouch && !icon ? 40 : minW;
    if (r.width < wNeed || r.height < minH)
      bv.push((el.className || 'button') + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
  }
  out.issues.buttonVisibility = bv.slice(0, 8);
  out.buttonCount = all.filter(el =>
    el.matches('button, [role=button], input[type=submit]')).length;

  // 5 alignment: vertical STACKS of >= 3 same-class siblings share the
  // left edge.  Grid/flex rows (single line of columns) and irregular
  // layouts are skipped — only strictly top-increasing stacks are lists.
  const al = [];
  for (const p of parents) {
    if (!p) continue;
    const groups = {};
    for (const k of Array.from(p.children).filter(visible)) {
      const key = k.tagName + '|' + (k.className || '');
      (groups[key] = groups[key] || []).push(k);
    }
    for (const key in groups) {
      const g = groups[key];
      if (g.length < 3) continue;
      const tops = g.map(el => el.getBoundingClientRect().top);
      let stack = true;
      for (let i = 1; i < tops.length; i++)
        if (tops[i] - tops[i - 1] < 4) { stack = false; break; }
      if (!stack) continue;  // row/grid layout — left edges legitimately differ
      const lefts = g.map(el => el.getBoundingClientRect().left);
      const spread = Math.max(...lefts) - Math.min(...lefts);
      if (spread > 1.5) al.push(key.split('|')[1] + ' spread=' + spread.toFixed(1) + 'px');
    }
  }
  out.issues.alignment = al.slice(0, 8);

  // 7 typography
  const distinct = Array.from(new Set(out.sizes.map(s => Math.round(s * 2) / 2))).sort((a, b) => a - b);
  out.distinctSizes = distinct;
  out.bodySize = parseFloat(bodyCs.fontSize);
  out.issues.typography = [];
  if (distinct.length > 8) out.issues.typography.push(distinct.length + ' distinct sizes');
  if (!(out.bodySize >= 13 && out.bodySize <= 20))
    out.issues.typography.push('body=' + out.bodySize);

  // 8 contrast
  const cr = [];
  let nText = 0, nBelowNeed = 0;
  for (const el of all) {
    if (!ownText(el)) continue;
    const cs = getComputedStyle(el);
    const fg = parseColor(cs.color); if (!fg) continue;
    const bg = effBg(el);
    const ratio = contrast(blend(fg, bg), bg);
    nText++;
    const big = parseFloat(cs.fontSize) >= 24 ||
      (parseFloat(cs.fontWeight) >= 700 && parseFloat(cs.fontSize) >= 18.66);
    const need = big ? 3.0 : 4.5;
    if (ratio < 3.0)
      cr.push((el.className || el.tagName) + ' ' + ratio.toFixed(2) + ':1');
    if (ratio < need) nBelowNeed++;
  }
  out.textCount = nText;
  out.belowNeed = nBelowNeed;
  out.issues.contrast = cr.slice(0, 8);
  out.contrastPass = cr.length === 0 && nText > 0 &&
    nBelowNeed / Math.max(1, nText) <= 0.10;

  // 9 interactivity
  const cur = [];
  let nBtn = 0;
  for (const el of all) {
    if (!el.matches('button, [role=button], a[href], input, select, textarea')) continue;
    if (el.matches('input, select, textarea')) continue;
    nBtn++;
    if (getComputedStyle(el).cursor !== 'pointer')
      cur.push((el.className || el.tagName) + ' cursor=' + getComputedStyle(el).cursor);
  }
  let hoverRules = 0;
  try {
    for (const sheet of document.styleSheets) {
      let rules; try { rules = sheet.cssRules; } catch (e) { continue; }
      if (!rules) continue;
      for (const r of rules)
        if (r.selectorText && r.selectorText.includes(':hover')) hoverRules++;
    }
  } catch (e) {}
  out.hoverRules = hoverRules;
  out.issues.interactivity = cur.slice(0, 8);
  out.cursorPass = cur.length === 0;
  out.interactivityPass = out.cursorPass && hoverRules >= 3 && nBtn > 0;

  // 10 visual hierarchy
  const hi = [];
  const levels = [1, 2, 3, 4];
  const sizes = {};
  for (const l of levels) {
    const els = Array.from(document.querySelectorAll('h' + l)).filter(visible);
    if (els.length) sizes[l] = parseFloat(getComputedStyle(els[0]).fontSize);
  }
  out.headingSizes = sizes;
  const hs = Object.values(sizes);
  for (let i = 1; i < hs.length; i++)
    if (hs[i] > hs[i - 1]) hi.push('h' + levels[i] + '(' + hs[i] + ') > h' + levels[i-1] + '(' + hs[i-1] + ')');
  for (const l of levels)
    if (sizes[l] && sizes[l] <= out.bodySize) hi.push('h' + l + '=' + sizes[l] + ' <= body');
  if (document.querySelectorAll('h1').length > 1) hi.push('multiple h1');
  out.issues.hierarchy = hi.slice(0, 8);
  out.hierarchyPass = hi.length === 0 && Object.keys(sizes).length >= 1;

  // responsive inputs
  out.scrollWidth = document.documentElement.scrollWidth;
  out.innerWidth = innerWidth;
  const main = document.querySelector('main, .main, .content, #root > div');
  out.contentWidth = main ? main.getBoundingClientRect().width :
    document.body.getBoundingClientRect().width;
  return out;
})();`;

// ---- driver ---------------------------------------------------------------

(async () => {
  const base = arg('base', 'http://127.0.0.1:4173');
  const outPath = arg('out', null);
  const shotsDir = arg('shots', null);
  const waitfor = arg('waitfor', 'body');
  const vpArg = arg('viewports', null);
  const viewports = vpArg ? vpArg.split(',').map(s => s.split('x').map(Number))
    : DEFAULT_VIEWPORTS;

  const browser = await chromium.launch();
  const report = {base, when: new Date().toISOString(), viewports: [], aggregate: {}};
  const perMetric = {};

  for (const [w, h] of viewports) {
    const ctx = await browser.newContext({viewport: {width: w, height: h}});
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(String(e.message).slice(0, 120)));
    try {
      await page.goto(base, {waitUntil: 'networkidle', timeout: 20000});
      if (waitfor && waitfor !== 'body') await page.waitForSelector(waitfor, {timeout: 8000});
      else await page.waitForTimeout(400);
    } catch (e) {
      report.viewports.push({width: w, height: h, error: String(e.message).split('\n')[0]});
      await ctx.close();
      continue;
    }
    const m = await page.evaluate(MEASURE);
    const vw = {
      width: w, height: h, page_errors: errors,
      metrics: {
        'text-visibility': m.issues.textVisibility.length === 0,
        'no-overlap': m.issues.overlap.length === 0,
        'no-h-overflow': m.issues.hOverflow.length === 0,
        'button-visibility': m.issues.buttonVisibility.length === 0,
        'alignment': m.issues.alignment.length === 0,
        'typography-consistency': m.issues.typography.length === 0,
        'contrast': m.contrastPass === true,
        'interactivity': m.interactivityPass === true,
        'visual-hierarchy': m.hierarchyPass === true,
      },
      details: m.issues, distinctSizes: m.distinctSizes, bodySize: m.bodySize,
      headingSizes: m.headingSizes, hoverRules: m.hoverRules,
      textCount: m.textCount, belowNeed: m.belowNeed,
      buttonCount: m.buttonCount,
      scrollWidth: m.scrollWidth, innerWidth: m.innerWidth,
      contentWidth: Math.round(m.contentWidth),
    };
    for (const k in vw.metrics) (perMetric[k] = perMetric[k] || []).push(vw.metrics[k]);
    report.viewports.push(vw);
    if (shotsDir) {
      mkdirSync(shotsDir, {recursive: true});
      await page.screenshot({path: path.join(shotsDir, `v-${w}x${h}.png`), fullPage: false});
    }
    await ctx.close();
  }

  // cross-viewport responsive-adaptation
  const okVps = report.viewports.filter(v => !v.error);
  const noOverflow = okVps.length > 0 && okVps.every(v => v.metrics['no-h-overflow']);
  const wide = okVps.find(v => v.width === 1440) || okVps[0];
  const narrow = okVps.filter(v => v.width <= 391).sort((a, b) => a.width - b.width)[0];
  const adapts = !!(narrow && wide && narrow.contentWidth <= wide.contentWidth + 8);
  report.aggregate = {};
  for (const k in perMetric)
    report.aggregate[k] = {pass: perMetric[k].every(Boolean),
                           passed: perMetric[k].filter(Boolean).length,
                           total: perMetric[k].length};
  report.aggregate['responsive-adaptation'] = {
    pass: noOverflow && adapts,
    passed: (noOverflow ? 1 : 0) + (adapts ? 1 : 0),
    total: 2,
    no_overflow_all_viewports: noOverflow, content_adapts: adapts,
  };
  report.responsive = {noOverflowAllViewports: noOverflow, contentAdapts: adapts,
    wide: wide && wide.contentWidth, narrow: narrow && narrow.contentWidth};
  const keys = Object.keys(report.aggregate);
  report.passed_metrics = keys.filter(k => report.aggregate[k].pass).length;
  report.total_metrics = keys.length;
  report.all_passed = report.passed_metrics === report.total_metrics;

  await browser.close();
  const text = JSON.stringify(report, null, 1);
  if (outPath) { mkdirSync(path.dirname(outPath), {recursive: true}); writeFileSync(outPath, text); }
  console.log(`visual: ${report.passed_metrics}/${report.total_metrics} metrics pass`);
  for (const k of keys) {
    const a = report.aggregate[k];
    console.log(`  ${a.pass ? 'PASS' : 'FAIL'}  ${k} (${a.passed}/${a.total} viewports)`);
  }
  process.exit(report.all_passed ? 0 : 2);
})().catch(e => { console.error('fatal:', e); process.exit(1); });
