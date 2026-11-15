import {test,expect} from 'vitest';
// @ts-expect-error local JS runtime contract
import {safeSummary,traceSummary,traceDestination} from '../scripts/trace-summary.mjs';
const report={kind:'REAL_EXECUTION_DETERMINISTIC_DEMO',secret:'do-not-upload',stages:[0,1,0].map(exitCode=>({exitCode,tests:[{title:'private data'}],source:'sensitive'}))};
test('default is offline even with ambient tracing flag',async()=>{process.env.LANGSMITH_TRACING='true';expect((await traceSummary(report)).uploaded).toBe(false);delete process.env.LANGSMITH_TRACING;});
test('trace only contains allowlisted fields',()=>{const text=JSON.stringify(safeSummary(report));expect(text).not.toContain('private');expect(text).not.toContain('secret');expect(text).not.toContain('source');});
test('explicit tracing calls stages and flushes',async()=>{const calls:string[]=[];let flush=false;const traceable=(f:Function,o:{name:string})=>async(v:unknown)=>{calls.push(o.name);return f(v);};await traceSummary(report,{enabled:true,traceable,client:{awaitPendingTraceBatches:async()=>{flush=true;}}});expect(calls).toHaveLength(4);expect(flush).toBe(true);});
test('invalid evidence rejected',()=>expect(()=>safeSummary({})).toThrow());
test('flush failure not reported as successful upload',async()=>{await expect(traceSummary(report,{enabled:true,traceable:(f:Function)=>f,client:{awaitPendingTraceBatches:async()=>{throw Error('offline');}}})).rejects.toThrow('offline');});
test('installed SDK supports explicitly disabled tracing without network',async()=>{
 const {traceable}=await import('langsmith/traceable');
 const previous=globalThis.fetch;let calls=0;
 globalThis.fetch=(async()=>{calls++;throw Error('unexpected network');}) as typeof fetch;
 try{const f=traceable(async(x:number)=>x+1,{name:'offline-sdk-check',tracingEnabled:false});expect(await f(2)).toBe(3);expect(calls).toBe(0);}finally{globalThis.fetch=previous;}
});

test('installed SDK validates explicit agent destination',async()=>{
 const {AgentAddress}=await import('langsmith');
 expect(traceDestination({LANGSMITH_AGENT_ID:'qe-demo',LANGSMITH_AGENT_ENVIRONMENT:'local'},AgentAddress).address).toMatchObject({kind:'AGENT',id:'qe-demo',environment:'LOCAL'});
 expect(()=>traceDestination({LANGSMITH_AGENT_ID:'qe-demo'},AgentAddress)).toThrow('both');
 expect(()=>traceDestination({LANGSMITH_AGENT_ID:'qe-demo',LANGSMITH_AGENT_ENVIRONMENT:'local',LANGSMITH_PROJECT:'old'},AgentAddress)).toThrow('Unset');
 expect(()=>traceDestination({LANGSMITH_AGENT_ID:'invalid id',LANGSMITH_AGENT_ENVIRONMENT:'local'},AgentAddress)).toThrow();
 expect(()=>traceDestination({},AgentAddress)).toThrow('explicitly');
 expect(traceDestination({LANGSMITH_PROJECT:'legacy'},AgentAddress)).toEqual({project_name:'legacy'});
});
test('real SDK sends agent address and safe data to mock client only',async()=>{
 const {AgentAddress}=await import('langsmith');const {traceable}=await import('langsmith/traceable');
 const runs:any[]=[];let flush=false;
 const client={createRun:async(r:any)=>{runs.push(r);},updateRun:async()=>{},awaitPendingTraceBatches:async()=>{flush=true;}};
 const previous=globalThis.fetch;
 globalThis.fetch=(async()=>{throw Error('network forbidden');}) as typeof fetch;
 try{
  await traceSummary(report,{enabled:true,traceable,client,destination:{address:new AgentAddress('qe-demo','local')}});
  expect(runs).toHaveLength(4);
  for(const run of runs)expect(run.address).toMatchObject({kind:'AGENT',id:'qe-demo',environment:'LOCAL'});
  expect(JSON.stringify(runs)).not.toContain('do-not-upload');expect(flush).toBe(true);
 }finally{globalThis.fetch=previous;}
});
