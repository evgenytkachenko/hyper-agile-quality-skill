/** DELIBERATELY VULNERABLE BENCHMARK. No public listener or normal-app import. */
import { createServer, type Server } from 'node:http';
import { labs, principalFor } from '../../app/data.js';
export function createVulnerableServer(): Server {
  return createServer((req, res) => {
    res.setHeader('Content-Type', 'application/json');
    const finish = (code: number, value: unknown) => { res.writeHead(code); res.end(JSON.stringify(value)); };
    const path = new URL(req.url ?? '/', 'http://localhost').pathname;
    if (req.method !== 'GET' || !path.startsWith('/api/labs/')) { finish(404, { error: 'not_found' }); return; }
    if (!principalFor(req.headers.authorization)) { finish(401, { error: 'unauthenticated' }); return; }
    const lab = labs[path.slice('/api/labs/'.length)];
    if (!lab) { finish(404, { error: 'not_found' }); return; }
    // Seeded bug: authenticated principal is never checked against the lab owner.
    finish(200, lab);
  });
}
