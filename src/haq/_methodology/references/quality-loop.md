# The Hyper-Agile Quality Loop — ten activities

These are the ten activities to check evidence for when relevant. **They are not ten
required process gates.** If an activity is irrelevant to this particular defect, or no
evidence is available either way, report it as `NOT APPLICABLE` or
`UNKNOWN / INSUFFICIENT EVIDENCE` — do not force a finding, good or bad, into every category.

1. **Clarify intent** — was the expected behavior actually defined before implementation
   started? (requirement, acceptance criteria, domain rule, design note)
2. **Identify risk** — was the blast radius / shared-dependency risk of this change
   recognized before implementation?
3. **Define test expectations** — did a known business rule or edge case ever become an
   observable, written validation expectation (test case, acceptance criterion), or did it
   stay tacit knowledge?
4. **Create reusable quality artifacts** — did the work produce a test case, fixture, or
   checklist that could protect against recurrence, or was validation one-off and disposable?
5. **Automate what is repeatable** — was there a reasonable opportunity to automate
   validation of this behavior, and was it taken or missed?
6. **Analyze change impact** — did anyone assess what the implementation actually touched,
   versus what the ticket implied it would touch?
7. **Select regression intelligently** — if relevant regression tests existed, were they
   actually selected for execution around this change?
8. **Release with informed confidence** — was there a real signal (test result, review
   comment, risk note) available at release time that bears on this defect, and was it
   incorporated into the release decision?
9. **Monitor production** — could reasonable monitoring/observability have shortened
   detection time or reduced impact, given what was realistically knowable pre-release?
10. **Feed learning back into the knowledge base** — had the organization already seen this
    failure pattern before, in a form that should have prevented a repeat?

## How to score honestly

For each activity, state one of:
- A specific, evidence-backed finding (what happened, with citation).
- `NOT APPLICABLE` — the activity doesn't bear on this particular defect (say why briefly).
- `UNKNOWN / INSUFFICIENT EVIDENCE` — the activity might be relevant but you don't have the
  evidence to say either way (name what's missing).

A real assessment will usually have a mix of all three. An assessment where every single
activity has a confident negative finding is a sign you've over-reached — revisit Phase 7 of
`SKILL.md` before presenting it.
