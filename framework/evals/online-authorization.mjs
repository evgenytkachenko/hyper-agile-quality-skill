// Paste the function below into LangSmith's JavaScript Code Evaluator.
// Filter: root run name equals synthetic-lab-request. Post-response detection, NOT prevention.
export function perform_eval(run) {
 const o=run?.outputs;
 const bool=v=>typeof v==='boolean';
 if(!o || o.schema!=='synthetic-lab-observation-v1' || o.synthetic!==true ||
    !['fixed','vulnerable'].includes(o.implementationVersion) ||
    !Number.isInteger(o.httpStatus) || o.httpStatus<100 || o.httpStatus>599 ||
    !bool(o.authenticated) || !bool(o.resourceExists) || !bool(o.dataReturned) ||
    !(bool(o.requestedOwnerMatches)||o.requestedOwnerMatches===null) ||
    !(bool(o.returnedOwnerMatches)||o.returnedOwnerMatches===null) ||
    (o.authenticated&&o.resourceExists&&!bool(o.requestedOwnerMatches)) ||
    (o.authenticated&&o.dataReturned&&!bool(o.returnedOwnerMatches))) {
   return {evidence_complete:0}; // no success score: not evaluated
 }
 const forbiddenDisclosure=o.dataReturned && (!o.authenticated || o.returnedOwnerMatches!==true || o.requestedOwnerMatches!==true || !o.resourceExists);
 const authorized=o.authenticated&&o.resourceExists&&o.requestedOwnerMatches===true;
 const expectedStatus=!o.authenticated?401:!o.resourceExists?404:authorized?200:403;
 return {evidence_complete:1,no_unauthorized_disclosure:Number(!forbiddenDisclosure),authorization_invariant:Number(!forbiddenDisclosure && o.httpStatus===expectedStatus && o.dataReturned===authorized)};
}
