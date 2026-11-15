# Independent AI Quality Engineering framework

A production-inspired **demonstration**, extending Hyper-Agile Quality Skill without changing its investigation CLI. It shows why passing tests are not enough: a missing cross-patient authorization scenario is identified, a targeted real HTTP test fails against an isolated fictional defect, and the same check passes against the secure implementation.

## Start locally

Node.js 22+ and npm are required. All patients, sessions and lab values are synthetic. Never use these public fixture sessions as production authentication.

```sh
cd framework
npm ci
npm run typecheck
npm test
npm run demo
npm run evals
npm run test:mutation
npm run gate
npx playwright install chromium
npm run test:browser
```

`demo` returns success only if the existing incomplete suite passes, the generated targeted case **fails** against the vulnerable benchmark, and it passes against the fixed implementation. Read the generated `evidence/<run-id>/quality-report.json`, individual test reports, execution receipts and logs. A demo success means the negative-control sequence worked; it does not mean the vulnerable fixture is approved. The benchmark is not selectable by the normal application entry point.

To see the negative control's actual nonzero exit directly:

```sh
QE_BENCHMARK=missing-authorization npx vitest run auditor/tests/targeted-authorization.test.ts
```

That command should fail. The environment variable is consumed only by test code; no vulnerable production mode exists. `npm run test:api` exercises the normal secure server using real HTTP and server-side session-to-patient resolution.

## Agents and deterministic checks

- [Guarded coding skill](../skill/guarded-coding/SKILL.md) instructs the coding host to analyze requirements and risk, implement, test, inspect surviving mutants and report gaps.
- [Independent QE auditor skill](../skill/independent-qe-auditor/SKILL.md) independently reviews original acceptance criteria and existing assertions, proposing new tests only for meaningful gaps.
- `scripts/audit.mjs` is a **deterministic structured coverage helper**, not an LLM. Test-ID mappings are declarations, not semantic proof. Negative controls provide additional execution evidence.
- `npm run audit:model` optionally invokes an installed Codex host in read-only mode and records a proposal and trace. Review proposals before executing code. This CLI attempt was blocked in the implementation environment, so it is not a successful repeatable model evaluation.
- A separate actual native QE agent performed a one-off source review and proposed the acceptance test in `auditor/tests/independent-acceptance.test.ts`. Its benchmark/fixed runs were executed. This single development trial is not model accuracy evidence.

No claim is made that a skill prompt enforces filesystem permissions. Use a genuinely read-only application mount or the host's supported read-only sandbox; the model should propose tests and an authorized orchestrator writes them only under `auditor/`. A hash detects changes after the fact, not malicious consistent rewriting. See [enforcement boundaries](docs/enforcement-boundaries.md).

## Mutation, fault injection and evaluation

Stryker mutates only `app/authorization.ts`, runs unit tests in process and never deploys each mutant. Surviving or uncovered mutants require investigation. A survivor in the initial redundant guard was equivalent; simplifying that guard preserved tests and resulted in four killed mutants, with no threshold weakening or exclusion.

Playwright checks a real browser path plus a synthetic service failure through request interception. Client interception does not prove server authorization; API tests do that separately.

`npm run evals` evaluates 12 risk/gate cases, four coverage cases and three synthetic behavior traces. Its detection and false-positive numbers describe that **deterministic calibration set only**, not coding/auditor model quality. Preserve a previous `evidence/evals.json` outside the output path, then run `node scripts/evaluate.mjs <previous-file>` to compare compatible dataset versions. A changed dataset is not evaluated. Expand held-out agent trials before claiming model accuracy.

## CI and actual trust boundaries

The GitHub Actions workflow runs deterministic tests, negative controls, mutation checks and browser checks, then retains evidence for 30 days. No deployment or release exists. Critical violations are not waivable by a high overall pass rate. The policy grader returns PASS, FAIL or REVIEW_REQUIRED; missing execution, unresolved critical coverage or ambiguous high-risk evidence cannot pass.

**Repository files alone cannot prevent an agent with repository write/admin access from altering a workflow.** The governance job deliberately blocks initial bootstrap and changes to policy/workflow/gate scripts. The owner must review and merge the bootstrap, configure required checks/rulesets, restrict policy ownership and prevent bypasses. For adversarial contributors, use an organization-managed required workflow or separate trusted CI service, execute untrusted app code in isolated jobs, and keep gate code/credentials outside candidate control. These settings were not changed. The same-repository workflow is demonstrative until those external controls exist.

## Reuse of existing HAQ components

Existing evidence provenance, answer binding and human decisions are not replaced by another framework. After `npm run demo`, export its synthetic run into the original adapter:

```sh
python scripts/export-haq-case.py
# With the original repository's Python package installed:
haq check-case evidence/haq-case
```

This invokes the existing evidence loader/masking/validation unchanged. It explicitly reports missing release/origin artifacts; the benchmark is not a production incident. The original `haq investigate` answer exchange can then support a human-reviewed investigation, subject to its existing confidentiality rules.

## Optional observability

[LangSmith integration](docs/langsmith.md) uses the official SDK without adding LangChain. `npm run trace:summary` stays offline. Upload requires an explicit flag and securely configured account credentials; only allowlisted synthetic stage summaries are sent. No live LangSmith upload was performed.

## Portfolio walkthrough

See [architecture diagram](docs/architecture.md), [interview walkthrough](docs/interview-walkthrough.md), and [verified results and limitations](docs/verification.md). These are personal-project results, not prior employer achievements or healthcare compliance certification.

### Repeatable evaluations of actual host-agent answers

For both roles, `node scripts/agent-eval.mjs prepare coding` (or `auditor`) creates a bound request without expected answers. Give that request and the matching skill to a separate host agent; preserve its actual trace and JSON response. Grade it with `node scripts/agent-eval.mjs grade coding <actual-answer.json> [prior-result.json]`. Missing/duplicate/stale answers fail, and results keep role, model metadata, skill/dataset hashes and separate defect/clean denominators. Do not supply hand-written answers and describe them as a model run. The six development cases are visible in the repository and must not be described as blind or held-out benchmarks. Full live runs for both roles are not verified here.

### Three-layer evaluation lab

[Run the deterministic, offline dataset, and online monitoring walkthrough](docs/layered-evals.md). `npm run evals:offline` executes six real loopback HTTP cases against both implementations; `npm run evals:online` demonstrates per-request monitoring locally. Neither uploads unless `--upload-synthetic` is explicitly supplied. Hosted online evaluation requires the separate LangSmith evaluator setup described in the guide.
