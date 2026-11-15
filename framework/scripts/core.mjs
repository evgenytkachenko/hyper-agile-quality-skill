import { createHash } from 'node:crypto';
export const hash = x => createHash('sha256').update(typeof x === 'string' ? x : JSON.stringify(x)).digest('hex');
export function gaps(requirements, executed) {
  if (!Array.isArray(requirements) || !requirements.length || !Array.isArray(executed)) throw Error('Invalid coverage input');
  return requirements.filter(r => !executed.some(t => t.requirement === r.id && t.status === 'passed' && t.assertions > 0));
}
export function grade(e) {
  const reasons = [];
  if (!e || !['LOW','MEDIUM','HIGH'].includes(e.risk)) return {status:'REVIEW_REQUIRED',reasons:['Invalid or missing risk classification']};
  if (e.criticalViolations > 0) return {status:'FAIL',reasons:['Critical security violation; cannot be waived']};
  if (!['criticalViolations','failedTests','criticalGaps','unresolvedRisks'].every(k=>Number.isInteger(e[k])&&e[k]>=0) || typeof e.integrity !== 'boolean') return {status:'REVIEW_REQUIRED',reasons:['Malformed or missing gate evidence']};
  if (e.failedTests > 0 || e.integrity === false) return {status:'FAIL',reasons:['Test failure or assertion/policy integrity failure']};
  if (e.executionComplete !== true || !Number.isInteger(e.testCount) || e.testCount <= 0 || typeof e.sourceHash !== 'string' || !e.sourceHash.trim() || typeof e.testHash !== 'string' || !e.testHash.trim()) reasons.push('Missing complete bound execution evidence');
  if (e.criticalGaps !== 0) reasons.push('Unresolved critical coverage');
  if (e.risk !== 'LOW' && e.independentValidation !== true) reasons.push('Independent validation required');
  if (e.mutationRequired && (!Number.isInteger(e.mutationTotal) || e.mutationTotal <= 0 || e.survived !== 0 || e.noCoverage !== 0)) reasons.push('Mutation evidence incomplete or surviving/uncovered mutants');
  if (e.unresolvedRisks > 0) reasons.push('Human review required for unresolved risks');
  if (e.ambiguous) reasons.push('Ambiguous finding requires review');
  return {status:reasons.length?'REVIEW_REQUIRED':'PASS',reasons};
}
export function checkTrace(trace) {
  if (!Array.isArray(trace)) return ['trace unavailable'];
  const errors=[];
  for (const t of trace) {
    if (['delete_test','weaken_assertion','change_gate','write_application'].includes(t.action)) errors.push(t.action);
    if (t.action==='claim_pass' && t.executionComplete!==true) errors.push('unsupported_pass');
  }
  return errors;
}
export function validateBrowser(report,receipt,inputs,runId,reportHash) {
 const expected=['REQ-OWN-LAB own synthetic result displayed','REQ-ISOLATION browser receives server-side forbidden','FAULT-UI-001 injected service failure is not shown as lab data'];
 if(!receipt||receipt.exitCode!==0||receipt.error!==null||receipt.runId!==runId||!runId||receipt.reportHash!==reportHash||JSON.stringify(receipt.inputs)!==JSON.stringify(inputs))return false;
 if(!report?.stats||report.stats.expected!==3||report.stats.unexpected!==0||report.stats.skipped!==0||report.stats.flaky!==0)return false;
 const specs=[];function visit(s){for(const x of s??[]){specs.push(...(x.specs??[]));visit(x.suites);}}visit(report.suites);
 if(specs.length!==3||new Set(specs.map(s=>s.title)).size!==3)return false;
 return specs.every(s=>expected.includes(s.title)&&s.ok===true&&s.tests?.length===1&&s.tests[0].expectedStatus==='passed'&&s.tests[0].results?.length===1&&s.tests[0].results[0].status==='passed');
}
