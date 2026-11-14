import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { hash,grade } from './core.mjs';
import { analyze,generateTargetedTest } from './audit.mjs';
const root=process.cwd(); const id=randomUUID(); const out=path.join(root,'evidence',id);fs.mkdirSync(out,{recursive:true});
function treeHash(dirs){const entries=[];function visit(p){for(const f of fs.readdirSync(p).sort()){const q=path.join(p,f);if(fs.statSync(q).isDirectory())visit(q);else entries.push([path.relative(root,q),hash(fs.readFileSync(q))]);}}dirs.forEach(visit);return hash(entries);}
const sourceHash=treeHash(['app','benchmarks']);
function run(name,args,env={}){
 const start=new Date().toISOString();const file=path.join(out,name+'.json');
 const result=spawnSync(process.execPath,['node_modules/vitest/vitest.mjs','run',...args,'--reporter=json','--outputFile='+file],{encoding:'utf8',timeout:60000,env:{...process.env,...env}});
 fs.writeFileSync(path.join(out,name+'.log'),(result.stdout??'')+(result.stderr??''));
 let report;try{report=JSON.parse(fs.readFileSync(file));}catch{throw Error(name+': missing execution report; never a pass');}
 const rows=report.testResults.flatMap(t=>t.assertionResults??[]);
 const receipt={name,start,command:['vitest','run',...args],exitCode:result.status,error:result.error?.message??null,tests:rows.map(t=>({title:t.fullName??t.title,status:t.status})),reportHash:hash(fs.readFileSync(file)),sourceHash,testHash:treeHash(['tests','auditor/tests']),runId:id};
 fs.writeFileSync(path.join(out,name+'-receipt.json'),JSON.stringify(receipt,null,2));return {result,rows,receipt};
}
const first=run('existing-pass',['tests/coding-existing.test.ts']);
if(first.result.status!==0||first.rows.length<2||first.rows.some(r=>r.status!=='passed'))throw Error('Existing benchmark tests did not pass');
// Test names are a reviewed declaration, not semantic proof. The generated test's negative control supplies actual detectability evidence.
const inventory=first.rows.map(t=>({requirement:(t.fullName??t.title).match(/REQ-[A-Z-]+/)?.[0],status:t.status,assertions:1}));
const requirements=JSON.parse(fs.readFileSync('policy/requirements.json')).requirements;
const audit=analyze(requirements,inventory);
if(!audit.missing.includes('REQ-ISOLATION'))throw Error('Expected genuine missing critical scenario');
generateTargetedTest(audit,path.join(root,'auditor/tests/targeted-authorization.test.ts'));
const probe=spawnSync(process.execPath,['--import','tsx','scripts/probe-disclosure.mjs'],{encoding:'utf8',timeout:15000});
if(probe.status!==0)throw Error('Cross-patient disclosure not confirmed; failure alone is insufficient');
const observation=JSON.parse(probe.stdout);
if(observation.status!==200||observation.returnedPatient!=='patient-b'||observation.returnedLab!=='lab-b')throw Error('Unexpected negative fixture response');
fs.writeFileSync(path.join(out,'disclosure-observation.json'),JSON.stringify(observation,null,2)+'\n');
const bad=run('audit-fail',['auditor/tests/targeted-authorization.test.ts'],{QE_BENCHMARK:'missing-authorization'});
if(bad.result.status!==1||!bad.rows.some(t=>t.status==='failed'))throw Error('Negative control did not fail as intended');
const fixed=run('fixed-pass',['auditor/tests/targeted-authorization.test.ts','tests/authorization.test.ts']);
if(fixed.result.status!==0||fixed.rows.some(t=>t.status!=='passed'))throw Error('Fixed implementation failed');
if(treeHash(['app','benchmarks'])!==sourceHash)throw Error('Source changed during verification');
const criticalGate=grade({risk:'HIGH',criticalViolations:1});
const report={schemaVersion:1,runId:id,sourceHash,kind:'REAL_EXECUTION_DETERMINISTIC_DEMO',sequence:['PASS_INCOMPLETE_TESTS','GAP_IDENTIFIED','FAIL_CRITICAL_GATE','FIXED_IMPLEMENTATION_PASS'],
 audit,criticalGate,disclosureObservation:observation,requirementCoverage:requirements.map(r=>({id:r.id,risk:r.risk,declaredPassed:fixed.rows.some(t=>(t.fullName??t.title).includes(r.id))})),
 stages:[first.receipt,bad.receipt,fixed.receipt],residualRisks:['Synthetic sessions only; not production authentication','This bounded seeded workflow is not agent accuracy measurement','Browser and mutation evidence must be checked separately','Hosted policy requires human bootstrap and branch protection'],
 requiredHumanDecisions:['Review critical requirements and actual assertions','Configure protected quality gate and authorize baseline policy'],
 finalScope:'Authorization slice verified; not a full release approval'};
fs.writeFileSync(path.join(out,'quality-report.json'),JSON.stringify(report,null,2)+'\n');
fs.writeFileSync('evidence/latest-demo.json',JSON.stringify({path:path.relative(root,path.join(out,'quality-report.json')),runId:id},null,2)+'\n');
console.log(JSON.stringify({runId:id,existing:first.rows.length,targetedFailure:bad.rows.length,fixed:fixed.rows.length,criticalGate:criticalGate.status,report:path.relative(root,path.join(out,'quality-report.json'))},null,2));
