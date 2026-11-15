import {describe,it,expect,vi,afterEach} from 'vitest';
// @ts-expect-error JavaScript exercise module
import {CASES,localDataset,streamRequests,selectCase,gradeOffline,uploadExperiments,validateExperiment} from '../scripts/layered-evals.mjs';
// @ts-expect-error portable JS evaluator
import {perform_eval} from '../evals/online-authorization.mjs';
afterEach(()=>vi.unstubAllGlobals());
describe('layered evaluation',()=>{
 it('executes real HTTP and detects both cross-patient leaks only in benchmark',async()=>{
  const bad=await localDataset('vulnerable');const good=await localDataset('fixed');
  expect(bad.correct).toBe(4);expect(good.correct).toBe(6);
  expect(bad.rows.filter((r:any)=>r.scores.no_unauthorized_disclosure===0).map((r:any)=>r.caseId)).toEqual(['cross-a-b','cross-b-a']);
 });
 it('local monitoring never contacts cloud even when global tracing is on',async()=>{
  const old=process.env.LANGSMITH_TRACING;process.env.LANGSMITH_TRACING='true';
  const original=globalThis.fetch;
  vi.stubGlobal('fetch',(url:any,opts:any)=>{expect(String(url)).toMatch(/^http:\/\/127\.0\.0\.1:\d+\/api\/labs\//);return original(url,opts);});
  try{const r=await streamRequests('fixed');expect(r.traceDelivery).toBe('not-uploaded');expect(r.rows).toHaveLength(6);}finally{if(old===undefined)delete process.env.LANGSMITH_TRACING;else process.env.LANGSMITH_TRACING=old;}
 });
 it.each([undefined,{}, {schema:'wrong'}, {schema:'synthetic-lab-observation-v1',synthetic:'true'}])('missing or malformed evidence cannot pass: %j',o=>{
  expect(perform_eval({outputs:o})).toEqual({evidence_complete:0});
 });
 it('wrong returned owner cannot pass an otherwise successful own-resource request',async()=>{
  const r=await localDataset('fixed');
  const output={...r.rows[0].outputs,returnedOwnerMatches:false};
  expect(gradeOffline(output,CASES[0])).toEqual({evidence_complete:1,no_unauthorized_disclosure:0,authorization_invariant:0,authorization_correct:0});
 });
 it('never grades missing evidence as correct',()=>expect(gradeOffline({},CASES[0]).authorization_correct).toBeNull());
 it('rejects arbitrary case ids and versions',async()=>{expect(()=>selectCase('https://example.com')).toThrow();await expect(localDataset('prod')).rejects.toThrow();});
 it('exports only bounded safe facts',async()=>{
  const r=await localDataset('fixed');
  for(const row of r.rows){expect(Object.keys(row.outputs).sort()).toEqual(['schema','synthetic','implementationVersion','httpStatus','authenticated','resourceExists','requestedOwnerMatches','dataReturned','returnedOwnerMatches'].sort());}
  expect(JSON.stringify(r)).not.toContain('demo-session');expect(JSON.stringify(r)).not.toContain('glucose');
 });
 it('cloud dataset orchestration uses independent labels and two real implementations with stubbed cloud only',async()=>{
  const created:any[]=[];const invocations:any[]=[];
  const client={createDataset:async(name:string)=>({id:'fake-dataset',name}),createExamples:async(rows:any)=>created.push(...rows),awaitPendingTraceBatches:async()=>{}};
  const evaluate=async(target:any,options:any)=>{
   const rows:any[]=[];for(const e of created){const output=await target(e.inputs);const scores=options.evaluators[0]({outputs:output},{outputs:e.outputs});rows.push({example:e,run:{outputs:output},evaluationResults:scores});}
   invocations.push({prefix:options.experimentPrefix,rows});
   return {experimentName:options.experimentPrefix,results:rows};
  };
  const result=await uploadExperiments({client,evaluate});
  expect(result.results.map((r:any)=>r.correct)).toEqual([4,6]);
  expect(()=>validateExperiment({results:[]},'fixed')).toThrow();
  const rows=invocations[1].rows;
  expect(()=>validateExperiment({results:rows.map((r:any,i:number)=>i===0?{...r,run:{...r.run,error:'target failed'}}:r)},'fixed')).toThrow();
  expect(()=>validateExperiment({results:rows.map((r:any,i:number)=>i===0?{...r,evaluationResults:{results:[]}}:r)},'fixed')).toThrow();
  expect(created).toHaveLength(6);expect(created[1].outputs.expectedStatus).toBe(403);
  expect(invocations[0].rows[1].evaluationResults.results.find((s:any)=>s.key==='authorization_correct').score).toBe(0);
  expect(invocations[1].rows[1].evaluationResults.results.find((s:any)=>s.key==='authorization_correct').score).toBe(1);
 });
});
