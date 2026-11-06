// TRUSTED-SCAFFOLD build: bundles the Qwen-authored React app with
// esbuild and emits the Qwen-authored CSS string as style.css.
import {build} from 'esbuild';
import {writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
const require = createRequire(import.meta.url);

await build({
  entryPoints: ['client/main.jsx'],
  bundle: true,
  outfile: 'public/app.js',
  format: 'iife',
  jsx: 'transform',
  logLevel: 'info',
  minify: false,
});

// css module (Qwen bytes) -> style.css (deterministic string extraction)
const cssModule = require('./client/style.js');
const css = typeof cssModule === 'string' ? cssModule : String(cssModule);
writeFileSync('public/style.css', css);
console.log('built public/app.js and public/style.css');
