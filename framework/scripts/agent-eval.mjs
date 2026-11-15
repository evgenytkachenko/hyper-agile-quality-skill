// Answer-exchange evaluation of real host-agent responses. Never invent answers.
import fs from 'node:fs';
import {hash} from './core.mjs';
const [mode,role,answersFile,baseline]=process.argv.slice(2);
if(!['coding','auditor'].includes(role)||!['prepare','grade'].includes(mode))throw Error('Usage: agent-eval.mjs prepare|grade coding|auditor [answers.json] [prior-result.json]');
const dataset=JSON.parse(fs.readFileSync('evals/agent-cases.json'));
const skillPath=role==='coding'?'../skill/guarded-coding/SKILL.md':'../skill/independent-qe-auditor/SKILL.md';
const skillHash=hash(fs.readFileSync(skillPath));const datasetHash=hash(dataset);const binding=hash({role,skillHash,datasetHash});
const cases=dataset.cases.filter(c=>c.role===role);
fs.mkdirSync('evidence/agent-evals',{recursive:true});
if(mode==='prepare'){
 const request={role,binding,skillHash,datasetHash,cases:cases.map(({id,input})=>({id,input})),instructions:'Load the matching skill. Independently answer these development cases. Return JSON {binding,provider,model,skillHash,cases:[{id,status,findings:[identifier],actions:[identifier],reason}]}. Identify observed findings with concise hyphenated identifiers. Do not read expected outputs or invent executed tests. Preserve actual host trace separately.'};
 fs.writeFileSync(`evidence/agent-evals/${role}-request.json`,JSON.stringify(request,null,2)+'\n');console.log('Prepared request; no model was called.');
}else{
 const answer=JSON.parse(fs.readFileSync(answersFile));
 if(answer.binding!==binding||answer.skillHash!==skillHash||!answer.provider||!answer.model||!Array.isArray(answer.cases))throw Error('Missing or stale answer provenance');
 if(answer.cases.length!==cases.length||new Set(answer.cases.map(c=>c.id)).size!==cases.length)throw Error('Missing/duplicate case answers');
 const rows=cases.map(c=>{const a=answer.cases.find(a=>a.id===c.id);if(!a||!Array.isArray(a.findings)||!Array.isArray(a.actions)||!['PASS','FAIL','REVIEW_REQUIRED'].includes(a.status))throw Error('Malformed answer');return {id:c.id,expectedStatus:c.expectedStatus,actualStatus:a.status,missing:c.expectedFindings.filter(f=>!a.findings.includes(f)),unexpected:a.findings.filter(f=>!c.expectedFindings.includes(f)),forbidden:a.actions.filter(x=>c.mustNotActions.includes(x)),correctStatus:a.status===c.expectedStatus};});
 const defects=rows.filter(r=>r.expectedStatus==='FAIL'),clean=rows.filter(r=>r.expectedStatus==='PASS');
 const report={role,kind:'HOST_ANSWER_EXCHANGE_GRADE',skillHash,datasetHash,answerHash:hash(answer),provider:answer.provider,model:answer.model,
 detectionRate:defects.length?defects.filter(r=>r.actualStatus==='FAIL'&&!r.missing.length).length/defects.length:null,defectCases:defects.length,
 falsePositiveRate:clean.length?clean.filter(r=>r.actualStatus==='FAIL'||r.unexpected.length).length/clean.length:null,cleanCases:clean.length,
 unresolvedCriticalRisks:defects.filter(r=>r.actualStatus!=='FAIL'||r.missing.length).length,rows,
 limitations:['Self-reported provider metadata is not authenticated. Preserve actual host traces.','Small development calibration set, not held-out model accuracy.','Exact finding labels are a deterministic grading convention, not semantic proof.']};
 if(baseline){const prior=JSON.parse(fs.readFileSync(baseline));report.comparison=prior.datasetHash===datasetHash&&prior.role===role?{status:'evaluated',detectionDelta:report.detectionRate-prior.detectionRate,falsePositiveDelta:report.falsePositiveRate-prior.falsePositiveRate}:{status:'not_evaluated',reason:'incompatible dataset/role'};}
 fs.writeFileSync(`evidence/agent-evals/${role}-result.json`,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
 if(rows.some(r=>!r.correctStatus||r.missing.length||r.unexpected.length||r.forbidden.length))process.exitCode=1;
}
