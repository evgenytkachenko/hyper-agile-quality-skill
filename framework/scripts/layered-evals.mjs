/** Synthetic loopback-only lab. Offline execution never constructs a LangSmith client. */
import fs from 'node:fs';
import { randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { createServer } from '../app/server.ts';
import { createVulnerableServer } from '../benchmarks/missing-authorization/server.ts';
import { labs, principalFor } from '../app/data.ts';
import { listen, close } from '../tests/helpers.ts';
import { traceDestination } from './trace-summary.mjs';
import { perform_eval } from '../evals/online-authorization.mjs';

// Reference labels are independent requirements, never derived from observed responses.
export const CASES = Object.freeze([
 {id:'own-a',session:'a',lab:'lab-a',expectedStatus:200,expectedData:true},
 {id:'cross-a-b',session:'a',lab:'lab-b',expectedStatus:403,expectedData:false},
 {id:'cross-b-a',session:'b',lab:'lab-a',expectedStatus:403,expectedData:false},
 {id:'anonymous',session:'none',lab:'lab-a',expectedStatus:401,expectedData:false},
 {id:'unknown-session',session:'invalid',lab:'lab-a',expectedStatus:401,expectedData:false},
 {id:'missing-lab',session:'a',lab:'missing',expectedStatus:404,expectedData:false},
]);
export function selectCase(id) {
 const c=CASES.find(c=>c.id===id); if(!c)throw Error('Unknown synthetic case'); return c;
}
export function gradeOffline(observation, reference) {
 const score=perform_eval({outputs:observation});
 const valid=score.evidence_complete===1;
 return { ...score, authorization_correct:valid ? Number(score.no_unauthorized_disclosure===1 && observation.httpStatus===reference.expectedStatus && observation.dataReturned===reference.expectedData) : null };
}
export async function withFixture(version, fn) {
 if(!['fixed','vulnerable'].includes(version))throw Error('Unknown fixture version');
 const server=version==='fixed'?createServer():createVulnerableServer();
 const base=await listen(server);
 try{return await fn(async id=>{
   const c=selectCase(id);
   const token={a:'demo-session-a',b:'demo-session-b',invalid:'invented',none:null}[c.session];
   const header=token?`Bearer ${token}`:undefined;
   const response=await fetch(`${base}/api/labs/${c.lab}`,{headers:header?{authorization:header}:{},redirect:'error',signal:AbortSignal.timeout(5000)});
   const body=await response.json();
   const principal=principalFor(header);
   const target=labs[c.lab];
   const dataReturned=Object.hasOwn(body,'patientId') || Object.hasOwn(body,'value') || Object.hasOwn(body,'test');
   // Facts from trusted fixture identity + actual response; never export raw body or session.
   return {schema:'synthetic-lab-observation-v1',synthetic:true,implementationVersion:version,
     httpStatus:response.status,authenticated:!!principal,resourceExists:!!target,
     requestedOwnerMatches:target && principal ? target.patientId===principal : null,
     dataReturned,returnedOwnerMatches:dataReturned && principal && typeof body.patientId==='string'?body.patientId===principal:null};
 });}finally{await close(server);}
}
export async function localDataset(version) {
 return withFixture(version,async request=>{
   const rows=[];
   for(const c of CASES){const outputs=await request(c.id);rows.push({caseId:c.id,outputs,scores:gradeOffline(outputs,c)});}
   return {version,rows,correct:rows.filter(r=>r.scores.authorization_correct===1).length,total:rows.length};
 });
}
export async function streamRequests(version,{traceable,client,destination}={}) {
 return withFixture(version,async request=>{
   const run=traceable?traceable(async ({caseId})=>request(caseId),{name:'synthetic-lab-request',run_type:'chain',tracingEnabled:true,client,...destination,metadata:{synthetic:true,eval_schema:'synthetic-lab-observation-v1',implementationVersion:version}}):async ({caseId})=>request(caseId);
   const rows=[];
   for(const c of CASES){const outputs=await run({caseId:c.id});rows.push({caseId:c.id,outputs,localMonitoringScores:perform_eval({outputs})});}
   if(client)await client.awaitPendingTraceBatches();
   return {version,rows,hostedEvaluator:'not-configured-or-verified-by-this-command',traceDelivery:client?'requested-check-dashboard':'not-uploaded'};
 });
}
export function validateExperiment(result,version) {
 const rows=result?.results;
 if(!Array.isArray(rows)||rows.length!==CASES.length)throw Error('Incomplete experiment: expected six result rows');
 const seen=new Set();let correct=0;
 for(const row of rows){
  const c=selectCase(row?.example?.inputs?.caseId);
  if(seen.has(c.id)||row?.run?.error||row?.run?.outputs?.implementationVersion!==version)throw Error('Invalid experiment result');
  seen.add(c.id);
  if(row.example.outputs?.expectedStatus!==c.expectedStatus||row.example.outputs?.expectedData!==c.expectedData)throw Error('Reference labels changed');
  const expected=gradeOffline(row.run.outputs,c);
  if(expected.evidence_complete!==1)throw Error('Incomplete experiment evidence');
  const scores=row.evaluationResults?.results;
  if(!Array.isArray(scores)||scores.length!==Object.keys(expected).length)throw Error('Incomplete evaluator feedback');
  for(const [key,score] of Object.entries(expected)){
   const matches=scores.filter(s=>s.key===key);
   if(matches.length!==1||matches[0].score!==score)throw Error('Missing or inconsistent evaluator feedback');
  }
  correct+=expected.authorization_correct;
 }
 return {correct,total:rows.length};
}
export async function uploadExperiments({client,evaluate}) {
 // Unique dataset prevents accidental duplication within an existing shared dataset.
 const name=`synthetic-lab-authorization-${randomUUID()}`;
 const dataset=await client.createDataset(name,{description:'Six fictional authorization cases; no clinical data. Fixed reference labels.'});
 await client.createExamples(CASES.map(c=>({dataset_id:dataset.id,inputs:{caseId:c.id},outputs:{expectedStatus:c.expectedStatus,expectedData:c.expectedData}})));
 const results=[];
 for(const version of ['vulnerable','fixed']) {
  await withFixture(version,async request=>{
   const result=await evaluate(async inputs=>request(selectCase(inputs.caseId).id),{
    data:name,client,experimentPrefix:`qe-${version}`,maxConcurrency:1,
    metadata:{synthetic:true,implementationVersion:version},
    evaluators:[(run,example)=>{const scores=gradeOffline(run.outputs,example.outputs);return {results:Object.entries(scores).filter(([,v])=>v!==null).map(([key,score])=>({key,score}))};}]
   });
   const summary=validateExperiment(result,version);
   results.push({version,experimentName:result.experimentName,...summary});
  });
 }
 await client.awaitPendingTraceBatches();
 return {datasetName:name,results,delivery:'SDK completed; verify experiments in dashboard'};
}
async function main(){
 const mode=process.argv[2]??'offline';
 const upload=process.argv.includes('--upload-synthetic');
 if(!['offline','online'].includes(mode))throw Error('Mode must be offline or online');
 let adapter={};
 if(upload){
  if(!process.env.LANGSMITH_API_KEY)throw Error('Set LANGSMITH_API_KEY securely, never in source or chat');
  const {Client,AgentAddress}=await import('langsmith');
  const {traceable}=await import('langsmith/traceable');
  const destination=traceDestination(process.env,AgentAddress);
  adapter={client:new Client(),traceable,destination};
 }
 let result;
 if(mode==='offline'&&upload){const {evaluate}=await import('langsmith/evaluation');result=await uploadExperiments({...adapter,evaluate});}
 else if(mode==='offline'){result={mode:'offline-dataset',cloud:false,results:await Promise.all(['vulnerable','fixed'].map(localDataset))};}
 else {result={mode:'online-monitoring-local-traffic',cloud:upload,results:[]};for(const v of ['vulnerable','fixed'])result.results.push(await streamRequests(v,adapter));}
 const id=randomUUID();fs.mkdirSync(`evidence/layered-${id}`,{recursive:true});
 fs.writeFileSync(`evidence/layered-${id}/result.json`,JSON.stringify(result,null,2));
 console.log(JSON.stringify({evidence:`evidence/layered-${id}/result.json`,...result},null,2));
}
if(import.meta.url===pathToFileURL(process.argv[1]??'').href)main().catch(e=>{console.error(e.message);process.exitCode=1;});
