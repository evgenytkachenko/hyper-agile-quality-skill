import { createServer as nodeServer, type Server } from 'node:http';
import { canReadLab } from './authorization.js';
import { labs, principalFor } from './data.js';

const page = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Synthetic lab portal</title></head><body>
<h1>Synthetic lab portal</h1><p>Fictional data. Not for clinical use.</p>
<label>Demo session <select id="session"><option value="demo-session-a">Patient A</option><option value="demo-session-b">Patient B</option></select></label>
<label>Lab ID <input id="lab" value="lab-a"></label><button id="load">Load result</button><pre id="result" role="status"></pre>
<script>document.querySelector('#load').onclick=async()=>{const r=await fetch('/api/labs/'+encodeURIComponent(document.querySelector('#lab').value),{headers:{Authorization:'Bearer '+document.querySelector('#session').value}});const data=await r.json();document.querySelector('#result').textContent=r.ok?JSON.stringify(data):'Access denied: '+r.status;};</script></body></html>`;

/** Secure entry point. There is no vulnerable-mode flag. */
export function createServer(): Server {
  return nodeServer((req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    if (req.method === 'GET' && req.url === '/') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); res.end(page); return;
    }
    res.setHeader('Content-Type', 'application/json');
    const finish = (code: number, data: unknown) => { res.writeHead(code); res.end(JSON.stringify(data)); };
    const path = new URL(req.url ?? '/', 'http://localhost').pathname;
    if (req.method !== 'GET' || !path.startsWith('/api/labs/')) { finish(404, { error: 'not_found' }); return; }
    const principal = principalFor(req.headers.authorization);
    if (!principal) { finish(401, { error: 'unauthenticated' }); return; }
    const lab = labs[path.slice('/api/labs/'.length)];
    if (!lab) { finish(404, { error: 'not_found' }); return; }
    if (!canReadLab(principal, lab.patientId)) { finish(403, { error: 'forbidden' }); return; }
    finish(200, lab);
  });
}
