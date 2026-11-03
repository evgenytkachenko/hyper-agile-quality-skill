# Evaluation harness

A lightweight record for validating this skill against historical production escapes whose
actual history the reviewer already understands well enough to judge the assessment against.
This is for improving the skill, not for grading teams or individuals — never share a
completed record as a performance evaluation of the people involved.

Not a test framework — just a consistent note-taking shape so multiple manual evaluations are
comparable. Validate against 3-5 historical production issues to start.

## Record template

For each historical issue evaluated, record:

```markdown
### Evaluation: <issue identifier or short label>

- Traceability correct: Yes / Partial / No
- Primary causal analysis useful: Yes / Partial / No
- Earliest missed opportunity accurate: Yes / Partial / No
  (including: did the skill correctly conclude "no clear pre-release missed opportunity"
  when that was the right answer, rather than inventing one?)
- Loop assessment useful: Yes / Partial / No
- Actions actionable: Yes / Partial / No
- Unsupported claims: <count>
- Important evidence missed: <count>
- Hindsight-bias findings: <count>
  (causal claims that used post-release knowledge to criticize a pre-release decision
  without evidence it was knowable beforehand)
- Notes: <free text — what specifically was right/wrong, and why>
```

## How to use it

1. Pick a production escape you already understand the real history of — ideally one with
   some nuance (a genuine pre-release miss, a case where nothing reasonable could have caught
   it, a case with ambiguous originating PRs, etc.), not just the easiest case.
2. Run the assessment for real (or walk through the methodology by hand) without feeding the
   skill your own prior conclusions.
3. Compare its output to what you know actually happened and fill in the record above.
4. Look for patterns across records — e.g. if "hindsight-bias findings" is consistently
   nonzero, the Phase 5/7 checks in `SKILL.md` need to be stronger, not just this one report
   re-run.
5. Feed anything systematic back into `SKILL.md` or the other reference files — this harness
   is a diagnostic for the methodology, not a one-off checklist to fill in and discard.
