// Serves recovery/session034-fixed (the patched copies). See preview server.
'use strict';
import {createServer} from 'node:http';
import {readFileSync, existsSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)));
const PORT = 4196;
const TYPES = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8', '.jsx': 'text/plain; charset=utf-8',
  '.png': 'image/png', '.svg': 'image/svg+xml'};
createServer((req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p === '/') p = '/taskflow-v2/index.html';
  // /vendor lives in session034-preview (identical copies)
  let file = path.join(ROOT, p.replace(/\.\./g, ''));
  if (!existsSync(file) && p.startsWith('/vendor'))
    file = path.join(ROOT, '..', 'session034-preview', p.replace(/\.\./g, ''));
  if (existsSync(file)) {
    res.writeHead(200, {'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream'});
    return res.end(readFileSync(file));
  }
  res.writeHead(404); res.end('not found: ' + p);
}).listen(PORT, '127.0.0.1', () => console.log(`fixed server on http://127.0.0.1:${PORT}`));
