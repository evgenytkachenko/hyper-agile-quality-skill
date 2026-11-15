/** Offline task preparation and grading. No model service or telemetry is contacted. */
import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {buildRequest,gradeAnswers,digest} from './agent-task-core.mjs';
import {withFixture} from './layered-evals.mjs';
export async function runProbe(p){
 const id=p.session==='a'?'cross-a-b':'cross-b-a', observations=[];
 for(const version of ['vulnerable','fixed'])observations.push(await withFixture(version,r=>r(id)));
 const [bad,good]=observations;
 return {kind:'real-http-probe',executed:true,total:2,passed:Number(bad.httpStatus===200&&bad.dataReturned&&bad.returnedOwnerMatches===false)+Number(good.httpStatus===p.expectedStatus&&!good.dataReturned),observations};
}
export async function main(args){
 const [mode,role,file]=args;
 if(!['prepare','grade'].includes(mode)||!['coding','auditor'].includes(role))throw Error('Usage: npm run evals:agents -- prepare|grade coding|auditor [answers.json]');
 const request=buildRequest(role),dir=path.resolve('evidence/agent-tasks',randomUUID());
 if(mode==='prepare'){
  fs.mkdirSync(dir,{recursive:true});fs.writeFileSync(path.join(dir,'request.json'),JSON.stringify(request,null,2));
  console.log(JSON.stringify({mode:'prepared-only',request:path.join(dir,'request.json'),binding:request.binding,next:'Give only request.json to your agent, save its JSON answer, then grade it. No model has been invoked.'},null,2));return;
 }
 if(!file)throw Error('Provide the agent answers JSON file.');
 const answer=JSON.parse(fs.readFileSync(file,'utf8'));
 const grade=await gradeAnswers(request,answer,runProbe);
 // An imported answer is not proof that a live model ran. Never manufacture provenance.
 const report={...grade,executionMode:'imported-agent-response',agentInvocationVerified:false,createdAt:new Date().toISOString(),requestHash:digest(request),runnerHash:digest(fs.readFileSync(new URL(import.meta.url),'utf8'))};
 fs.mkdirSync(dir,{recursive:true});fs.writeFileSync(path.join(dir,'grade.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify({report:path.join(dir,'grade.json'),taskPassRate:report.taskPassRate,unresolvedCriticalTasks:report.unresolvedCriticalTasks,agentInvocationVerified:false,toolBehavior:'NOT_EVALUATED'},null,2));
 if(report.taskPassRate!==1)process.exitCode=1;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)main(process.argv.slice(2)).catch(e=>{console.error(e.message);process.exitCode=1;});
