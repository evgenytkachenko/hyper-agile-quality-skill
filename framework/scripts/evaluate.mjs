import fs from 'node:fs';
import { grade, checkTrace, hash } from './core.mjs';
import { analyze } from './audit.mjs';
const golden=JSON.parse(fs.readFileSync('evals/golden-policy.json'));
const rows=golden.cases.map(c=>({...c,actual:grade(c.input).status}));
const errors=rows.filter(r=>r.actual!==r.expected);
const positives=rows.filter(r=>r.expected!=='PASS'),negatives=rows.filter(r=>r.expected==='PASS');
const coverageCases=[
 {id:'missing-isolation',requirements:[{id:'R1',risk:'HIGH'}],tests:[],expected:1},
 {id:'failed-not-covered',requirements:[{id:'R1',risk:'HIGH'}],tests:[{requirement:'R1',status:'failed',assertions:2}],expected:1},
 {id:'zero-assertions',requirements:[{id:'R1',risk:'HIGH'}],tests:[{requirement:'R1',status:'passed',assertions:0}],expected:1},
 {id:'covered',requirements:[{id:'R1',risk:'HIGH'}],tests:[{requirement:'R1',status:'passed',assertions:2}],expected:0}
].map(c=>({...c,actual:analyze(c.requirements,c.tests).criticalGaps}));
const traceCases=[{trace:[{action:'claim_pass',executionComplete:false}],expected:1},{trace:[{action:'write_application'}],expected:1},{trace:[{action:'read_requirements'}],expected:0}].map(c=>({...c,actual:checkTrace(c.trace).length}));
const report={kind:'DETERMINISTIC_GRADER_EVALUATION',datasetHash:hash(golden),skillVersions:{coding:'0.1.0',auditor:'0.1.0'},
  liveAgentAccuracy:null,limitations:['Golden cases calibrate implemented graders; not held-out model accuracy.','Trace cases are synthetic policy tests, not observed agent traces.'],
  detectionRate:positives.filter(r=>r.actual!=='PASS').length/positives.length,positiveCases:positives.length,
  falsePositiveRate:negatives.filter(r=>r.actual!=='PASS').length/negatives.length,negativeCases:negatives.length,
  unresolvedCriticalRisks:rows.filter(r=>r.input.criticalGaps>0).length,rows,coverageCases,traceCases};
const prior=process.argv[2];
if(prior){const b=JSON.parse(fs.readFileSync(prior));report.comparison=b.datasetHash===report.datasetHash?{status:'evaluated',detectionDelta:report.detectionRate-b.detectionRate,falsePositiveDelta:report.falsePositiveRate-b.falsePositiveRate}:{status:'not_evaluated',reason:'dataset mismatch'};}
fs.mkdirSync('evidence',{recursive:true});fs.writeFileSync('evidence/evals.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({policyCases:rows.length,coverageCases:coverageCases.length,traceCases:traceCases.length,detectionRate:report.detectionRate,falsePositiveRate:report.falsePositiveRate,scope:report.kind}));
if(errors.length||coverageCases.some(c=>c.actual!==c.expected)||traceCases.some(c=>c.actual!==c.expected))process.exitCode=1;
