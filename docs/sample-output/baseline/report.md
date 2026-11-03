# Escaped-defect investigation: Promo discount applied twice after a cart quantity change

- Case: `checkout-promo`
- Answers: **SCRIPTED RESPONSES (not a model)** — marked [SCRIPTED] below
- Checks: hyper-agile-engine guards (vendored) and this skill's hypothesis checks — marked [CHECK]
- Decisions: none taken by this tool — marked [DECISION]

> **Scripted demo.** The answers in this report were written in advance for a fictional case. No model was run. The checks and the report are real code running on those answers.

> This report contains checked hypotheses for human review. It does not establish a root cause. [CHECK] means an identifier, citation or quote was found where the answer said it was, or a rule was applied; it does not mean the evidence says what the hypothesis claims.

## 1. Production problem

[SCRIPTED] After applying a percentage promo code on the cart page, changing an item quantity reduced the order total a second time (19% off instead of 10% for SPRING10). 37 orders were affected between 2026-03-10 and 2026-03-14. It was detected by the finance team's daily discount reconciliation, not by customers [issue:SHOP-482] [production-learning.md].

## 2. Evidence chain: production back to origin

| Link | Recorded? [CHECK] | Confidence [CHECK] | Verified support [CHECK] | Basis [SCRIPTED] |
| --- | --- | --- | --- | --- |
| SHOP-482 → SHOP-455 (is caused by) | DIRECT | CONFIRMED | recorded issue link: SHOP-482 is caused by SHOP-455 (DIRECT) | The production issue records an 'is caused by' link to SHOP-455. |
| SHOP-455 → PR #318 (implemented by) | DIRECT | CONFIRMED | issue:SHOP-455 records PR #318 | The pull request title names SHOP-455, and the story comment says it was merged in PR #318. |
| PR #318 → junit:ci-unit (validated by) | INFERRED (answered DIRECT) | STRONGLY SUPPORTED (answered CONFIRMED) | code-change.md | The CI results and the pull request show the same commit 4f2c1a9e. |
| PR #318 → TC-210 (tested by) | INFERRED | POSSIBLE CONTRIBUTING FACTOR | code-change.md, tests.md | Same feature area; TC-210 is automated as test_promo_applies_percentage, which the pull request adds. |
| SHOP-455 → Release 4.2.0 (released in) | DIRECT | CONFIRMED | issue:SHOP-455 records Release 4.2.0 | The release record lists SHOP-455 as a work item. |

Critical signals [SCRIPTED] with provenance [CHECK]:

- `signal-001` (pre-release, relevance HIGH, CONFIRMED; provenance: source holds what it says) from `issue:SHOP-455` — QA asked what should happen to the discount if a quantity changes after a code is applied; the comment says this is not covered by the acceptance criteria, and no answer is recorded.
- `signal-002` (pre-release, relevance HIGH, CONFIRMED; provenance: source holds what it says) from `release:4.2.0` — The release approval note states that quantity edits after applying a code are not covered in release 4.2.0, with follow-up SHOP-470.

Known before release [SCRIPTED]:

- The pricing rules required discounts to be calculated from the undiscounted subtotal [documentation.md].
- A QA question about quantity changes after applying a code was recorded on SHOP-455 and has no recorded answer [issue:SHOP-455].
- The release approval note stated that quantity edits after applying a code were not covered, with follow-up SHOP-470 [release:4.2.0].

Learned after release [SCRIPTED]:

- The discount was applied a second time after a quantity change; 37 orders were affected [issue:SHOP-482].
- The quantity-change hook re-applied the promo to a total that already included the discount [fix-change.md].

Timeline [SCRIPTED]:

- 2026-01-15 — Pricing rules document says percentage discounts are calculated from the undiscounted subtotal. (`documentation.md`)
- 2026-02-26T14:20:00Z — QA engineer asks on SHOP-455 what happens to the discount when a quantity changes after a code is applied. (`issue:SHOP-455`)
- 2026-03-03T15:35:12Z — CI unit suite passes at commit 4f2c1a9e. (`junit:ci-unit`)
- 2026-03-03T15:40:00Z — PR #318 merged. (`code-change.md`)
- 2026-03-09T17:00:00Z — Regression run RUN-77 closes: TC-210 and TC-212 passed; TC-211 not run. (`release:4.2.0`)
- 2026-03-09T18:00:00Z — Release 4.2.0 approved with a note that quantity edits after applying a code are not covered. (`release:4.2.0`)
- 2026-03-10T08:00:00Z — Release 4.2.0 deployed to production. (`production-learning.md`)
- 2026-03-14T07:30:00Z — Finance reconciliation flags discounts above the promo percentage. (`production-learning.md`)
- 2026-03-14T09:10:00Z — SHOP-482 opened. (`issue:SHOP-482`)
- 2026-03-14T17:20:00Z — Fix PR #331 merged. (`fix-change.md`)

## 3. Testing and release evidence

| Test | Could detect the failure? [CHECK] | Classification [CHECK] | Confidence [CHECK] | Run for this release? [SCRIPTED] | Material differences [SCRIPTED] |
| --- | --- | --- | --- | --- | --- |
| TC-210 | NO | RELATED BUT NOT DETECTING | STRONGLY SUPPORTED | YES | The quantity never changes after the code is applied, so the recalculation hook never runs. |
| TC-211 | UNCERTAIN (answered YES) | UNCERTAIN | UNKNOWN (answered STRONGLY SUPPORTED) | NO | A page reload is not a quantity change, and the test checks only that the code is shown, not the discount amount. |
| TC-212 | NO | RELATED BUT NOT DETECTING | CONFIRMED | YES | No discount is applied, so no recalculation can happen. |
| tests.test_cart::test_quantity_update_changes_total | NO | RELATED BUT NOT DETECTING | STRONGLY SUPPORTED | YES | No promo code is applied, so the discount recalculation path is not exercised. |

- Regression-selection gap [CHECK, derived from the rows above]: **UNCERTAIN**
- Test-coverage failure mode [SCRIPTED]: 1. No relevant test existed: the recorded tests apply a code to an unchanged cart, reload the page, or use an expired code; none changes a quantity after applying a code.
- What CI actually demonstrated [SCRIPTED]: junit:ci-unit shows three unit tests passing at commit 4f2c1a9e. test_quantity_update_changes_total exercises a quantity change without a promo code. No CI result exercises a quantity change after a code is applied.
- Signals available at release time [SCRIPTED]: Release approval note: quantity edits after applying a code are not covered in this release; follow-up SHOP-470 (signal-002).

Quality Loop activities in this step [SCRIPTED], held by [CHECK]:

- **Automate what is repeatable**: UNKNOWN / INSUFFICIENT EVIDENCE (answered STRONGLY SUPPORTED) — The promo percentage and expired-code checks were automated in the unit suite; no automated test changes a quantity after applying a code. (evidence linked review required)
- **Analyze change impact**: UNKNOWN / INSUFFICIENT EVIDENCE (answered STRONGLY SUPPORTED) — PR #318 changed cart/events.py so that the discount is recalculated on any cart change, which is wider than the story's acceptance criteria describe. (evidence linked review required)
- **Select regression intelligently**: POSSIBLE CONTRIBUTING FACTOR — TC-211 was not run in RUN-77. (evidence linked review required)
- **Release with informed confidence**: UNKNOWN / INSUFFICIENT EVIDENCE (answered CONFIRMED) — The release decision recorded the uncovered quantity-edit condition and approved the release with a follow-up. (evidence linked review required)
- **Monitor production**: UNKNOWN / INSUFFICIENT EVIDENCE — Detection came from a daily finance reconciliation four days after release; no monitoring evidence was provided. (evidence linked review required)

## 4. What the evidence supports, contradicts and leaves unknown

### Supported after checks [CHECK]

**H1** [SCRIPTED] PR #318 calculates the discount from the cart total after discounts and re-applies it when a quantity changes, so a second discount is taken from an already-discounted total.

- Layer: Defect introduction; Quality Loop activity: Analyze change impact
- Confidence [CHECK]: STRONGLY SUPPORTED — citations and quotes checked; meaning not verified
- Supporting quote from `code-change.md` — VERIFIED_QUOTE: “subtotal = cart.total() # total after discounts already applied”
- Supporting quote from `issue:SHOP-482` — VERIFIED_QUOTE: “Customers who changed the quantity after applying SPRING10 received 19% off instead of 10%.”
- What would settle it [SCRIPTED]: The history of cart/events.py before release 4.2.0, and whether SHOP-460 changed the cart total calculation.

**H2** [SCRIPTED] No test before release exercised a quantity change after a promo code was applied, so pre-release validation could not expose the defect.

- Layer: Detection / escape gap; Quality Loop activity: Define test expectations
- Confidence [CHECK]: CONFIRMED — citations and quotes checked; meaning not verified
- Supporting quote from `tests.md` — VERIFIED_QUOTE: “Steps: Reload the cart page.”
- Supporting quote from `junit:ci-unit` — VERIFIED_QUOTE: “tests.test_cart::test_quantity_update_changes_total: passed”
- What would settle it [SCRIPTED]: A complete export of the test-management system and all automated test suites run for 4.2.0.

**H3** [SCRIPTED] The release decision knowingly accepted the uncovered quantity-edit condition with a follow-up, without a compensating control such as monitoring.

- Layer: Release decision gap; Quality Loop activity: Release with informed confidence
- Confidence [CHECK]: STRONGLY SUPPORTED — citations and quotes checked; meaning not verified
- Supporting quote from `release:4.2.0` — VERIFIED_QUOTE: “Quantity edits after applying a code are not covered in this release; follow-up SHOP-470.”
- What would settle it [SCRIPTED]: The content and schedule of SHOP-470, and whether any compensating control was discussed at approval.

**H7** [SCRIPTED] The quantity-change hook in cart/events.py, not the promo calculation itself, introduced the double discount.

- Layer: Defect introduction; Quality Loop activity: Analyze change impact
- Confidence [CHECK]: POSSIBLE CONTRIBUTING FACTOR (answered STRONGLY SUPPORTED) — citations and quotes checked; meaning not verified
- Supporting quote from `fix-change.md` — VERIFIED_QUOTE: “The quantity-change hook in cart/events.py re-applied the promo to a total that already included the discount.”
- What would settle it [SCRIPTED]: Whether cart/events.py called the promo calculation before PR #318.

### Contradicted or in conflict [CHECK]

**H4** [SCRIPTED] The expected discount behavior after a quantity change was never defined, because the QA question on SHOP-455 was not answered before release.

- Layer: Prevention gap; Quality Loop activity: Clarify intent
- Confidence [CHECK]: POSSIBLE CONTRIBUTING FACTOR (answered STRONGLY SUPPORTED) — citations and quotes checked; meaning not verified
- Supporting quote from `issue:SHOP-455` — VERIFIED_QUOTE: “What should happen to the discount if the customer changes a quantity after applying a code? Not covered by the acceptance criteria.”
- Contradicting quote from `documentation.md` — VERIFIED_QUOTE: “Any change to the cart recalculates the discount from the undiscounted subtotal.”
- What would settle it [SCRIPTED]: Whether the pricing rules document was known to the story's team and linked from SHOP-455.

**H5** [SCRIPTED] TC-211 was left out of the regression run; had it been selected, it would have caught the defect before release.

- Layer: Detection / escape gap; Quality Loop activity: Select regression intelligently
- Confidence [CHECK]: UNKNOWN (answered STRONGLY SUPPORTED) — citations and quotes checked; meaning not verified
- Supporting quote from `release:4.2.0` — VERIFIED_QUOTE: “Not run: TC-211”
- Contradicting quote from `tests.md` — VERIFIED_QUOTE: “Expected: The code SPRING10 is still shown as applied.”
- What would settle it [SCRIPTED]: Running TC-211 against release 4.2.0.

### Not established [CHECK]

**H6** [SCRIPTED] Monitoring alerted on the discount anomaly within an hour of release, but the alert was not acted on for four days.

- Layer: Production detection gap; Quality Loop activity: Monitor production
- Confidence [CHECK]: UNKNOWN (answered STRONGLY SUPPORTED) — citations and quotes checked; meaning not verified
- Supporting quote from `monitoring-alerts.md` — UNKNOWN_SOURCE: “Discount ratio above threshold”
- What would settle it [SCRIPTED]: Alert history for the checkout service between 2026-03-10 and 2026-03-14.

### Unknowns [SCRIPTED]

- Whether the release manager saw the QA question on SHOP-455 (no record of it in the release evidence).
- What SHOP-470 contained and whether it was scheduled.
- Whether any production monitoring covers discount amounts (no monitoring evidence was provided).
- Whether SHOP-460, released in the same version, touched cart code.

### Evidence limitations [CHECK]

- No requirements artifact was provided in the case folder.

## 5. What worked

- [SCRIPTED] The finance team's daily reconciliation detected the defect within four days, before any customer complaint. — quotes [CHECK]: `production-learning.md` VERIFIED_QUOTE
- [SCRIPTED] The expired-code path stayed protected: TC-212 ran and passed in the release regression. — quotes [CHECK]: `release:4.2.0` VERIFIED_QUOTE
- [SCRIPTED] The release decision recorded the known uncovered condition explicitly instead of leaving it tacit. — quotes [CHECK]: `release:4.2.0` VERIFIED_QUOTE

## 6. Proposed regression tests (for human review)

**T1. Percentage promo after a quantity change** [SCRIPTED]

- Condition: Given a cart with one item at 20.00 and SPRING10 applied, when the quantity changes from 1 to 3, then the discount is 6.00 and the total is 54.00.
- Level: unit and API; destination: automation repository (pricing tests) and test-management system; addresses: H1, H2
- Status [DECISION]: proposed — not accepted

**T2. Discount never exceeds the promo percentage across cart edits** [SCRIPTED]

- Condition: For random sequences of add, remove and quantity changes after applying a percentage code, the discount always equals the percentage of the undiscounted subtotal.
- Level: unit (property-based); destination: automation repository (pricing tests); addresses: H1
- Status [DECISION]: proposed — not accepted

**T3. Add TC-211 to the release regression set** [SCRIPTED]

- Condition: Run TC-211 in every release regression run.
- Level: manual; destination: test-management system; addresses: H5
- Review flag [CHECK]: none of the hypotheses it addresses is SUPPORTED after checks; treat as exploratory, not as a fix for an established gap
- Status [DECISION]: proposed — not accepted

## 7. Proposed quality-loop improvements (for human review)

**C1. Define test expectations** [SCRIPTED] Before a story is marked Done, every open question in its comments is either answered and turned into an acceptance criterion or test case, or explicitly accepted as out of scope with a linked follow-up.

- Where: issue tracker workflow (definition of done); owner type: delivery team with QE; addresses: H2, H4
- Recurrence protection: Questions such as the one on SHOP-455 become observable test expectations instead of staying in a comment thread.
- Status [DECISION]: proposed — not accepted

**C2. Release with informed confidence** [SCRIPTED] When a release note accepts an uncovered condition, the approval names a compensating control (a monitor, a feature flag or a dated follow-up) for that condition.

- Where: release checklist; owner type: release manager; addresses: H3
- Recurrence protection: Accepted risks get a detection path instead of relying on a follow-up ticket alone.
- Status [DECISION]: proposed — not accepted

**C3. Monitor production** [SCRIPTED] Alert when any order's discount exceeds the configured percentage of its undiscounted subtotal.

- Where: monitoring; owner type: platform / SRE with the checkout team; addresses: H6
- Recurrence protection: Detects discount calculation errors within minutes instead of at the next daily reconciliation.
- Review flag [CHECK]: none of the hypotheses it addresses is SUPPORTED after checks; treat as exploratory, not as a fix for an established gap
- Status [DECISION]: proposed — not accepted

**C4. Feed learning back into the knowledge base** [SCRIPTED] Improve testing of promotions and add more test cases.

- Where: quality knowledge base; owner type: QE; addresses: H2
- Recurrence protection: More coverage.
- Review flag [CHECK]: uses vague wording the methodology rejects: improve testing, add more test cases
- Status [DECISION]: proposed — not accepted

## 8. Decisions needed [DECISION]

Record decisions in `decisions.yaml` next to this report. This tool never marks a hypothesis as the cause, and never creates tickets, tests or monitoring.

- 7 hypotheses to accept, reject or investigate further
- 3 proposed regression tests and 4 proposed controls to accept or reject

## 9. Check log [CHECK]

| Step | Rule | Subject | Answered → after check | Reason |
| --- | --- | --- | --- | --- |
| 1-trace | G-TRACE-SUPPORT | PR #318 → junit:ci-unit | DIRECT → INFERRED | link 'PR #318 → junit:ci-unit' was claimed as DIRECT but nothing it cites records it (no collected relationship record ties the two items, no cited artifact of one item names the other, and no quoted passage was found in a cited artifact); relabelled INFERRED. |
| 1-trace | ENGINE-NOTE | — | — | inferred link 'PR #318 → junit:ci-unit' cannot be CONFIRMED; downgraded to STRONGLY SUPPORTED. |
| 2-validation | G-MATERIAL-DIFFERENCE | TC-211 | YES → UNCERTAIN | 'TC-211' was marked able to detect the failure although material differences from the failing condition are recorded; treated as UNCERTAIN. |
| 2-validation | G-GAP-DERIVED | — | SUPPORTED → UNCERTAIN | the regression-selection gap is UNCERTAIN, not SUPPORTED as the model's own answers about each test would imply. 'TC-211' was marked able to detect the failure although material differences from the failing condition are recorded; treated as UNCERTAIN. |
| 2-validation | G-ACTIVITY-ESTABLISHMENT | Automate what is repeatable | STRONGLY SUPPORTED → UNKNOWN / INSUFFICIENT EVIDENCE | 'Automate what is repeatable' was STRONGLY SUPPORTED; citation provenance does not establish the activity interpretation. Held unresolved; this does not change independently recorded execution or release facts. |
| 2-validation | G-ACTIVITY-ESTABLISHMENT | Analyze change impact | STRONGLY SUPPORTED → UNKNOWN / INSUFFICIENT EVIDENCE | 'Analyze change impact' was STRONGLY SUPPORTED; citation provenance does not establish the activity interpretation. Held unresolved; this does not change independently recorded execution or release facts. |
| 2-validation | G-ACTIVITY-ESTABLISHMENT | Release with informed confidence | CONFIRMED → UNKNOWN / INSUFFICIENT EVIDENCE | 'Release with informed confidence' was CONFIRMED; citation provenance does not establish the activity interpretation. Held unresolved; this does not change independently recorded execution or release facts. |
| 3-hypotheses | H-CONTRADICTED | H4 | STRONGLY SUPPORTED → POSSIBLE CONTRIBUTING FACTOR | H4 has a contradicting quote found in documentation.md; lowered to POSSIBLE CONTRIBUTING FACTOR until a reviewer resolves the conflict. |
| 3-hypotheses | H-REGRESSION-GAP | H5 | STRONGLY SUPPORTED → UNKNOWN | H5 attributes the escape to regression selection, but the engine-derived regression-selection gap is UNCERTAIN (it needs a test classified DETECTING that was not run); set to UNKNOWN. |
| 3-hypotheses | G-CITATION-UNRESOLVED | H6 | monitoring-alerts.md → | 'H6' cited 'monitoring-alerts.md', which names no evidence collected for this assessment (or an identifier the evidence it names does not hold); removed from its citations. Remaining: none. |
| 3-hypotheses | G-EVIDENCE-REF | H6 | STRONGLY SUPPORTED → UNKNOWN | 'H6' was STRONGLY SUPPORTED without any evidence reference that checks out against the case artifacts; downgraded to UNKNOWN. |
| 3-hypotheses | H-POST-RELEASE-ONLY | H7 | STRONGLY SUPPORTED → POSSIBLE CONTRIBUTING FACTOR | H7 is supported only by evidence produced after release (remediation_changes); that shows what was learned, not what was knowable before release. Lowered to POSSIBLE CONTRIBUTING FACTOR. |
| 3-hypotheses | H-PROPOSAL-BASIS | T3 | — | proposal T3: none of the hypotheses it addresses is SUPPORTED after checks; treat as exploratory, not as a fix for an established gap. |
| 3-hypotheses | H-PROPOSAL-BASIS | C3 | — | proposal C3: none of the hypotheses it addresses is SUPPORTED after checks; treat as exploratory, not as a fix for an established gap. |
| 3-hypotheses | H-VAGUE-ACTION | C4 | — | proposal C4: uses vague wording the methodology rejects: improve testing, add more test cases. |

## 10. Evidence reviewed

| Evidence ID | Category | File | SHA-256 (first 12) |
| --- | --- | --- | --- |
| `issue:SHOP-482` | production_issue | issues/SHOP-482.yaml | 4cb4f39d42b8 |
| `issue:SHOP-455` | originating_work | issues/SHOP-455.yaml | 23fa2ccfb586 |
| `documentation.md` | documentation | documentation.md | 5e55cd958396 |
| `code-change.md` | implementation_changes | code-change.md | b52cca1217b6 |
| `fix-change.md` | remediation_changes | fix-change.md | 44ff5df9932c |
| `tests.md` | test_evidence | tests.md | 9d41e68a3681 |
| `junit:ci-unit` | ci_evidence | test-results/ci-unit.xml | 10a0cfef5ab9 |
| `release:4.2.0` | release_evidence | releases/4.2.0.yaml | 07b502921442 |
| `production-learning.md` | production_evidence | production-learning.md | 0aa161306be8 |
| `adapter:relationships` | additional_evidence | derived:recorded-relationships.md | derived |
