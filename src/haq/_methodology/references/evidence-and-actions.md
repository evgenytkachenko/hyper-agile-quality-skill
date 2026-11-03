# Evidence confidence, action generation, and "what worked"

## Evidence confidence levels

Every conclusion that matters must be tagged with one of:

- `CONFIRMED` — directly evidenced (e.g. the PR diff shows it, the test run log shows it).
- `STRONGLY SUPPORTED` — multiple consistent, independent pieces of evidence, no direct
  proof.
- `POSSIBLE CONTRIBUTING FACTOR` — plausible given the evidence, but not well-supported on
  its own.
- `UNKNOWN` — insufficient evidence either way.

Preserve the underlying identifiers (issue ID, PR number, test case ID, commit SHA) next to
each conclusion so a reviewer can go check it themselves. Never include credentials, tokens,
or secret URLs in the report.

## Test-coverage failure modes — do not collapse these into "tested" / "not tested"

When investigating why a test didn't catch something, distinguish:

1. No relevant test existed.
2. A test existed but was not selected for this change.
3. A test was selected but not executed.
4. A test executed but failed to detect the problem.
5. A test failed, but the signal was ignored or the run was retried past it.
6. The test itself encoded the wrong expectation.

These are six different quality-system failures with different fixes — do not report any of
them as a generic "testing gap."

## Action generation

Produce 3-7 actions, no more. Every action needs all of:

- **Action** — the specific thing to do.
- **Reason** — why, tied to a specific evidence-backed finding.
- **Owner type** — who this kind of action belongs to (not a named person).
- **Destination** — where it should land: issue tracker, test-management system, automation
  repository, CI/CD config, documentation system, monitoring, architecture guidance, quality
  knowledge base, support documentation.
- **Priority**.
- **Evidence** — the finding(s) that justify it.
- **Recurrence protection** — how this specific action prevents the same failure mode from
  recurring (not just "fixes this instance").

**Bad** (generic, not executable, delete these if you catch yourself writing them):
"Improve testing." / "Improve communication." / "Add more test cases."

**Good** (specific, cites the actual gap, names what and where):
"Add a reusable test case covering already-authenticated sessions after account disablement,
and automate the session-revocation check at the lowest practical layer."

### Action-quality filter

Before finalizing the action list, reject or rewrite any action containing a vague phrasing
like: "improve testing," "improve requirements," "communicate better," "add more automation,"
"increase coverage," "monitor better," "improve process." These are symptoms that your
analysis stopped one level too early — go back to the specific evidence-backed finding that
prompted the vague instinct and name the actual gap.

Every surviving action must specify all five of:

- **WHAT** changes, concretely.
- **WHERE** it changes (which destination: issue tracker, test-management system, automation
  repository, CI/CD config, documentation system, monitoring, architecture guidance, quality
  knowledge base, support documentation).
- **WHY** this specific finding justifies it.
- **WHO** should normally own it (owner type, not a named person).
- **HOW** it reduces recurrence or improves detection — not just "fixes this instance."

Keep the final list to roughly 3-7 high-value items unless the evidence genuinely requires
more — a long list of small items is usually a sign several of them should be merged or cut.

## Always identify what worked

Alongside failures, name the controls that functioned correctly — e.g. a requirement that
correctly described part of the behavior, CI that correctly ran what it was configured to
run, adjacent automation that protected nearby functionality, a rollback that worked,
monitoring that detected the problem quickly, support that escalated correctly. The point is
system learning, not fault assignment — an assessment with zero "what worked" findings is
usually incomplete, not unusually bad luck.

## Missing integrations

Handle gracefully — never stop the assessment because one system is unavailable. State it
plainly, e.g.:

> Evidence limitations:
> - Test-management system unavailable; structured test coverage could not be verified.
> - Documentation system unavailable; requirement analysis relies on issue-tracker content
>   only.
> - Production monitoring unavailable; production-detection analysis relies on the incident
>   report as filed.

## Validation scenarios

If asked to self-test or validate this skill's behavior, reason through each of these and
confirm the methodology produces the conservative, evidence-correct answer rather than a
confident-sounding guess:

- Full traceability exists end-to-end.
- A relevant test existed but was not selected for the change.
- No relevant test existed at all.
- The requirement was clear; the implementation was wrong.
- The failure only occurs under an unexpected production condition, not reasonably
  reproducible pre-release.
- CI was green but never exercised the failing code path (expected: CI provided insufficient
  evidence; a green run is not proof of validation).
- A relevant automated test failed before release — determine whether that signal was
  actually available to, and acted on by, whoever made the release decision before assigning
  a release-decision gap; a failure that was rerun/ignored is a different finding than one
  that simply never reached the decision-maker.
- The documentation system integration is unavailable.
- Multiple plausible originating PRs exist and none is clearly "the" one.
- The issue tracker and the documentation system give conflicting accounts of the
  requirement.

The common thread: when evidence is incomplete or contradictory, the correct behavior is to
say so (`UNKNOWN`, multiple candidates listed, limitation noted) — never to resolve the
ambiguity by picking the most narratively satisfying answer.

For validating against real historical incidents (rather than reasoning through these
scenarios abstractly), use `references/evaluation-harness.md`.
