---
name: hyper-agile-assessment
description: "Evidence-based Quality Engineering investigation using the Hyper-Agile Quality Loop. Primary workflow is a Production Escape Assessment: given a production defect, incident, or escaped issue, traces it retrospectively through requirements, documentation, implementation, test coverage, CI/CD evidence, and release/production evidence, then evaluates the finding against the ten Hyper-Agile Quality Loop activities. Trigger on: 'analyze PROD-1234', 'run a hyper-agile assessment of BUG-456', 'why did this defect escape to production', 'trace this customer-reported defect back to the originating story', 'analyze this incident and tell me what we should change'."
allowed-tools: "*"
user-invocable: true
argument-hint: [issue-id-or-description]
---

# Hyper-Agile Assessment

A single orchestrating skill — no subagents — that performs evidence-based Quality
Engineering investigations. It is both the methodology (the Hyper-Agile Quality Loop,
causal-analysis rules, evidence-confidence rules, hindsight-bias safeguards, action-item
structure, report format) and the evidence-gathering workflow that feeds it. Do not split
this into a separate "analyzer + assessment skill" pair, and do not spawn agents for this —
one skill, using the model's own reasoning plus whatever tools are available, is sufficient
and keeps the methodology in one place.

This is a read-only analytical skill. It is not website, UI, documentation-site, or
dashboard functionality.

## Default execution mode: READ ONLY

**Tool availability does not imply permission to mutate a system.** This is a non-negotiable
execution rule, not a style preference.

During an assessment, you MUST NOT invoke any operation that creates, updates, deletes,
transitions, comments, uploads, merges, closes, reopens, assigns, changes workflow state,
modifies code, modifies configuration, triggers a deployment, changes a test case/test run,
changes documentation, or otherwise mutates an external system — in the issue tracker, code
repository, CI/CD system, test-management system, documentation system, or any other
discovered integration. If both a read and a write operation could get you the same evidence,
always choose the read operation. If the only way a connector exposes some piece of evidence
is through an operation that isn't clearly read-only, do not call it — report the limitation
instead (see "Evidence limitations" in `references/report-template.md`).

The assessment itself ends with recommendations only. After the report, you may ask:

> "Would you like me to prepare or apply any of these follow-up actions?"

No write operation may occur until the user explicitly approves **that specific class of
action**. "Yes, create issue-tracker follow-up tickets" authorizes issue-tracker ticket
creation only. "Yes, update the test case for X" authorizes that specific update only.
General statements such as "looks good," "continue," or "go ahead with the assessment" do
**not** authorize any write.

## Portability rule — read this before doing anything else

**Never hardcode** company names, project names, Jira project keys, repo names, CI
workflow names, Testiny/Confluence/Notion/Azure-DevOps/GitLab identifiers, or any other
environment-specific mapping in this file or in your reasoning. The methodology must work
identically regardless of which issue tracker, code host, test-management system, or docs
system is in play.

Refer to systems generically in your own output and reasoning:
- **issue tracker** (e.g. Jira, Azure DevOps, Linear)
- **code repository** (e.g. GitHub, GitLab)
- **CI/CD system** (e.g. GitHub Actions, Azure Pipelines)
- **test-management system** (e.g. Testiny, Xray, Zephyr)
- **documentation system** (e.g. Confluence, Notion)
- **production/observability sources** (e.g. incident tool, logs, monitoring, support records)

Parenthetical product names may appear in your output where it aids clarity (e.g. "issue
tracker (Jira)"), but the logic you follow must never assume a specific one exists.

## Phase 0 — Discover what's available

Before investigating anything:

1. Check which MCP tools/integrations actually exist in this environment (they may be
   deferred — use `ToolSearch` to find Jira/Atlassian, GitHub (`gh` via Bash is usually the
   right tool for GitHub + GitHub Actions evidence), Testiny, Confluence, Notion, or other
   relevant tool groups).
2. Treat anything unavailable as a known evidence gap, not a blocker. Note it for the
   "Evidence limitations" part of the report (see `references/report-template.md`) and keep
   going — never terminate the whole assessment because one system can't be queried.
3. **Classify every discovered capability as `READ`, `WRITE`, or `UNKNOWN`** before using any
   of them. This is a conceptual classification you make from the tool's description/behavior
   at runtime — never a hardcoded list of specific MCP function names, since those vary by
   environment. Use only `READ` capabilities for evidence collection. Never use `WRITE` or
   `UNKNOWN` capabilities during the assessment itself. If you're uncertain whether an
   operation mutates state, treat it as `WRITE`/`UNKNOWN` and don't call it — this is the
   mechanical enforcement of the READ ONLY rule above, not a separate judgment call.
4. If the user's invocation doesn't give you enough to resolve the production issue (e.g.
   just "analyze this incident" with no ID), ask one clarifying question before starting
   rather than guessing at a key.

## Phase 1 — Resolve the production problem

Identify: what happened, expected vs. actual behavior, impact, detection method, affected
release/version, known reproduction conditions. Pull this from the issue tracker entry and,
if available, production/incident sources.

## Phase 2 — Trace to originating work

Find the originating story/task/bug, linked epic or requirement, relevant documentation, and
the implementing PR/commits. **Do not assume the production defect and the originating story
are the same item** — trace the relationship explicitly and assign it a confidence level (see
`references/evidence-and-actions.md`). If explicit links are absent, search by issue key,
branch name, feature terminology, or commit metadata, and label any inferred relationship as
inferred.

Every link in the chain (defect → story, story → PR, PR → changed area, story → test
coverage, change → CI execution) needs its own confidence tag — `CONFIRMED`, `STRONGLY
SUPPORTED`, `POSSIBLE CONTRIBUTING FACTOR`, or `UNKNOWN`. **Keyword or naming similarity alone
is never enough to promote a link to `CONFIRMED` or `STRONGLY SUPPORTED`** — it supports at
most `POSSIBLE CONTRIBUTING FACTOR` unless corroborated by an explicit reference (a link
field, an issue key in a commit/branch/PR title, an explicit cross-reference). If more than
one story or PR plausibly originates the defect, **list all of them with their individual
confidence levels and explain the ambiguity** rather than silently picking one.

## Phase 3 — Build the evidence chain

Gather evidence across: requirements, documentation, code/implementation, tests, automation,
CI, regression selection, release, production. Read `references/tool-mapping.md` for what
each category of tool is good for and the specific judgment calls each one requires (e.g. a
green CI build is never proof the relevant behavior was tested; test coverage has at least
six distinguishable failure modes, not just "tested" vs. "not tested").

Normalize everything into a compact evidence bundle before moving on — this is what later
phases and the final report work from.

## Phase 4 — Build a timeline

Chronological order, evidence-supported only (requirement created → clarified →
implementation started → PR created → tests created/updated → CI executed → merged →
released → first production signal → issue reported → fix created). Omit any step you have
no evidence for rather than inferring it.

## Phase 5 — Separate pre-release and post-release knowledge (mandatory)

Split everything you found into two explicit groups:
- **Known before release** — what was knowable/visible at the time the release decision was made.
- **Learned after release** — what only became known from the production failure itself.

This separation is required precisely to prevent hindsight bias in Phase 6-7. Read
`references/causal-model.md` before writing any causal conclusion — in particular its
"earliest reasonable missed opportunity" section, which exists to stop you from inventing a
pre-release failure point merely because a defect reached production.

Your assessment of requirements, risk, validation, regression, CI, and release readiness must
use only evidence from the "known before release" group. Evidence from "learned after
release" may inform learning and future-improvement recommendations, but must never be used
to claim the team "should have known" something unless you can show that information was
reasonably available beforehand. Before finalizing any causal finding, ask yourself: **"Am I
criticizing a pre-release decision using information that only became available after
release?"** If yes, revise the finding.

## Phase 6 — Assess against the Hyper-Agile Quality Loop

Read `references/quality-loop.md` for the ten activities and how to score each one honestly
(including when `NOT APPLICABLE` or `UNKNOWN / INSUFFICIENT EVIDENCE` is the correct and
expected answer — do not force a finding into every category). Apply the causal-layer model
and evidence-confidence levels from `references/causal-model.md` and
`references/evidence-and-actions.md`. Before treating anything as a cause rather than an
observation, run it through the root-cause quality check in `references/causal-model.md` —
it governs when a finding must be downgraded to `POSSIBLE CONTRIBUTING FACTOR` or `UNKNOWN`
instead of stated as a confirmed cause.

## Phase 7 — Challenge your own result

This is an internal quality gate, not report content — don't paste this checklist verbatim
into the user-facing report unless it's genuinely useful to show your work. Before presenting
anything, re-check your draft against every category and revise if it fails any item:

- **Traceability** — Did I connect the correct issue/story/PR/test/release, with confidence
  levels, rather than assuming the most narratively convenient link?
- **Evidence** — Did I distinguish fact (cited) from inference (labeled as inferred)? Did I
  mistake absence of evidence for evidence of absence anywhere?
- **Hindsight** — Did I separate pre-release knowledge from post-release learning, and run
  the "am I using after-the-fact information to criticize a before-the-fact decision?" check
  from Phase 5 on every causal finding?
- **Causality** — Did I avoid turning missing evidence into a root cause? Did I run the
  root-cause quality check from `references/causal-model.md` on each causal finding? Did I
  blame testing for what is actually a requirement/design/architecture failure, or blame
  requirements when the requirement was clear and the implementation contradicted it?
- **Coverage** — Did I correctly distinguish the six test-coverage failure modes in
  `references/evidence-and-actions.md` rather than collapsing them into "tested"/"not tested"?
- **Balance** — Did I identify what worked, not just what failed?
- **Learning** — Does this assessment actually change something about future quality work, or
  is it just a narrative of what happened?
- **Actionability** — Is every action item specific enough to execute without further
  investigation, and free of the vague phrasings the action-quality filter in
  `references/evidence-and-actions.md` rejects?
- Did I recommend automation where human judgment or monitoring would actually fit better?

## Phase 8 — Present the result

Use the structure in `references/report-template.md` exactly (section headers, order).
Preserve source links/issue IDs/PR IDs/test IDs so a reviewer can inspect the underlying
evidence — but never include credentials, tokens, or secret URLs.

## After the report: read-only by default

See "Default execution mode: READ ONLY" above — it governs this section. This skill never
automatically creates or edits anything in the issue tracker, test-management system, docs
system, code, CI, or monitoring, regardless of which write-capable tools happen to be
available. After presenting the report, ask:

> "Would you like me to prepare or apply any of these follow-up actions?"

Only after the user explicitly approves a **specific class of action** may you use the
corresponding write-capable tool, and only for that approved action — never the full action
list by default, and never on the strength of a general "looks good"/"continue"/"go ahead."

## Validation

If you're asked to validate or self-test this skill, use the scenario list at the bottom of
`references/evidence-and-actions.md` (full traceability; test existed but wasn't selected; no
test existed; clear requirement but wrong implementation; condition only reproducible in
production; green CI that never exercised the failing path; a failing test that was
rerun/ignored; a missing integration; multiple candidate originating PRs; conflicting
evidence between the issue tracker and documentation). Behave conservatively — prefer `UNKNOWN`
over a confident-sounding guess — whenever evidence is incomplete or contradictory.

When validating this skill against real historical production escapes (as opposed to
reasoning through the abstract scenarios above), use the lightweight recording template in
`references/evaluation-harness.md`. It's a learning tool for improving the skill, not a
scorecard for grading teams.
