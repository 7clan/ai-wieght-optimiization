// Serve the recovered Session 034 preview apps for re-verification.
// Maps /vendor to the recovered vendor dir so the apps' absolute
// references work.  TRUSTED-SCAFFOLD test tooling (recovery session).
'use strict';
import {createServer} from 'node:http';
import {readFileSync, existsSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)));
const PORT = Number(process.env.PORT || 4195);
const TYPES = {'.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.jsx': 'text/plain; charset=utf-8', '.png': 'image/png',
  '.svg': 'image/svg+xml'};

createServer((req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p === '/') p = '/taskflow-v2/index.html';
  const file = path.join(ROOT, p.replace(/\.\./g, ''));
  if (existsSync(file) && file.startsWith(ROOT)) {
    res.writeHead(200, {'Content-Type': TYPES[path.extname(file)] ||
      'application/octet-stream'});
    return res.end(readFileSync(file));
  }
  res.writeHead(404); res.end('not found: ' + p);
}).listen(PORT, '127.0.0.1', () =>
  console.log(`recovery server on http://127.0.0.1:${PORT}`));
