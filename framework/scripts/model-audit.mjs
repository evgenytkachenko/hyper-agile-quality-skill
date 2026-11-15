// Optional real model run. Read-only model execution; proposal stays in auditor output.
import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
import { hash } from './core.mjs';
fs.mkdirSync('auditor/reports',{recursive:true});
const prompt=`Read policy/requirements.json, app/, benchmarks/missing-authorization/, and tests/coding-existing.test.ts. Independently identify critical requirements absent from those existing tests. Do not modify any file or run external requests. Return a concise review with a targeted Vitest API test proposal only if a gap justifies it; distinguish source observations from executed evidence. Do not read credentials or unrelated paths. No claim of executed tests.`;
const start=new Date().toISOString();
const r=spawnSync('codex',['exec','--ephemeral','--ignore-user-config','--sandbox','read-only','--json','--output-last-message','auditor/reports/model-review.md',prompt],{encoding:'utf8',timeout:180000,maxBuffer:8*1024*1024});
fs.writeFileSync('auditor/reports/model-trace.jsonl',r.stdout??'');
fs.writeFileSync('auditor/reports/model-stderr.txt',r.stderr??'');
fs.writeFileSync('auditor/reports/model-run.json',JSON.stringify({kind:'LIVE_CODEX_REVIEW_ATTEMPT',start,promptHash:hash(prompt),exitCode:r.status,error:r.error?.message??null,sandbox:'read-only',executedTests:false,limitations:['Single development example, not statistical agent accuracy.','Do not execute generated code before review.']},null,2)+'\n');
console.log(r.status===0?'Live read-only review recorded':'Live review unavailable; see attempt receipt');
process.exitCode=r.status===0?0:2;
