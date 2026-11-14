# Interview walkthrough

## A short explanation

“I built a personal quality-engineering demonstration to answer a question that test counts
alone cannot answer: did the agent test the critical business risk? In the healthcare example,
a patient's results must never be returned to another patient.

“The first suite passes because it covers the happy path. The independent review checks the
original requirement against the actual assertions, identifies the missing cross-patient case,
and adds a targeted API test. That test runs against the server and exposes a deliberately seeded
authorization defect. The quality gate blocks it. After fixing the implementation, the same
assertion passes and becomes a permanent regression test.

“I use selective mutation testing to challenge the assertions, deterministic gates to check
execution evidence, and human review for unresolved high-risk decisions. The agent's own claim
of success is not the authority. I also keep the limits visible: passing a seeded demonstration
is not proof of model accuracy or complete security.”

Adapt the tense to the verified run record. If the auditor is a deterministic implementation
rather than a live model in the run being shown, explicitly call it a deterministic auditor.
Do not say an agent discovered a defect unless a recorded agent execution did so.

## Live demonstration order

1. Open the original requirement before showing any results. Explain the business harm of
   returning another patient's lab result.
2. Show the passing narrow tests and their assertions. Ask what they do **not** establish.
3. Show the documented gap and the targeted API test. Point to the distinct identities and the
   expected denial, not just its name or requirement tag.
4. Run the documented benchmark command. Show the real failing response, process exit and gate
   result. The vulnerable code must remain in the fixture, not the normal deployment path.
5. Show the fixed authorization condition and run the same regression assertion again.
6. Show the selective mutation report, including survivors/uncovered/errors if present.
7. Open the structured report and identify untested scope and any required human decision.

Use the current framework README for commands and its execution evidence for actual results.
Never substitute a screenshot of an earlier run for a fresh run without labeling it historical.

## Tradeoffs worth discussing

- **Independence:** a second role helps challenge assumptions, but identical model training or
  shared prompts can produce correlated mistakes. Deterministic server assertions and trusted
  policy add a different failure boundary.
- **Targeted tests:** extra tests are justified by a risk gap, not by a desire to raise counts.
- **Mutation cost:** mutate the small critical module, not the whole deployed application.
  Mutation strength and requirement completeness are different questions.
- **Evidence:** bind output to source, tests and command execution; missing evidence is visible.
  Provenance checks are not cryptographic proof of a trustworthy producer.
- **Business value:** a critical leak blocks a change even with many green tests. The result is
  a reviewable decision and permanent regression protection, not a vanity score.
- **Scope:** this is a synthetic personal project, not evidence that you previously deployed
  an enterprise healthcare accessibility, security or compliance program.

## Questions to be ready for

**Can an agent bypass the gate?**
A prompt cannot stop it. Explain the concrete host and protected-CI boundary actually configured.
If repository protection is still a setup step, say so.

**How did you evaluate the agents?**
Separate repeatable deterministic fixture/grade tests from real model trials. For actual trials,
name inputs, model/skill version, held-out cases, observable artifacts and denominators. Do not
quote an accuracy percentage from a small seeded demonstration as real-world performance.

**What happens when a check cannot run?**
It remains blocked or not evaluated. It does not turn into PASS, and a required human decision
is never fabricated by the coding or auditing role.
