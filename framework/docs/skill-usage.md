# Using the two skills locally

The skills are repository files, not separate model services. In Claude Code or Codex, open a
working checkout and explicitly ask the host to read the selected file:

- Coding role: `skill/guarded-coding/SKILL.md`
- Independent audit role: `skill/independent-qe-auditor/SKILL.md`

Directly reading these files works without installing a host-specific plugin or declaring that
a skill installation grants tools. A host may also support its own skill discovery locations;
follow that host's supported configuration rather than assuming both hosts have identical
permission syntax. Keep two separate agent contexts for a live coding/audit exercise.

For the coding role, provide original requirements and the permitted change scope. For the
auditor, provide the same original requirements, a frozen candidate snapshot, existing tests
and execution evidence. Do not provide benchmark expected answers during a blind model trial.
Use the actual restricted execution configuration when claiming the app is read-only; a new
chat or separate folder alone does not revoke application write permission.

From `framework/`, install the declared dependencies with `npm ci`, then use the framework
README's local commands. Installation downloads dependencies; browser installation and model
access are separate prerequisites. If a tool is unavailable, report that check as blocked rather
than silently substituting a simulation.

## Example coding assignment

“Read `skill/guarded-coding/SKILL.md`. Implement this requirement within the allowed application
files: a synthetic patient's lab results are available only to that authenticated patient.
Identify material risks and assertions, run the repository checks, and provide version-bound
evidence and unresolved gaps. Do not change trusted gates, existing assertions or human approvals
to obtain a passing result.”

## Example independent audit assignment

“Read `skill/independent-qe-auditor/SKILL.md`. Independently review the original lab-access
requirement against this frozen application, its existing tests and execution artifacts.
Application code and existing tests are read-only. Write only in the assigned auditor test and
report directories. Identify a justified coverage gap before adding a targeted test. Preserve
real execution evidence and report PASS, FAIL or REVIEW_REQUIRED with limitations.”

These examples are instructions, not evidence that either host followed them. Evaluate observable
behavior and review the execution boundary. The deterministic demo can run without any model;
that makes it reproducible, not a live-agent benchmark.
