import fs from 'node:fs';
import {spawnSync} from 'node:child_process';
import {hash} from './core.mjs';
const bound=['app/authorization.ts','tests/policy.test.ts','vitest.mutation.config.ts','stryker.config.json','package-lock.json'];
const inputs=Object.fromEntries(bound.map(p=>[p,hash(fs.readFileSync(p))]));
fs.mkdirSync('reports/mutation',{recursive:true});
for(const f of ['mutation.json','receipt.json']){try{fs.unlinkSync('reports/mutation/'+f);}catch(e){if(e.code!=='ENOENT')throw e;}}
const runId=JSON.parse(fs.readFileSync('evidence/latest-demo.json')).runId;
const toolVersion=JSON.parse(fs.readFileSync('node_modules/@stryker-mutator/core/package.json')).version;
const result=spawnSync(process.execPath,['node_modules/@stryker-mutator/core/bin/stryker.js','run'],{encoding:'utf8',timeout:120000,maxBuffer:4*1024*1024});
fs.writeFileSync('reports/mutation/run.log',(result.stdout??'')+(result.stderr??''));
let reportHash=null;try{reportHash=hash(fs.readFileSync('reports/mutation/mutation.json'));}catch{}
fs.writeFileSync('reports/mutation/receipt.json',JSON.stringify({runId,toolVersion,inputs,exitCode:result.status,error:result.error?.message??null,reportHash,completedAt:new Date().toISOString()},null,2));
process.stdout.write(result.stdout??'');process.stderr.write(result.stderr??'');
process.exitCode=result.status===0&&reportHash?0:1;
