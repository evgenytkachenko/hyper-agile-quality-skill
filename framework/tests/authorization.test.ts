import { beforeAll, afterAll, describe, it, expect } from 'vitest';
import { createServer } from '../app/server.js';
import { listen, close } from './helpers.js';
const server = createServer(); let base: string;
beforeAll(async () => { base = await listen(server); });
afterAll(async () => { await close(server); });
describe('real HTTP authorization regressions', () => {
  it('REQ-OWN-LAB returns own lab', async () => {
    const response = await fetch(`${base}/api/labs/lab-a`, { headers: { authorization: 'Bearer demo-session-a' } });
    expect(response.status).toBe(200); expect(await response.json()).toEqual({ id:'lab-a', patientId:'patient-a', test:'Synthetic glucose', value:90, unit:'mg/dL' });
  });
  it('REQ-AUTH rejects absent identity', async () => {
    const response = await fetch(`${base}/api/labs/lab-a`); expect(response.status).toBe(401); expect(await response.json()).toEqual({ error:'unauthenticated' });
  });
  it('REQ-ISOLATION Patient A cannot read B even with forged patient ID', async () => {
    const response = await fetch(`${base}/api/labs/lab-b?patientId=patient-b`, { headers: { authorization: 'Bearer demo-session-a', 'x-patient-id': 'patient-b' } });
    expect(response.status).toBe(403); expect(await response.json()).toEqual({ error:'forbidden' });
  });
  it('REQ-ISOLATION Patient B cannot read A', async () => {
    const response = await fetch(`${base}/api/labs/lab-a`, { headers: { authorization:'Bearer demo-session-b' } });
    expect(response.status).toBe(403); expect(await response.json()).toEqual({ error:'forbidden' });
  });
  it('REQ-AUTH rejects an invented session', async () => {
    const response = await fetch(`${base}/api/labs/lab-a`, { headers: { authorization:'Bearer patient-a' } });
    expect(response.status).toBe(401);
  });
  it('REQ-AUTH rejects object prototype names as sessions', async () => {
    const response = await fetch(`${base}/api/labs/lab-a`, { headers: { authorization:'Bearer __proto__' } });
    expect(response.status).toBe(401);
  });
});
