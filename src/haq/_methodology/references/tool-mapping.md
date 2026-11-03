# Tool-role mapping (generic — discover concrete tools at runtime)

This file describes what each *category* of system is used for and the judgment calls each
one requires. It never names a specific company's project IDs, repo names, or field
mappings — discover the actual available tools via `ToolSearch` / `gh` / whatever MCP
integrations exist in this environment, per Phase 0 of `SKILL.md`.

## Issue tracker (e.g. Jira, Azure DevOps, Linear)

Use for: the production defect/incident itself, the originating story or bug, linked issues,
epic/parent relationships, description, acceptance criteria, comments, release/version,
requirement decisions, follow-up defects, timestamps.

Build relationships conservatively — **do not assume the production defect and the
originating story are the same item.** If the link isn't explicit, say so and label your
inference.

## Code repository (e.g. GitHub, GitLab)

Use for: linked PRs, commits, changed files, diff, tests changed, review discussion,
implementation decisions, configuration changes. Establish the chain Story → PR → Commit →
Changed Areas. If explicit links are absent, search by issue key, branch name, feature
terminology, or commit metadata, and label inferred relationships clearly. `gh` via Bash is
normally the right way to query GitHub and GitHub Actions in this environment.

## CI/CD system (e.g. GitHub Actions, Azure Pipelines)

Use for: workflows executed, job status, which tests actually ran, skipped jobs, failures,
retries, artifacts, timing relative to merge/release.

**A green build is never proof that the relevant behavior was tested.** Always ask: "what
evidence did this workflow actually provide?" — not "did it pass?"

## Test-management system (e.g. Testiny, Xray, Zephyr)

Use for: related test cases, expected behavior, linked requirement coverage, regression
suites, execution history, automation status, historical results. Use the six-way
test-coverage taxonomy in `references/evidence-and-actions.md` rather than a binary
tested/not-tested judgment.

## Documentation system (e.g. Confluence, Notion)

Use for: requirements, domain rules, architecture decisions, design notes, product
decisions, known limitations, release notes, requirement-analysis notes. Search linked
documentation first; if nothing is linked, search by issue key, feature name, epic name, or
requirement terminology.

Never conclude "no documentation existed." Instead say: "No relevant documentation was found
in the sources searched" — the distinction matters because the former is an unfalsifiable
negative claim and the latter is an honest statement of search scope.

## Optional production sources (incident tooling, support records, monitoring, logs, alerts)

Use, where available, to establish: actual failure behavior, customer impact, frequency,
detection path, first known occurrence, affected versions/configurations.

## Classifying tools as READ / WRITE / UNKNOWN

Within each category above, the concrete tools discovered at runtime split into operations
that only observe state and operations that can change it. Classify each one before using it:

- **READ** — the operation's description and behavior indicate it only retrieves or searches
  data (e.g. "get issue," "search," "list," "view," "export"). Safe to use during evidence
  collection.
- **WRITE** — the operation's description indicates it creates, updates, deletes, transitions,
  comments, uploads, merges, closes, reopens, assigns, changes workflow state, modifies
  code/config, triggers a deployment, or otherwise mutates something. Never use these during
  evidence collection, regardless of how convenient they'd be.
- **UNKNOWN** — you can't tell from the name/description whether it mutates state. Treat it
  exactly like `WRITE` — don't call it to gather evidence.

Do this classification conceptually from what's actually discovered in the current
environment; never hardcode a list of specific tool/function names into this methodology,
since the concrete tool names differ by environment and change over time. When a connector
only exposes a mutating operation as the way to obtain some piece of evidence, don't call
it — report the gap as an evidence limitation instead.

## General rule across all categories

Never invent endpoint names, field names, or identifiers. If a category of tool isn't
available in this environment, note it as an evidence limitation (see
`references/evidence-and-actions.md`) and continue — don't block the whole assessment on one
missing integration.
