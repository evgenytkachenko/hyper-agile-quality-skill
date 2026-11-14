import {test,expect} from 'vitest';
// @ts-expect-error local JS runtime contract
import {safeSummary,traceSummary} from '../scripts/trace-summary.mjs';
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
