/** Offline by default. Cloud evaluation is explicit, never enabled in CI. */
import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {buildRequest,gradeAnswers} from './agent-task-core.mjs';
import {runProbe} from './agent-tasks.mjs';
import {prepareJudge,assessJudge,callProvider,judgePrompt} from './judge-core.mjs';
const [mode,role,file,...flags]=process.argv.slice(2);
try {
 if(!['prepare','import','provider'].includes(mode)||!['coding','auditor'].includes(role)||!file)throw Error('Usage: npm run evals:judge -- prepare|import|provider coding|auditor answers.json [judge-response.json | --allow-provider --model MODEL]');
 // Always rebuild authoritative inputs and rerun deterministic artifact checks. Never trust an imported grade/request.
 const request=buildRequest(role),answer=JSON.parse(fs.readFileSync(file,'utf8'));
 const grade=await gradeAnswers(request,answer,runProbe);
 const input=prepareJudge(request,answer,grade);
 const dir=path.resolve('evidence/judge',randomUUID());fs.mkdirSync(dir,{recursive:true});
 fs.writeFileSync(path.join(dir,'request.json'),JSON.stringify(input,null,2));
 fs.writeFileSync(path.join(dir,'messages.json'),JSON.stringify(judgePrompt(input),null,2));
 fs.writeFileSync(path.join(dir,'deterministic-grade.json'),JSON.stringify(grade,null,2));
 if(mode==='prepare')console.log(JSON.stringify({mode:'prepared-only',request:path.join(dir,'request.json'),modelInvoked:false},null,2));
 else {
  let response=null,error=null,providerInvocation='not-invoked';
  const model=flags.includes('--model')?flags[flags.indexOf('--model')+1]:undefined;
  try {
   if(mode==='import')response=JSON.parse(fs.readFileSync(flags[0],'utf8'));
   else {
    if(flags.includes('--allow-provider')&&model&&process.env.OPENAI_API_KEY)providerInvocation='attempted';
    response=await callProvider(input,{allowNetwork:flags.includes('--allow-provider'),model,apiKey:process.env.OPENAI_API_KEY});
    providerInvocation='json-response-received';
   }
  }catch(e){error=mode==='provider'?'Provider unavailable, refused, timed out or returned invalid output':`Missing or invalid imported judgment`;}
  if(response)fs.writeFileSync(path.join(dir,'judge-response.json'),JSON.stringify(response,null,2));
  const report=assessJudge(input,response,{mode:mode==='provider'?'provider-response':'imported-response',model:model??'unverified',error});
  report.providerInvocation=mode==='import'?'unverified-import':providerInvocation;
  fs.writeFileSync(path.join(dir,'report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify({report:path.join(dir,'report.json'),status:report.status,deterministicTaskStatus:report.deterministicTaskStatus,releaseApproval:false},null,2));
  if(report.status!=='SUPPORTED'||report.deterministicTaskStatus!=='PASS')process.exitCode=1;
 }
}catch(e){console.error(e.message);process.exitCode=1;}
