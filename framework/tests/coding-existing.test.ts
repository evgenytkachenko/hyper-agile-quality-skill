/** Intentionally incomplete benchmark tests: they omit cross-patient requests. */
import { beforeAll, afterAll, it, expect } from 'vitest';
import { createVulnerableServer } from '../benchmarks/missing-authorization/server.js';
import { listen, close } from './helpers.js';
const server = createVulnerableServer(); let base: string;
beforeAll(async () => { base = await listen(server); });
afterAll(async () => { await close(server); });
it('REQ-OWN-LAB own lab happy path passes despite hidden defect', async () => {
  const response = await fetch(`${base}/api/labs/lab-a`, { headers: { authorization:'Bearer demo-session-a' } });
  expect(response.status).toBe(200); expect((await response.json()).id).toBe('lab-a');
});
it('REQ-AUTH missing session denied', async () => {
  expect((await fetch(`${base}/api/labs/lab-a`)).status).toBe(401);
});
