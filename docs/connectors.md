# Evidence inputs

All inputs are local files. `haq` never contacts an issue tracker, code host, CI system,
test-management system or documentation system.

## Implemented and tested (fictional fixtures)

### Markdown and text files

Files at the top of the case folder are filed by name, using the hyper-agile-engine
convention:

| File stem | Category |
| --- | --- |
| `production-issue` | production issue |
| `originating-story` | originating work |
| `requirements` | requirements |
| `documentation` | documentation |
| `code-change` | implementation changes |
| `fix-change` | remediation changes (post-release learning only) |
| `tests` | test evidence |
| `ci` | CI evidence |
| `release` | release evidence |
| `production-learning` | production evidence |
| anything else (`.md`, `.markdown`, `.txt`) | additional evidence |

`README.*` and `answer-key.*` are ignored. Text files in subfolders other than the
structured ones below are loaded as additional evidence.

### `issues/<KEY>.yaml`

```yaml
key: SHOP-482
type: Bug
title: ...
status: Done
created: 2026-03-14T09:10:00Z
affected_versions: [4.2.0]
links:
  - relation: is caused by
    target: SHOP-455
description: |
  ...
acceptance_criteria: [...]
comments:
  - at: 2026-02-26T14:20:00Z
    author_role: QA engineer      # a role, not a name
    body: "..."                   # quote text that contains '#'
```

The issue named as `incident` in `case.yaml` is the production issue; other issues are
originating work. Each `links` entry becomes a recorded (DIRECT) relationship, which the
engine's link check accepts as a record of the relationship.

### `test-results/*.xml`

JUnit XML (`<testsuites>` or a single `<testsuite>`): suite properties, timestamps and
each test case's status (passed, FAILED, ERROR, SKIPPED with message).

### `releases/*.yaml`

```yaml
version: 4.2.0
released: 2026-03-10T08:00:00Z
issues: [SHOP-455]
validation_runs:
  - id: RUN-77
    results: {TC-210: PASSED}
    not_run: [TC-211]
approval:
  decision: approved
  by_role: Release manager
  note: ...
```

### Variants

A folder with `variant.yaml` (`remove: [paths]`) plus replacement files, applied with
`--variant`. Used to show how missing or changed evidence changes the result.

### Masking and limits

Masking cannot catch every secret: a credential in an unrecognized format, and confidential or
personal information that does not look like a credential, pass through unchanged. Review evidence
before running `haq` and review every output before sharing it.

Credential-like strings in free text are masked with the engine's patterns before anything is
shown to a model or written. Identifiers — file paths, case and variant IDs, issue keys, link
targets and relations, release versions — that look like credentials, or that contain non-ASCII
or control characters, are refused with a message
that shows only the masked form, because masking them could make two citations identical. Every
evidence ID and file name must name exactly one artifact (case aside): repeated basenames in
different folders, or the same issue key in two files, are refused. Files over 2 MiB are refused; artifacts over 20,000 characters are
truncated and the cut is listed. Symlinks and hidden files are skipped.

## Not included

hyper-agile-engine has read-only connectors for Jira, GitHub, Testiny and Notion over MCP
and REST. They are not part of this project: they depend on the engine's collector,
snapshot and transport layers, and they were not reviewed for publication or tested here.
To use evidence from those systems, export it to the formats above.

## Agent-mediated export (instructions only)

`skill/hyper-agile-quality/SKILL.md` tells an agent how to export evidence with its own
read-only tools into a case folder. That behavior depends on the agent and its tools and is
not tested by this project.
