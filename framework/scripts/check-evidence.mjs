// Fail-closed local evidence consistency check; not a signature/trusted CI boundary.
import fs from 'node:fs';
import path from 'node:path';
import {hash,validateBrowser} from './core.mjs';
function treeHash(dirs){const entries=[];function visit(p){for(const f of fs.readdirSync(p).sort()){const q=path.join(p,f);if(fs.statSync(q).isDirectory())visit(q);else entries.push([q,hash(fs.readFileSync(q))]);}}dirs.forEach(visit);return hash(entries);}
const latest=JSON.parse(fs.readFileSync('evidence/latest-demo.json'));
if(typeof latest.path!=='string'||!/^evidence\/[a-f0-9-]+\/quality-report\.json$/.test(latest.path))throw Error('Unexpected report path');
const demo=JSON.parse(fs.readFileSync(latest.path));
if(demo.runId!==latest.runId||demo.sourceHash!==treeHash(['app','benchmarks']))throw Error('Stale source/run evidence');
if(demo.disclosureObservation?.status!==200||demo.disclosureObservation?.returnedPatient!=='patient-b'||demo.disclosureObservation?.returnedLab!=='lab-b')throw Error('Missing actual disclosure observation');
if(demo.criticalGate.status!=='FAIL'||demo.stages[1].exitCode!==1||demo.stages[2].exitCode!==0)throw Error('Missing expected negative/fixed execution');
if(demo.stages[2].testHash!==treeHash(['tests','auditor/tests']))throw Error('Tests changed since verification');
for(const stage of demo.stages){
 if(stage.runId!==demo.runId||stage.sourceHash!==demo.sourceHash||stage.error!==null||!stage.tests.length)throw Error('Invalid stage evidence');
 const f=path.join(path.dirname(latest.path),stage.name+'.json');
 if(hash(fs.readFileSync(f))!==stage.reportHash)throw Error('Test report changed');
 const report=JSON.parse(fs.readFileSync(f));
 const rows=report.testResults.flatMap(t=>t.assertionResults??[]).map(t=>({title:t.fullName??t.title,status:t.status}));
 if(JSON.stringify(rows)!==JSON.stringify(stage.tests))throw Error('Reported cases differ from execution report');
}
const receipt=JSON.parse(fs.readFileSync('reports/mutation/receipt.json'));
if(receipt.runId!==demo.runId||receipt.toolVersion!==JSON.parse(fs.readFileSync('node_modules/@stryker-mutator/core/package.json')).version||receipt.exitCode!==0||receipt.error!==null||receipt.reportHash!==hash(fs.readFileSync('reports/mutation/mutation.json')))throw Error('Missing/failed mutation execution');
for(const f of ['app/authorization.ts','tests/policy.test.ts','vitest.mutation.config.ts','stryker.config.json','package-lock.json'])if(receipt.inputs[f]!==hash(fs.readFileSync(f)))throw Error('Stale mutation inputs');
const mutations=JSON.parse(fs.readFileSync('reports/mutation/mutation.json'));
const files=Object.entries(mutations.files);
if(files.length!==1||files[0][0]!=='app/authorization.ts'||files[0][1].source!==fs.readFileSync('app/authorization.ts','utf8'))throw Error('Mutation source mismatch');
const all=files.flatMap(([,f])=>f.mutants);
if(!all.length||all.some(m=>m.status!=='Killed'))throw Error('Mutation survivor, timeout, no coverage, invalid or missing mutants: human investigation required');
console.log(JSON.stringify({status:'PASS',scope:'bound local demo + selective mutation consistency checks',mutants:all.length,releaseApproval:false,limitation:'Not signed; a consistent malicious rewrite is outside this check'}));

let browser={status:'NOT_VERIFIED',passed:0,failed:0};
try{
 const raw=fs.readFileSync('reports/browser.json');const b=JSON.parse(raw);
 const receipt=JSON.parse(fs.readFileSync('reports/browser-receipt.json'));
 const bound=['app/server.ts','app/data.ts','app/authorization.ts','app/main.ts','tests/browser.spec.ts','playwright.config.ts','package-lock.json'];
 const inputs=Object.fromEntries(bound.map(p=>[p,hash(fs.readFileSync(p))]));
 browser={status:validateBrowser(b,receipt,inputs,demo.runId,hash(raw))?'PASS':'NOT_VERIFIED',passed:b.stats?.expected??0,failed:b.stats?.unexpected??0};
}catch{}

const final={status:'REVIEW_REQUIRED',deterministicCore:'PASS',browser,requirementCoverage:demo.requirementCoverage,detectedDefects:[{requirement:'REQ-ISOLATION',fixture:'isolated-benchmark',status:'detected'}],mutation:{total:all.length,killed:all.length},supportingEvidence:{demo:latest.path,mutation:'reports/mutation/mutation.json'},residualRisks:demo.residualRisks,requiredHumanDecisions:demo.requiredHumanDecisions,releaseApproval:false};
fs.writeFileSync('evidence/quality-report.json',JSON.stringify(final,null,2)+'\n');
if(process.argv.includes('--require-browser')&&browser.status!=='PASS')throw Error('Browser evidence not verified');
