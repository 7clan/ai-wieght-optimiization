// archagent/visual/check_component.mjs — per-task acceptance criteria for
// the Session 034 visual curriculum.  Runs a REAL headless browser against
// the harness fixture for one task and asserts measurable DOM/computed-
// style criteria.  TRUSTED-SCAFFOLD test infrastructure.
//
// Usage: node archagent/visual/check_component.mjs --base http://127.0.0.1:4190 \
//          --task button-basics [--out report.json]
'use strict';
import {chromium} from 'playwright';
import {mkdirSync, writeFileSync} from 'node:fs';
import path from 'node:path';

function arg(name, dflt) {
  const i = process.argv.indexOf('--' + name);
  return i > -1 ? process.argv[i + 1] : dflt;
}

// Shared color math + helpers injected into every criteria context.
const PRELUDE = `
  const parseColor = s => {
    const m = s && s.match(/rgba?\\(([\\d.]+),\\s*([\\d.]+),\\s*([\\d.]+)(?:,\\s*([\\d.]+))?\\)/);
    return m ? [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]] : null;
  };
  const blend = (fg, bg) => [0,1,2].map(i => fg[3]*fg[i] + (1-fg[3])*bg[i]).concat([1]);
  const effBg = el => {
    let n = el;
    while (n && n !== document.documentElement) {
      const c = parseColor(getComputedStyle(n).backgroundColor);
      if (c && c[3] > 0.55) return c;
      n = n.parentElement;
    }
    return [255,255,255,1];
  };
  const lum = c => { const f = v => { v/=255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
    return 0.2126*f(c[0]) + 0.7152*f(c[1]) + 0.0722*f(c[2]); };
  const contrast = (fg, bg) => { const a = lum(fg), b = lum(bg);
    return (Math.max(a,b)+0.05)/(Math.min(a,b)+0.05); };
  const textContrast = el => {
    const fg = parseColor(getComputedStyle(el).color); if (!fg) return 0;
    return contrast(blend(fg, effBg(el)), effBg(el));
  };
  const rect = el => { const r = el.getBoundingClientRect();
    return {x: r.left, y: r.top, w: r.width, h: r.height}; };
  const cs = el => getComputedStyle(el);
  const q = s => document.querySelector(s);
  const qa = s => Array.from(document.querySelectorAll(s));
`;

// Per-task criteria.  Each returns [{name, ok, detail}].
const TASKS = {
  'design-tokens': () => [
    {name: 'surface token paints a background', ok: !!(() => {
      const el = q('.t-bg-surface'); if (!el) return false;
      const c = parseColor(cs(el).backgroundColor);
      return c && c[3] > 0.5; })(),
     detail: cs(q('.t-bg-surface')).backgroundColor},
    {name: 'strong text >= 4.5:1 on its background', ok: textContrast(q('.t-text-strong')) >= 4.5,
     detail: textContrast(q('.t-text-strong')).toFixed(2)},
    {name: 'muted text >= 3.0:1', ok: textContrast(q('.t-text-muted')) >= 3.0,
     detail: textContrast(q('.t-text-muted')).toFixed(2)},
    {name: 'muted differs from strong', ok: cs(q('.t-text-muted')).color !== cs(q('.t-text-strong')).color,
     detail: cs(q('.t-text-muted')).color},
  ],
  'base-reset': () => [
    {name: 'body margin 0', ok: parseFloat(cs(document.body).marginTop) === 0,
     detail: cs(document.body).marginTop},
    {name: 'box-sizing border-box', ok: cs(q('.stack')).boxSizing === 'border-box',
     detail: cs(q('.stack')).boxSizing},
    {name: 'body background painted', ok: (() => {
      const c = parseColor(cs(document.body).backgroundColor);
      return c && c[3] > 0.5; })(), detail: cs(document.body).backgroundColor},
    {name: 'paragraph text >= 4.5:1', ok: textContrast(q('.stack p')) >= 4.5,
     detail: textContrast(q('.stack p')).toFixed(2)},
  ],
  'typography-scale': () => {
    const h1 = parseFloat(cs(q('h1')).fontSize), h2 = parseFloat(cs(q('h2')).fontSize),
      h3 = parseFloat(cs(q('h3')).fontSize), p = parseFloat(cs(q('article p')).fontSize);
    return [
      {name: 'h1 > h2 > h3', ok: h1 > h2 && h2 > h3, detail: `${h1}>${h2}>${h3}`},
      {name: 'h3 > body', ok: h3 > p, detail: `${h3}>${p}`},
      {name: 'body 13-20px', ok: p >= 13 && p <= 20, detail: String(p)},
      {name: 'muted smaller or lighter', ok: (() => {
        const m = cs(q('.t-muted'));
        return parseFloat(m.fontSize) < p || parseInt(m.fontWeight) < 400 ||
          m.opacity < '1'; })(), detail: cs(q('.t-muted')).fontSize + '/' + cs(q('.t-muted')).fontWeight},
      {name: 'muted >= 3.0:1', ok: textContrast(q('.t-muted')) >= 3.0,
       detail: textContrast(q('.t-muted')).toFixed(2)},
    ];
  },
  'spacing-layout': () => {
    const stack = qa('.stack > *'), cards = qa('.row .card');
    const gapY = rect(stack[1]).y - (rect(stack[0]).y + rect(stack[0]).h);
    return [
      {name: 'stack vertical gap 8-64px', ok: gapY >= 8 && gapY <= 64, detail: gapY.toFixed(1) + 'px'},
      {name: 'row children same top', ok: Math.abs(rect(cards[0]).y - rect(cards[1]).y) < 2,
       detail: Math.abs(rect(cards[0]).y - rect(cards[1]).y).toFixed(1) + 'px'},
      {name: 'row children no overlap', ok: rect(cards[1]).x >= rect(cards[0]).x + rect(cards[0]).w - 1,
       detail: 'right=' + rect(cards[0]).w.toFixed(0) + ' next=' + rect(cards[1]).x.toFixed(0)},
      {name: 'cards have padding >= 12', ok: cards.every(c => parseFloat(cs(c).paddingTop) >= 12),
       detail: cs(cards[0]).paddingTop},
    ];
  },
  'card': () => {
    const card = q('.card'), inter = q('.card-interactive');
    return [
      {name: 'padding >= 12px', ok: parseFloat(cs(card).paddingTop) >= 12, detail: cs(card).paddingTop},
      {name: 'radius > 0', ok: parseFloat(cs(card).borderRadius) > 0, detail: cs(card).borderRadius},
      {name: 'border or shadow present', ok: cs(card).borderStyle !== 'none' ||
        cs(card).boxShadow !== 'none', detail: cs(card).boxShadow.slice(0, 30)},
      {name: 'surface background', ok: (() => { const c = parseColor(cs(card).backgroundColor);
        return c && c[3] > 0.5; })(), detail: cs(card).backgroundColor},
      {name: 'interactive hover rule exists', ok: (() => {
        try { for (const sh of document.styleSheets) {
          let rs; try { rs = sh.cssRules; } catch (e) { continue; }
          for (const r of rs || [])
            if (r.selectorText && r.selectorText.includes('.card-interactive') &&
                r.selectorText.includes(':hover')) return true; } } catch (e) {}
        return false; })(), detail: 'css :hover scan'},
      {name: 'card title is h3 > body', ok: parseFloat(cs(q('.card h3')).fontSize) > 16,
       detail: cs(q('.card h3')).fontSize},
    ];
  },
  'button-basics': () => {
    const btn = q('.btn'), dis = q('.btn[disabled]');
    return [
      {name: 'min height >= 32px', ok: rect(btn).h >= 32, detail: rect(btn).h.toFixed(0) + 'px'},
      {name: 'cursor pointer', ok: cs(btn).cursor === 'pointer', detail: cs(btn).cursor},
      {name: 'padding both axes >= 6px', ok: parseFloat(cs(btn).paddingTop) >= 6 &&
        parseFloat(cs(btn).paddingLeft) >= 6, detail: cs(btn).padding},
      {name: 'radius > 0', ok: parseFloat(cs(btn).borderRadius) > 0, detail: cs(btn).borderRadius},
      {name: 'text >= 4.5:1', ok: textContrast(btn) >= 4.5, detail: textContrast(btn).toFixed(2)},
      {name: 'disabled looks disabled', ok: (() => {
        if (!dis) return false;
        const d = cs(dis);
        return parseFloat(d.opacity) < 1 || d.cursor === 'not-allowed' ||
          d.pointerEvents === 'none' || textContrast(dis) < 3.0; })(),
       detail: 'opacity=' + cs(dis).opacity + ' cursor=' + cs(dis).cursor},
      {name: ':hover rule exists', ok: (() => {
        try { for (const sh of document.styleSheets) {
          let rs; try { rs = sh.cssRules; } catch (e) { continue; }
          for (const r of rs || [])
            if (r.selectorText && r.selectorText.includes('.btn') &&
                r.selectorText.includes(':hover')) return true; } } catch (e) {}
        return false; })(), detail: 'css :hover scan'},
    ];
  },
  'button-variants': () => {
    const p = q('.btn-primary'), g = q('.btn-ghost'), d = q('.btn-danger');
    return [
      {name: 'primary painted', ok: (() => { const c = parseColor(cs(p).backgroundColor);
        return c && c[3] > 0.8; })(), detail: cs(p).backgroundColor},
      {name: 'primary text >= 4.5:1', ok: textContrast(p) >= 4.5, detail: textContrast(p).toFixed(2)},
      {name: 'ghost transparent or surface bg', ok: (() => {
        const c = parseColor(cs(g).backgroundColor);
        return !c || c[3] < 0.5; })(), detail: cs(g).backgroundColor},
      {name: 'ghost has border', ok: cs(g).borderStyle !== 'none' && parseFloat(cs(g).borderWidth) > 0,
       detail: cs(g).border},
      {name: 'danger is reddish', ok: (() => { const c = parseColor(cs(d).backgroundColor);
        return c && c[0] > c[1] + 30 && c[0] > c[2] + 30; })(),
       detail: cs(d).backgroundColor},
      {name: 'danger text >= 3.0:1', ok: textContrast(d) >= 3.0, detail: textContrast(d).toFixed(2)},
      {name: 'variants same height', ok: Math.abs(rect(p).h - rect(g).h) < 2 &&
        Math.abs(rect(p).h - rect(d).h) < 2,
       detail: rect(p).h.toFixed(0) + '/' + rect(g).h.toFixed(0) + '/' + rect(d).h.toFixed(0)},
    ];
  },
  'form-inputs': () => {
    const inp = q('.input'), sel = q('.select'), inv = q('.is-invalid'), err = q('.field-error');
    return [
      {name: 'input height >= 32px', ok: rect(inp).h >= 32, detail: rect(inp).h.toFixed(0) + 'px'},
      {name: 'input padding >= 8px', ok: parseFloat(cs(inp).paddingLeft) >= 8,
       detail: cs(inp).padding},
      {name: 'input has border', ok: cs(inp).borderStyle !== 'none' && parseFloat(cs(inp).borderWidth) > 0,
       detail: cs(inp).border},
      {name: 'select matches input height', ok: Math.abs(rect(sel).h - rect(inp).h) <= 4,
       detail: rect(sel).h.toFixed(0) + ' vs ' + rect(inp).h.toFixed(0)},
      {name: 'invalid state differs (red border)', ok: (() => {
        const bc = parseColor(cs(inv).borderColor) || [0,0,0,0];
        const nc = parseColor(cs(inp).borderColor) || [0,0,0,0];
        return bc[0] > bc[1] + 30 && bc[0] > bc[2] + 30 &&
          (bc[0] !== nc[0] || bc[1] !== nc[1]); })(),
       detail: 'invalid=' + cs(inv).borderColor + ' normal=' + cs(inp).borderColor},
      {name: 'field-error is red text', ok: (() => {
        const c = parseColor(cs(err).color); return c && c[0] > c[1] + 30; })(),
       detail: cs(err).color},
      {name: 'field-error smaller than body', ok: parseFloat(cs(err).fontSize) <= 14,
       detail: cs(err).fontSize},
    ];
  },
  'interactive-states': () => {
    const btn = q('.btn'), link = q('.link');
    return [
      {name: 'link cursor pointer', ok: cs(link).cursor === 'pointer', detail: cs(link).cursor},
      {name: 'btn cursor pointer', ok: cs(btn).cursor === 'pointer', detail: cs(btn).cursor},
    ];
  },
  'color-contrast': () => [
    {name: 'all badges >= 3.0:1', ok: qa('.badge').every(b => textContrast(b) >= 3.0),
     detail: qa('.badge').map(b => textContrast(b).toFixed(1)).join(',')},
    {name: 'strong >= 4.5:1', ok: textContrast(q('.t-text-strong')) >= 4.5,
     detail: textContrast(q('.t-text-strong')).toFixed(2)},
    {name: 'muted >= 4.5:1', ok: textContrast(q('.t-text-muted')) >= 4.5,
     detail: textContrast(q('.t-text-muted')).toFixed(2)},
  ],
  'breakpoints': () => {
    const cols = qa('.two-col .card');
    const sameTop = Math.abs(rect(cols[0]).y - rect(cols[1]).y) < 2;
    const stacked = rect(cols[1]).y > rect(cols[0]).y + rect(cols[0]).h - 2;
    return [
      {name: innerWidth <= 720 ? 'stacked at narrow' : 'side-by-side at wide',
       ok: innerWidth <= 720 ? stacked : sameTop,
       detail: `y0=${rect(cols[0]).y.toFixed(0)} y1=${rect(cols[1]).y.toFixed(0)}`},
      {name: 'no h-overflow', ok: document.documentElement.scrollWidth <= innerWidth + 1,
       detail: document.documentElement.scrollWidth + '/' + innerWidth},
    ];
  },
  'app-header': () => {
    const hd = q('.app-header'), brand = q('.brand-name'), tag = q('.brand-tag'),
      act = q('.header-actions');
    return [
      {name: 'header is flex', ok: cs(hd).display.includes('flex'), detail: cs(hd).display},
      {name: 'brand h1 > body', ok: parseFloat(cs(brand).fontSize) >= 20,
       detail: cs(brand).fontSize},
      {name: 'actions right-aligned', ok: rect(act).x > rect(brand).x,
       detail: `brand=${rect(brand).x.toFixed(0)} actions=${rect(act).x.toFixed(0)}`},
      {name: 'header bg or border', ok: (() => { const c = parseColor(cs(hd).backgroundColor);
        return (c && c[3] > 0.5) || cs(hd).borderBottomStyle !== 'none'; })(),
       detail: cs(hd).backgroundColor + '/' + cs(hd).borderBottomStyle},
      {name: 'tagline muted >= 3:1', ok: textContrast(tag) >= 3.0,
       detail: textContrast(tag).toFixed(2)},
    ];
  },
  'app-nav': () => {
    const btns = qa('.project-btn'), title = q('.nav-title');
    const lefts = btns.map(b => rect(b).x);
    const spread = Math.max(...lefts) - Math.min(...lefts);
    return [
      {name: 'nav title is h2', ok: title && title.tagName === 'H2', detail: title && title.tagName},
      {name: 'project buttons full-ish width', ok: btns.every(b => rect(b).w >= 120),
       detail: btns.map(b => rect(b).w.toFixed(0)).join(',')},
      {name: 'aligned left edges', ok: spread <= 1.5, detail: spread.toFixed(1) + 'px'},
      {name: 'buttons cursor pointer', ok: btns.every(b => cs(b).cursor === 'pointer'),
       detail: cs(btns[0]).cursor},
      {name: 'selected affordance rule exists (:focus or .active or :hover)',
       ok: (() => { try { for (const sh of document.styleSheets) {
         let rs; try { rs = sh.cssRules; } catch (e) { continue; }
         for (const r of rs || [])
           if (r.selectorText && r.selectorText.includes('.project-btn') &&
               /:hover|:focus|\.active/.test(r.selectorText)) return true; } } catch (e) {}
         return false; })(), detail: 'css scan'},
    ];
  },
  'badge': () => [
    {name: 'all badges >= 3.0:1', ok: qa('.badge').every(b => textContrast(b) >= 3.0),
     detail: qa('.badge').map(b => textContrast(b).toFixed(1)).join(',')},
    {name: 'radius > 0', ok: qa('.badge').every(b => parseFloat(cs(b).borderRadius) > 0),
     detail: cs(qa('.badge')[0]).borderRadius},
    {name: 'priority colors differ', ok: (() => {
      const c = s => cs(q(s)).backgroundColor;
      return c('.badge-high') !== c('.badge-medium') &&
        c('.badge-medium') !== c('.badge-low'); })(), detail: '3 distinct bgs'},
    {name: 'status colors differ', ok: (() => {
      const c = s => cs(q(s)).backgroundColor;
      return c('.badge-done') !== c('.badge-todo') && c('.badge-todo') !== c('.badge-doing'); })(),
     detail: '3 distinct bgs'},
    {name: 'compact (padding <= 8px)', ok: qa('.badge').every(b => parseFloat(cs(b).paddingTop) <= 8),
     detail: cs(qa('.badge')[0]).padding},
  ],
  'progress': () => {
    const bar = q('.progress'), fill = q('.progress-fill'), text = q('.progress-text');
    return [
      {name: 'bar height 4-16px', ok: rect(bar).h >= 4 && rect(bar).h <= 16,
       detail: rect(bar).h.toFixed(0) + 'px'},
      {name: 'bar radius > 0', ok: parseFloat(cs(bar).borderRadius) > 0, detail: cs(bar).borderRadius},
      {name: 'fill painted', ok: (() => { const c = parseColor(cs(fill).backgroundColor);
        return c && c[3] > 0.8; })(), detail: cs(fill).backgroundColor},
      {name: 'fill width 25-75% (demo)', ok: rect(fill).w / rect(bar).w > 0.25 &&
        rect(fill).w / rect(bar).w < 0.75,
       detail: (100 * rect(fill).w / rect(bar).w).toFixed(0) + '%'},
      {name: 'fill differs from bar track', ok: cs(fill).backgroundColor !== cs(bar).backgroundColor,
       detail: cs(fill).backgroundColor + ' vs ' + cs(bar).backgroundColor},
      {name: 'text >= 4.5:1', ok: textContrast(text) >= 4.5, detail: textContrast(text).toFixed(2)},
    ];
  },
  'task-row': () => {
    const rows = qa('.task-row'), lefts = rows.map(r => rect(r).x);
    const spread = Math.max(...lefts) - Math.min(...lefts);
    const done = q('.task-done .task-title');
    return [
      {name: 'rows aligned', ok: spread <= 1.5, detail: spread.toFixed(1) + 'px'},
      {name: 'row padding >= 8px', ok: rows.every(r => parseFloat(cs(r).paddingTop) >= 8),
       detail: cs(rows[0]).padding},
      {name: 'row is flex', ok: rows.every(r => cs(r).display.includes('flex')),
       detail: cs(rows[0]).display},
      {name: 'rows separated (border/gap/shadow)', ok: cs(rows[0]).borderBottomStyle !== 'none' ||
        rect(rows[1]).y > rect(rows[0]).y + rect(rows[0]).h + 3 ||
        cs(rows[0]).backgroundColor !== cs(document.body).backgroundColor,
       detail: 'border=' + cs(rows[0]).borderBottomStyle},
      {name: 'action buttons >= 24px tall', ok: qa('.task-actions .btn').every(b => rect(b).h >= 24),
       detail: qa('.task-actions .btn').map(b => rect(b).h.toFixed(0)).join(',')},
      {name: 'title >= 4.5:1', ok: textContrast(q('.task-title')) >= 4.5,
       detail: textContrast(q('.task-title')).toFixed(2)},
      {name: 'done title muted or struck', ok: (() => {
        return cs(done).textDecorationLine.includes('line-through') ||
          parseFloat(cs(done).opacity) < 1 || textContrast(done) < textContrast(q('.task-title'));
       })(), detail: cs(done).textDecorationLine},
    ];
  },
  'empty-state': () => {
    const es = q('.empty-state'), t = q('.empty-title'), x = q('.empty-text');
    return [
      {name: 'centered', ok: (() => { const r = rect(es), b = rect(document.body);
        return Math.abs((r.x + r.w / 2) - (b.x + b.w / 2)) < 8; })(), detail: 'centered'},
      {name: 'padding >= 24px', ok: parseFloat(cs(es).paddingTop) >= 24, detail: cs(es).paddingTop},
      {name: 'title is h3', ok: t.tagName === 'H3', detail: t.tagName},
      {name: 'text muted >= 3:1', ok: textContrast(x) >= 3.0, detail: textContrast(x).toFixed(2)},
      {name: 'icon present and sized', ok: rect(q('.empty-icon')).w >= 20,
       detail: rect(q('.empty-icon')).w.toFixed(0) + 'px'},
    ];
  },
  'modal': () => {
    const ov = q('.modal-overlay'), md = q('.modal');
    return [
      {name: 'overlay covers viewport', ok: rect(ov).h >= innerHeight - 2,
       detail: rect(ov).h.toFixed(0) + '>=' + innerHeight},
      {name: 'overlay dims (dark translucent)', ok: (() => { const c = parseColor(cs(ov).backgroundColor);
        return c && c[3] > 0 && c[3] < 0.9; })(), detail: cs(ov).backgroundColor},
      {name: 'dialog surface + radius + shadow', ok: (() => { const c = parseColor(cs(md).backgroundColor);
        return c && c[3] > 0.8 && parseFloat(cs(md).borderRadius) > 0 &&
          cs(md).boxShadow !== 'none'; })(), detail: cs(md).boxShadow.slice(0, 24)},
      {name: 'dialog narrower than viewport', ok: rect(md).w < innerWidth - 32,
       detail: rect(md).w.toFixed(0)},
      {name: 'title is h3', ok: q('.modal-title').tagName === 'H3', detail: 'h3'},
      {name: 'actions right-aligned', ok: (() => { const a = q('.modal-actions');
        return cs(a).display.includes('flex') && (cs(a).justifyContent || '').includes('end') ||
          rect(q('.modal-actions .btn-primary')).x > rect(q('.modal input')).x; })(),
       detail: 'flex-end'},
    ];
  },
  'toast': () => {
    const s = q('.toast-success'), e = q('.toast-error');
    return [
      {name: 'success greenish', ok: (() => { const c = parseColor(cs(s).backgroundColor);
        return c && c[1] > c[0] + 20; })(), detail: cs(s).backgroundColor},
      {name: 'error reddish', ok: (() => { const c = parseColor(cs(e).backgroundColor);
        return c && c[0] > c[1] + 20; })(), detail: cs(e).backgroundColor},
      {name: 'both readable >= 3:1', ok: textContrast(s) >= 3.0 && textContrast(e) >= 3.0,
       detail: textContrast(s).toFixed(1) + ',' + textContrast(e).toFixed(1)},
      {name: 'radius > 0', ok: parseFloat(cs(s).borderRadius) > 0, detail: cs(s).borderRadius},
    ];
  },
  'skeleton': () => {
    const l = q('.skeleton-line'), b = q('.skeleton-block');
    return [
      {name: 'skeleton has surface-ish bg (gray)', ok: (() => {
        const c = parseColor(cs(l).backgroundColor);
        return c && c[3] > 0.5; })(), detail: cs(l).backgroundColor},
      {name: 'lines short height', ok: rect(l).h >= 6 && rect(l).h <= 24,
       detail: rect(l).h.toFixed(0) + 'px'},
      {name: 'block taller than lines', ok: rect(b).h > rect(l).h * 2,
       detail: rect(b).h.toFixed(0) + '>' + rect(l).h.toFixed(0)},
      {name: 'animation exists', ok: cs(l).animationName !== 'none',
       detail: cs(l).animationName},
    ];
  },
  'app-shell': () => {
    const side = q('.app-side'), main = q('.app-main'), nav = q('.app-nav');
    const narrow = innerWidth <= 720;
    const sideBySide = rect(main).x >= rect(side).x + rect(side).w - 2;
    const stacked = rect(main).y >= rect(side).y + rect(side).h - 2;
    return [
      {name: narrow ? 'stacked on mobile' : 'sidebar + main side-by-side',
       ok: narrow ? stacked : sideBySide,
       detail: `side=${rect(side).x.toFixed(0)},${rect(side).w.toFixed(0)} main=${rect(main).x.toFixed(0)}`},
      {name: 'no h-overflow', ok: document.documentElement.scrollWidth <= innerWidth + 1,
       detail: document.documentElement.scrollWidth + '/' + innerWidth},
      {name: 'nav list aligned', ok: (() => { const b = qa('.project-btn');
        const ls = b.map(x => rect(x).x);
        return Math.max(...ls) - Math.min(...ls) <= 1.5; })(), detail: 'aligned'},
      {name: 'panel title h2 > body', ok: parseFloat(cs(q('.panel-title')).fontSize) >= 18,
       detail: cs(q('.panel-title')).fontSize},
      {name: 'progress text visible', ok: textContrast(q('.progress')) >= 3.0,
       detail: textContrast(q('.progress')).toFixed(2)},
    ];
  },
};

(async () => {
  const base = arg('base', 'http://127.0.0.1:4190');
  const task = arg('task', null);
  const outPath = arg('out', null);
  if (!task || !TASKS[task]) {
    console.error('unknown task; known: ' + Object.keys(TASKS).join(', '));
    process.exit(1);
  }
  // breakpoints + app-shell need both wide and narrow measurements.
  const widths = (task === 'breakpoints' || task === 'app-shell')
    ? [1440, 390] : [1280];

  const browser = await chromium.launch();
  const all = [];
  for (const w of widths) {
    const ctx = await browser.newContext({viewport: {width: w, height: 900}});
    const page = await ctx.newPage();
    await page.goto(`${base}/h/${task}`, {waitUntil: 'networkidle', timeout: 10000});
    const checks = await page.evaluate(
      `(() => { ${PRELUDE}\nconst fn = ${TASKS[task].toString()}; return fn(); })()`);
    for (const c of checks) all.push({...c, viewport: w});
    await ctx.close();
  }
  await browser.close();
  const passed = all.filter(c => c.ok).length;
  const report = {task, base, when: new Date().toISOString(),
    checks: all, passed, total: all.length, all_passed: passed === all.length};
  for (const c of all) console.log(`  ${c.ok ? 'PASS' : 'FAIL'}  [${c.viewport}] ${c.name} — ${c.detail}`);
  console.log(`component ${task}: ${passed}/${all.length}`);
  if (outPath) { mkdirSync(path.dirname(outPath), {recursive: true});
    writeFileSync(outPath, JSON.stringify(report, null, 1)); }
  process.exit(report.all_passed ? 0 : 2);
})().catch(e => { console.error('fatal:', e); process.exit(1); });
