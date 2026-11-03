# Causal layers and the earliest reasonable missed opportunity

## Causal layers

Keep these layers separate. A defect can have findings in several layers, or none in some —
never force every layer to produce a finding.

1. **Defect introduction** — why did the incorrect behavior exist in the first place?
2. **Prevention gap** — what earlier decision or missing understanding allowed that
   condition to be created?
3. **Detection / escape gap** — why did pre-release validation fail to expose it?
4. **Release decision gap** — was relevant warning evidence available but not incorporated
   into the release decision?
5. **Production detection gap** — could monitoring or observability reasonably have reduced
   time-to-detection or impact?
6. **Learning gap** — had the organization already encountered a similar failure pattern
   without incorporating that learning?

## Root-cause quality check

Run every candidate causal finding through these questions before it goes in the report. If
the answer to any "is this real causality" question is unclear, downgrade the finding from a
stated cause to `POSSIBLE CONTRIBUTING FACTOR` or `UNKNOWN` (see
`references/evidence-and-actions.md` for the confidence vocabulary):

- Is this actually a cause, or merely something *absent* from the evidence? (Absence of a
  test, a doc, or a link is not automatically a cause — it's a gap; the cause is why the gap
  existed and whether it mattered.)
- Which layer does it belong to — introduction, prevention, detection/escape, release
  decision, production monitoring, or learning? (Don't leave it unclassified.)
- Would changing this factor plausibly have changed the outcome? If removing it wouldn't have
  prevented, detected, or contained the failure, it isn't a cause of *this* failure.
- Is there direct evidence for it, or are you inferring it from the shape of the timeline?
- Is another explanation equally plausible given the same evidence? If so, say so — don't
  silently pick one.
- Are you assigning responsibility to QE/testing for what is actually a requirement,
  implementation, product, or architecture problem?
- Are you assigning responsibility to requirements when the requirement was in fact clear and
  the implementation contradicted it?

A finding that survives all of these can be stated as a cause with its evidence confidence
level. A finding that doesn't survive gets downgraded, not dropped silently — note what kept
it from being confirmed.

## Earliest reasonable missed opportunity

The final assessment must answer: **"What was the earliest reasonable point at which the
outcome could have changed?"** Anchor the answer to one of the ten Quality Loop activities,
for example:

- *Clarify Intent* — the behavior was genuinely undefined.
- *Identify Risk* — a shared dependency was not recognized.
- *Define Test Expectations* — a known business rule never became observable validation
  guidance.
- *Analyze Change Impact* — the implementation touched a wider area than the ticket implied.
- *Select Regression* — relevant tests existed but were not selected.
- *Release* — a meaningful failure signal existed but was accepted without review.
- *Monitor Production* — the condition was genuinely difficult to reproduce before release,
  but monitoring could plausibly have detected it sooner.

**The earliest lifecycle stage where an artifact is missing is not automatically the earliest
missed opportunity.** A missing test, a missing doc, or a missing risk note is a gap, not by
itself a missed opportunity — you must separately determine whether an action at that point
could *plausibly* have prevented, detected, or contained this specific failure. A gap that
wouldn't have changed the outcome isn't the answer to this question, even if it's worth fixing
for other reasons.

It is a fully valid conclusion — and should be treated as a **successful assessment, not an
incomplete one** — to say:

> "No clear pre-release missed opportunity was identified. The failure depended on a
> condition first observable in production. The primary improvement opportunity is earlier
> production detection and reusable learning."

Do not invent an earlier missed opportunity merely because a defect reached production — some
defects really do represent a reasonable, undetectable-in-advance outcome given the evidence
available at the time. This is the primary hindsight-bias safeguard in this methodology; it
exists precisely because "it happened, therefore someone should have caught it" is the
default (and usually wrong) narrative.
