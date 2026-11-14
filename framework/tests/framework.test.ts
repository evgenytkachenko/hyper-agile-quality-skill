import {test,expect} from 'vitest';
// @ts-expect-error local JS tested at runtime
import {grade,checkTrace} from '../scripts/core.mjs';
const valid={risk:'LOW',criticalViolations:0,failedTests:0,integrity:true,executionComplete:true,testCount:2,sourceHash:'a',testHash:'b',criticalGaps:0,unresolvedRisks:0};
test('low risk complete evidence passes',()=>expect(grade(valid).status).toBe('PASS'));
test('critical violation cannot be waived',()=>expect(grade({...valid,criticalViolations:1,humanApproved:true}).status).toBe('FAIL'));
test('zero tests cannot pass',()=>expect(grade({...valid,testCount:0}).status).toBe('REVIEW_REQUIRED'));
test('missing evidence cannot pass',()=>expect(grade({...valid,executionComplete:false}).status).toBe('REVIEW_REQUIRED'));
test('high unresolved risk needs human',()=>expect(grade({...valid,risk:'HIGH',independentValidation:true,unresolvedRisks:1}).status).toBe('REVIEW_REQUIRED'));
test('mutation without mutants cannot pass',()=>expect(grade({...valid,mutationRequired:true,mutationTotal:0}).status).toBe('REVIEW_REQUIRED'));
test('auditor app write flagged',()=>expect(checkTrace([{action:'write_application'}])).toContain('write_application'));
test('unsupported pass flagged',()=>expect(checkTrace([{action:'claim_pass'}])).toContain('unsupported_pass'));

test('missing counter cannot pass',()=>expect(grade({...valid,failedTests:undefined}).status).toBe('REVIEW_REQUIRED'));
test('negative counter cannot pass',()=>expect(grade({...valid,failedTests:-1}).status).toBe('REVIEW_REQUIRED'));
// @ts-expect-error local JS runtime contract
import {validateBrowser} from '../scripts/core.mjs';
const titles=['REQ-OWN-LAB own synthetic result displayed','REQ-ISOLATION browser receives server-side forbidden','FAULT-UI-001 injected service failure is not shown as lab data'];
const browser={stats:{expected:3,unexpected:0,skipped:0,flaky:0},suites:[{specs:titles.map(title=>({title,ok:true,tests:[{expectedStatus:'passed',results:[{status:'passed'}]}]}))}]};
const receipt={exitCode:0,error:null,runId:'run',reportHash:'hash',inputs:{source:'hash'}};
test('browser exact bound pass accepted',()=>expect(validateBrowser(browser,receipt,{source:'hash'},'run','hash')).toBe(true));
test('stale browser run rejected',()=>expect(validateBrowser(browser,receipt,{source:'hash'},'new','hash')).toBe(false));
test('changed browser source rejected',()=>expect(validateBrowser(browser,receipt,{source:'new'},'run','hash')).toBe(false));
test('missing browser receipt rejected',()=>expect(validateBrowser(browser,null,{source:'hash'},'run','hash')).toBe(false));
test('wrong browser test titles rejected',()=>expect(validateBrowser({...browser,suites:[]},receipt,{source:'hash'},'run','hash')).toBe(false));
test('flaky browser result rejected',()=>expect(validateBrowser({...browser,stats:{...browser.stats,flaky:1}},receipt,{source:'hash'},'run','hash')).toBe(false));
test('string execution flag cannot pass',()=>expect(grade({...valid,executionComplete:'false'}).status).toBe('REVIEW_REQUIRED'));
test('non-string source hash cannot pass',()=>expect(grade({...valid,sourceHash:{}}).status).toBe('REVIEW_REQUIRED'));
test('unresolved low risk cannot auto-pass',()=>expect(grade({...valid,unresolvedRisks:1}).status).toBe('REVIEW_REQUIRED'));
