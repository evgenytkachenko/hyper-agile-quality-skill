import { test, expect } from 'vitest';
import { createServer } from '../../app/server.js';
import { createVulnerableServer } from '../../benchmarks/missing-authorization/server.js';
test('REQ-ISOLATION generated gap test: A cannot read B', async () => {
  const server = process.env.QE_BENCHMARK === 'missing-authorization' ? createVulnerableServer() : createServer();
  await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));
  try {
    const port=(server.address() as import('node:net').AddressInfo).port;
    const response=await fetch('http://127.0.0.1:'+port+'/api/labs/lab-b',{headers:{Authorization:'Bearer demo-session-a'}});
    expect(response.status).toBe(403);
    const text=await response.text();
    expect(text).not.toContain('patient-b');
    expect(text).not.toContain('lab-b');
  } finally { await new Promise<void>((r,j)=>server.close(e=>e?j(e):r())); }
});
