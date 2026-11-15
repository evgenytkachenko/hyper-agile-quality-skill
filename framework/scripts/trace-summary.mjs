// Optional LangSmith summary trace. Never sends raw reports, source, patient records or logs.
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';
export function safeSummary(report) {
  if (!report || report.kind!=='REAL_EXECUTION_DETERMINISTIC_DEMO' || !Array.isArray(report.stages) || report.stages.length!==3) throw Error('Expected three-stage synthetic demo report');
  const stages=report.stages.map((s,i)=>{
    if(!Number.isInteger(s.exitCode)||!Array.isArray(s.tests))throw Error('Invalid stage');
    return {stage:['existing-tests','gap-negative-control','fixed-tests'][i],exitCode:s.exitCode,testCount:s.tests.length};
  });
  return {kind:'synthetic-qe-demo',stages,releaseApproval:false};
}
// Validate before constructing a client: the SDK may only warn on incomplete env settings.
export function traceDestination(env, AgentAddress) {
  const id=env.LANGSMITH_AGENT_ID;
  const environment=env.LANGSMITH_AGENT_ENVIRONMENT;
  const legacy=['LANGSMITH_PROJECT','LANGCHAIN_PROJECT','LANGCHAIN_SESSION'].filter(k=>env[k]);
  if(id || environment) {
    if(!id || !environment) throw Error('Set both LANGSMITH_AGENT_ID and LANGSMITH_AGENT_ENVIRONMENT');
    if(legacy.length) throw Error('Unset legacy project variables before using agent addressing');
    return {address:new AgentAddress(id,environment)};
  }
  const projects=legacy.map(k=>env[k]);
  if(!projects.length) throw Error('Set an agent ID/environment pair or LANGSMITH_PROJECT explicitly');
  if(new Set(projects).size!==1) throw Error('Conflicting legacy project variables');
  return {project_name:projects[0]};
}
export async function traceSummary(report, {enabled=false, traceable, client, destination={}}={}) {
  const safe=safeSummary(report);
  if (!enabled) return {mode:'offline',summary:safe,uploaded:false};
  if(!traceable||!client)throw Error('Explicit LangSmith adapter required');
  const step=traceable(async value=>value,{name:'qe-stage',tracingEnabled:true,client,...destination});
  const pipeline=traceable(async summary=>{
    for(const stage of summary.stages)await step(stage);
    return {stages:summary.stages.length,releaseApproval:false};
  },{name:'synthetic-qe-verification',tracingEnabled:true,client,...destination});
  const result=await pipeline(safe);
  await client.awaitPendingTraceBatches();
  return {mode:'langsmith',result,uploaded:'requested-not-independently-confirmed'};
}
if(import.meta.url===pathToFileURL(process.argv[1]??'').href){
 const latest=JSON.parse(fs.readFileSync('evidence/latest-demo.json'));
 const report=JSON.parse(fs.readFileSync(latest.path));
 const enabled=process.argv.includes('--upload-synthetic-summary');
 let adapter={};
 if(enabled){
   if(!process.env.LANGSMITH_API_KEY)throw Error('Set LANGSMITH_API_KEY securely; never put it in source or chat');
   const {Client,AgentAddress}=await import('langsmith');const {traceable}=await import('langsmith/traceable');
   const destination=traceDestination(process.env,AgentAddress);
   adapter={traceable,client:new Client(),destination};
 }
 console.log(JSON.stringify(await traceSummary(report,{enabled,...adapter}),null,2));
}
