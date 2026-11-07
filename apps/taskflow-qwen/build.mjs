// TRUSTED-SCAFFOLD build: bundles the Qwen-authored React app with
// esbuild and emits the Qwen-authored CSS string as style.css.
// Uses createRequire so NODE_PATH resolution works without a local
// node_modules install.
import {writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
const require = createRequire(import.meta.url);
const {build} = require('esbuild');

await build({
  entryPoints: ['client/main.jsx'],
  bundle: true,
  outfile: 'public/app.js',
  format: 'iife',
  jsx: 'transform',
  logLevel: 'warning',
  minify: false,
  external: [],
});

// css module (Qwen bytes) -> style.css (deterministic string extraction)
const cssModule = require('./client/style.js');
const css = typeof cssModule === 'string' ? cssModule : String(cssModule);
writeFileSync('public/style.css', css);
console.log('built public/app.js and public/style.css');
