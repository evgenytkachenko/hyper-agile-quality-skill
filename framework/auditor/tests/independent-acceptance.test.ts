// Native independent QE review proposal; imports and fixture selection adapted for isolated runs.
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createServer } from '../../app/server.js';
import { createVulnerableServer } from '../../benchmarks/missing-authorization/server.js';
import { close, listen } from '../../tests/helpers.js';
const fixtures = [
  { token: 'demo-session-a', lab: { id: 'lab-a', patientId: 'patient-a', test: 'Synthetic glucose', value: 90, unit: 'mg/dL' } },
  { token: 'demo-session-b', lab: { id: 'lab-b', patientId: 'patient-b', test: 'Synthetic glucose', value: 185, unit: 'mg/dL' } },
];
const factory = process.env.QE_BENCHMARK === 'missing-authorization' ? createVulnerableServer : createServer;
describe('native independent acceptance proposal', () => {
 const server = factory(); let base: string;
 beforeAll(async()=>{base=await listen(server);}); afterAll(async()=>{await close(server);});
 for(const own of fixtures){
  it(`REQ-OWN-LAB complete owned record ${own.lab.id}`,async()=>{
   const response=await fetch(`${base}/api/labs/${own.lab.id}`,{headers:{authorization:`Bearer ${own.token}`}}); // fictional token-shaped session fixture
   expect(response.status).toBe(200);expect(await response.json()).toEqual(own.lab);
  });
  const other=fixtures.find(f=>f.token!==own.token)!;
  it(`REQ-ISOLATION denies ${own.token} access to ${other.lab.id}`,async()=>{
   const response=await fetch(`${base}/api/labs/${other.lab.id}`,{headers:{authorization:`Bearer ${own.token}`}}); // fictional token-shaped session fixture
   const body=await response.json();expect.soft([403,404]).toContain(response.status);
   expect(Object.keys(body)).toEqual(['error']);expect(typeof body.error).toBe('string');
   expect(JSON.stringify(body)).not.toContain(other.lab.patientId);expect(JSON.stringify(body)).not.toContain(other.lab.id);
  });
 }
 for(const authorization of [undefined,'Bearer unknown-session','Bearer ','Basic demo-session-a','Bearer toString']){
  for(const fixture of fixtures){
   it(`REQ-AUTH denies ${String(authorization)} for ${fixture.lab.id}`,async()=>{
    const headers:Record<string,string>={};if(authorization!==undefined)headers.authorization=authorization; // fictional token-shaped session fixture
    const response=await fetch(`${base}/api/labs/${fixture.lab.id}`,{headers});
    expect.soft(response.status).toBe(401);expect(await response.json()).toEqual({error:'unauthenticated'});
   });
  }
 }
});
