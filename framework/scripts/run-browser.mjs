import fs from 'node:fs';
import {spawnSync} from 'node:child_process';
import {hash} from './core.mjs';
const bound=['app/server.ts','app/data.ts','app/authorization.ts','app/main.ts','tests/browser.spec.ts','playwright.config.ts','package-lock.json'];
const inputs=Object.fromEntries(bound.map(p=>[p,hash(fs.readFileSync(p))]));
fs.mkdirSync('reports',{recursive:true});
for(const f of ['browser.json','browser-receipt.json']){try{fs.unlinkSync('reports/'+f);}catch(e){if(e.code!=='ENOENT')throw e;}}
let runId=null;try{runId=JSON.parse(fs.readFileSync('evidence/latest-demo.json')).runId;}catch{}
const result=spawnSync(process.execPath,['node_modules/@playwright/test/cli.js','test'],{encoding:'utf8',timeout:120000,maxBuffer:8*1024*1024});
fs.writeFileSync('reports/browser.log',(result.stdout??'')+(result.stderr??''));
let reportHash=null;try{reportHash=hash(fs.readFileSync('reports/browser.json'));}catch{}
fs.writeFileSync('reports/browser-receipt.json',JSON.stringify({runId,inputs,exitCode:result.status,error:result.error?.message??null,reportHash,completedAt:new Date().toISOString()},null,2));
process.stdout.write(result.stdout??'');process.stderr.write(result.stderr??'');
process.exitCode=result.status===0&&reportHash?0:1;
