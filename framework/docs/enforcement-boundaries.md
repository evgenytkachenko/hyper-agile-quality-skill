# Enforcement boundaries and deployment responsibilities

## What a skill can and cannot enforce

A `SKILL.md` describes how an agent should act. It cannot revoke filesystem permissions, remove
network access, protect GitHub settings or prove the agent obeyed. The auditor's read-only
application access must be enforced by its execution host, not inferred from a prompt.

For a real restricted deployment, mount the application, requirements, preexisting tests and
trusted policy read-only in an isolated process/container. Mount only auditor tests and reports
writable. Use separate output folders, no host secrets, a nonprivileged identity, no Docker
socket, and only the approved local target. An agent able to run arbitrary shell commands in
a writable repository is not read-only, even when a tool description or skill says it is.
Hash checks detect tampering after the fact; they do not prevent it.

Use only isolation features that the selected host actually supports. Record which protection
was configured and tested, which is merely recommended, and whether any denied-write test ran.
Do not label a portable skill install a sandbox.

## CI trust model

An agent must not decide its own passing score. Candidate instructions, candidate reports and
candidate workflow files are untrusted. A meaningful gate must execute independently using a
reviewed policy version and preserve the raw execution artifacts. Requirements, expected outcomes,
mutation scope and thresholds need review just as application changes do.

A workflow committed in a pull request does not become trusted merely because it uses hashes or
CODEOWNERS. If a contributor can edit the workflow, remove its job, forge a same-named status,
or merge without required checks, that contributor can bypass an ordinary repository-only gate.
CODEOWNERS requests reviews; it does not enforce them by itself.

Repository administrators must configure and verify required checks/reviews or a suitable
organization-level required workflow, restrict bypass privileges, and keep trusted policy outside
the coding agent's write authority. Record the exact protected policy revision. For a first PR
that introduces the policy, a human must review and establish that trusted base before its own
candidate gate can be treated as independent. Do not silently alter branch protection or grant
credentials as part of a demo.

Do not run untrusted pull-request application code with elevated `pull_request_target` tokens or
repository secrets. Separate trusted evaluation logic from candidate execution; use least-privilege
jobs and bounded artifacts. A fixed gate must independently reject a demonstrated critical
security defect, even if the overall pass rate or mutation percentage is high.

## Risk-based outcome interpretation

| Situation | Outcome |
| --- | --- |
| Low risk, all required current checks established, no unresolved blocker | PASS for evaluated scope |
| Medium risk with ambiguous independent evidence | REVIEW_REQUIRED |
| High risk with unresolved risks or required exception decision | REVIEW_REQUIRED, non-passing gate |
| Reproduced cross-patient disclosure or other critical violation | FAIL, cannot be waived by aggregate score |
| Required test did not start, timed out, produced no results or ran zero tests | Incomplete evidence; never PASS |

A human decision must name the reviewed result and version, its scope, reviewer role and rationale.
An agent-generated approval field is not human review. Do not auto-fill a human decision merely
to make the report green. Release approval and risk acceptance remain separate from test success.

## Reporting execution limits

Use explicit labels: **passed**, **failed**, **blocked**, **not run**, and **not evaluated**.
For example, API tests may pass while Chromium launch is blocked. Browser test source existing
in the repository is not browser test execution. A workflow YAML file is not a hosted CI run.
Local synthetic evidence is not deployment evidence, medical validation or HIPAA certification.

## Required repository owner setup

The feature PR intentionally fails the `governance` check until a human reviews bootstrap policy. Configure required status checks with no bypass, code-owner approvals for `.github/`, policy, graders and critical tests, and a trusted required workflow outside candidate control where adversarial changes are in scope. The included CODEOWNERS routes review but does not enforce it by itself. No settings were changed by this implementation. Do not solve the bootstrap failure by letting the coding agent lower policy or approve itself.
