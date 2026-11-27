import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { api } from './api.js';

const root = fileURLToPath(new URL('../', import.meta.url));
const dist = resolve(root, 'dist');
const port = Number(process.env.PORT || 4173);
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.png': 'image/png' };

async function serveBuild(req, res) {
  try {
    const path = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    const file = resolve(dist, '.' + (path === '/' ? '/index.html' : path));
    if (!file.startsWith(dist + sep)) throw new Error();
    const data = await readFile(file);
    res.writeHead(200, { 'Content-Type': types[extname(file)] || 'application/octet-stream' });
    res.end(data);
  } catch {
    res.writeHead(404).end('File unavailable. Run npm run build before npm start.');
  }
}

const server = http.createServer({ requestTimeout: 15_000 });
let serveUI = serveBuild;
if (process.argv.includes('--dev')) {
  const { createServer } = await import('vite');
  const vite = await createServer({ root, server: { middlewareMode: true, hmr: { server } } });
  serveUI = (req, res) => vite.middlewares(req, res);
}
server.on('request', (req, res) => {
  if (req.url.startsWith('/api/')) return void api(req, res);
  serveUI(req, res);
});
server.listen(port, '127.0.0.1', () => console.log(`SaaSLens is running at http://127.0.0.1:${port}`));
