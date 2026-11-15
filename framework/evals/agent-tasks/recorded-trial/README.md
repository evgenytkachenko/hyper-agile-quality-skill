# Recorded development trial, 2026-11-15

These are actual responses from two fresh-context internal agent invocations, one coding and one auditor, observed by the coordinating assistant. They are not scripted reference answers. Each was given only its prepared role request and permission to read that request, with no surrounding implementation history or oracle provided. No separately configured model API or LangSmith upload was used.

The record is coordinator-attested, not provider-signed. Model identity is not independently verified. The agent environment was not host-isolated from the repository; no tool-use transcript was captured in these public artifacts. Thus tool behavior and enforced answer-key isolation remain **NOT_EVALUATED**, despite instructions not to read other files. This is a response-level development trial, not a full autonomous coding-session evaluation.

Original rubric outcomes:

- Coding: 1/3 tasks passed the exact-label rubric. Its proposed predicate passed all 16 executed cases. Two answers added grounded extra findings that the rubric rejected.
- Auditor: 2/3 tasks passed the original rubric. Its proposed cross-patient probe reproduced status 200 with foreign data on the vulnerable fixture, then status 403 without data on the fixed fixture. It classified the pre-execution source-only issue as REVIEW_REQUIRED, consistent with waiting for reproduced evidence, while the original oracle demanded FAIL.

The original answers, original rubric and original grade reports are preserved. Do not interpret those rubric mismatches as proof that the agent's repair or probe failed. Conversely, passing these easy public tasks would not establish broad agent quality.

Regrading these files is **replay of captured responses**, not another live model evaluation. The harness reruns the proposed constrained artifacts when grading. The code does not claim independent invocation verification from an imported file.

## Reviewed rubric calibration, same responses

An independent reviewer approved these narrow rubric corrections:

- Allow `missing-isolation-test` in addition to the required ownership finding for the coding repair.
- Allow `evidence-unavailable` in addition to the required runner-unavailable finding.
- Allow pre-execution `REVIEW_REQUIRED` (never PASS) for the auditor isolation gap, plus optional `execution-unavailable`. Required ownership/coverage findings and the correctly executed probe remain mandatory.

The same captured responses then scored coding **3/3** and auditor **3/3** under the revised rubric. This is **rubric-calibration replay**, not new live runs, independent validation or evidence of 100% model accuracy. Original and revised oracle/grader hashes differ and must not be treated as comparable model regressions. Tests ensure optional labels cannot replace required findings and unrelated labels still fail.
