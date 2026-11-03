# Report format

Use exactly these section headers, in this order. Omit content within a section rather than
omitting the section itself — if a section has nothing to report, say so explicitly (e.g.
"No open questions.").

```markdown
# Hyper-Agile Production Escape Assessment

## Executive Summary

## Traceability Chain

## Timeline

## Evidence Reviewed

## What Failed

## Causal Analysis

## Hyper-Agile Quality Loop Assessment

## Earliest Reasonable Missed Opportunity

## What Worked

## Action Plan

## Reusable Learning

## Open Questions / Missing Evidence
```

Notes on specific sections:

- **Traceability Chain** — show the resolved chain (Production Problem → Originating
  Requirement → Documentation → Implementation/PR → Changed Areas → Test Coverage →
  Automation → CI/CD Evidence → Regression Selection → Release Evidence → Production
  Detection → Learning), with a confidence level per link where the link isn't certain.
- **Hyper-Agile Quality Loop Assessment** — one entry per activity from
  `references/quality-loop.md`, each tagged with its evidence confidence level or marked
  `NOT APPLICABLE` / `UNKNOWN / INSUFFICIENT EVIDENCE`.
- **Action Plan** — 3-7 actions in the structure from `references/evidence-and-actions.md`.
- **Open Questions / Missing Evidence** — include every integration gap noted during the
  investigation, not just ones that turned out to matter.

After presenting the report, always end with the read-only follow-up prompt described in
`SKILL.md` ("Would you like me to prepare the approved follow-up actions?") — never act on
any action item without explicit approval first.
