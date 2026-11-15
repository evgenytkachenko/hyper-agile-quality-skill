import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { hash, gaps } from './core.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
export function analyze(requirements, tests) {
  // Declarative coverage inventory only. Names/metadata are not proof of assertion semantics.
  const missing=gaps(requirements,tests);
  return {kind:'DETERMINISTIC_COVERAGE_CHECK',missing:missing.map(r=>r.id),criticalGaps:missing.filter(r=>r.risk==='HIGH').length,
    limitation:'Structured coverage mapping requires review; runtime negative controls establish detectability only for their seeded fault.'};
}
export function generateTargetedTest(report, output) {
  if (!report.missing.includes('REQ-ISOLATION')) return false;
  const allowed=path.join(root,'auditor/tests');
  const target=path.resolve(output);
  if (path.dirname(target)!==allowed || fs.existsSync(target) && fs.lstatSync(target).isSymbolicLink()) throw Error('Output outside auditor test directory');
  for(const dir of [path.join(root,'auditor'),allowed])if(fs.existsSync(dir)&&fs.lstatSync(dir).isSymbolicLink())throw Error('Symlink output directory refused');
  fs.mkdirSync(allowed,{recursive:true});
  fs.writeFileSync(target,`import { test, expect } from 'vitest';
import { createServer } from '../../app/server.js';
import { createVulnerableServer } from '../../benchmarks/missing-authorization/server.js';
test('REQ-ISOLATION generated gap test: A cannot read B', async () => {
  const server = process.env.QE_BENCHMARK === 'missing-authorization' ? createVulnerableServer() : createServer();
  await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));
  try {
    const port=(server.address() as import('node:net').AddressInfo).port;
    const response=await fetch('http://127.0.0.1:'+port+'/api/labs/lab-b',{headers:{Authorization:'Bearer demo-session-a'}});
    expect(response.status).toBe(403);
    const text=await response.text();
    expect(text).not.toContain('patient-b');
    expect(text).not.toContain('lab-b');
  } finally { await new Promise<void>((r,j)=>server.close(e=>e?j(e):r())); }
});
`);
  return true;
}
if (process.argv[1]===fileURLToPath(import.meta.url)) {
  const requirements=JSON.parse(fs.readFileSync(path.join(root,'policy/requirements.json'))).requirements;
  const inventory=JSON.parse(fs.readFileSync(process.argv[2]));
  const report=analyze(requirements,inventory);
  report.inputHash=hash({requirements,inventory});
  report.generated=generateTargetedTest(report,path.join(root,'auditor/tests/targeted-authorization.test.ts'));
  fs.mkdirSync(path.join(root,'evidence'),{recursive:true});
  fs.writeFileSync(path.join(root,'evidence/audit.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
}
