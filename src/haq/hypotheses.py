"""Step 3 of an investigation: hypotheses, unknowns and proposals, and their checks.

The model (or a scripted/agent answer) proposes hypotheses with supporting and
contradicting quotes, the unknowns, and candidate regression tests and preventive
controls. Code then checks them. The checks reuse the engine's functions wherever the
engine already has the rule:

- quote provenance: ``claim_evidence.bind_claims`` (exact source/quote check)
- citation resolution: ``guards.reject_unresolved_citations`` (G-CITATION-UNRESOLVED)
- strong claims need a resolving reference: ``guards._downgrade_unsupported`` (G-EVIDENCE-REF)
- absence claims need collected evidence: ``guards.downgrade_absence_claims`` (G-ABSENCE)

and adds rules specific to this skill (H-* IDs below). No check can establish that a
quote *means* what the hypothesis says; semantic support always stays UNVERIFIED and a
hypothesis is never presented as a confirmed root cause.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from ._engine import guards
from ._engine.claim_evidence import EvidenceLink, bind_claims
from ._engine.evidence import EvidenceBundle
from ._engine.guards import GuardNote, norm
from ._engine.passes import ENGINE_SET, TraceabilityResult, ValidationAssessment

LAYERS = (
    "Defect introduction",
    "Prevention gap",
    "Detection / escape gap",
    "Release decision gap",
    "Production detection gap",
    "Learning gap",
)

# Check IDs added by this skill. Engine guard IDs keep their own names.
H_QUOTE = "H-QUOTE-PROVENANCE"          # a strong hypothesis needs a supporting quote found in its cited source
H_CONTRADICTED = "H-CONTRADICTED"       # a verified contradicting quote caps the hypothesis and flags it for review
H_POST_RELEASE = "H-POST-RELEASE-ONLY"  # support only from post-release/fix evidence cannot confirm a pre-release cause
H_REGRESSION = "H-REGRESSION-GAP"       # a regression-selection hypothesis needs the engine-derived gap to be SUPPORTED
H_LAYER = "H-LAYER"                     # the causal layer must be one the methodology defines
H_PROPOSAL_BASIS = "H-PROPOSAL-BASIS"   # a proposal must address a hypothesis that is not unknown or contradicted
H_VAGUE = "H-VAGUE-ACTION"              # the methodology's action-quality filter, applied lexically

# The methodology's action-quality filter (references/evidence-and-actions.md), as phrases.
VAGUE_PHRASES = ("improve testing", "improve requirements", "communicate better", "add more automation",
                 "increase coverage", "monitor better", "improve process", "add more test cases",
                 "improve communication")

POST_RELEASE_CATEGORIES = {"remediation_changes", "production_evidence"}


class Quote(BaseModel):
    source: str = Field(description="The evidence ID of the artifact, copied exactly as written in brackets in the evidence index.")
    quote: str = Field(description="Exact text copied from that artifact. Not a paraphrase.")


class Hypothesis(BaseModel):
    id: str = Field(description="H1, H2, ...")
    statement: str = Field(description="One testable statement about why the defect was introduced, escaped, or was detected late.")
    layer: str = Field(description="Exactly one causal layer: " + "; ".join(LAYERS) + ".")
    loop_activity: str = Field(description="The Quality Loop activity this bears on, written exactly as in the methodology, or NONE.")
    confidence: str = Field(description="An evidence confidence level exactly as defined in the methodology excerpts.")
    supporting: list[Quote] = Field(description="Evidence that supports the hypothesis, as exact quotes.")
    contradicting: list[Quote] = Field(description="Evidence that weakens or contradicts it, as exact quotes. Empty list if none was found.")
    what_would_settle_it: str = Field(description="Which evidence, not yet in the case, would confirm or refute it.")
    cited_sources: list[str] = Field(default_factory=list, description=f"{ENGINE_SET}: sources of the supporting quotes.")
    check_status: str = Field("", description=f"{ENGINE_SET}: SUPPORTED, CONTRADICTED or NOT ESTABLISHED.")
    quote_checks: list[dict] = Field(default_factory=list, description=f"{ENGINE_SET}: per-quote provenance results.")


class WorkedItem(BaseModel):
    statement: str = Field(description="A control that worked (detection, rollback, a test that protected nearby behavior, ...).")
    supporting: list[Quote]
    quote_checks: list[dict] = Field(default_factory=list, description=f"{ENGINE_SET}: per-quote provenance results.")


class ProposedTest(BaseModel):
    id: str = Field(description="T1, T2, ...")
    title: str
    condition: str = Field(description="Given / when / then, concrete enough to implement.")
    level: str = Field(description="unit, integration, API, UI, contract, or manual exploratory.")
    destination: str = Field(description="Where it would live: test-management system, automation repository, ...")
    addresses: list[str] = Field(description="IDs of the hypotheses this test would detect or rule out.")
    review_flags: list[str] = Field(default_factory=list, description=f"{ENGINE_SET}: reasons a reviewer should look twice.")


class ProposedControl(BaseModel):
    id: str = Field(description="C1, C2, ...")
    loop_activity: str = Field(description="The Quality Loop activity, written exactly as in the methodology.")
    control: str = Field(description="WHAT changes, concretely.")
    destination: str = Field(description="WHERE it changes.")
    owner_type: str = Field(description="WHO would normally own it (a role, never a named person).")
    recurrence_protection: str = Field(description="HOW it reduces recurrence or improves detection.")
    addresses: list[str] = Field(description="IDs of the hypotheses that justify it.")
    review_flags: list[str] = Field(default_factory=list, description=f"{ENGINE_SET}: reasons a reviewer should look twice.")


class QualityInvestigation(BaseModel):
    hypotheses: list[Hypothesis]
    unknowns: list[str] = Field(description="Questions the evidence cannot answer, each naming the missing evidence.")
    what_worked: list[WorkedItem]
    proposed_regression_tests: list[ProposedTest]
    proposed_controls: list[ProposedControl]


TASK = (
    "Using the checked results of the earlier steps and the evidence, propose hypotheses that explain how this "
    "defect was introduced, why it escaped pre-release validation, and how it was detected. For each hypothesis "
    "give its causal layer, the Quality Loop activity it bears on, a confidence level, exact supporting quotes "
    "and exact contradicting quotes (search for contradicting evidence on purpose), and what evidence would settle "
    "it. Include competing hypotheses when the evidence allows more than one explanation. A missing artifact is a "
    "gap, not a cause. Never criticize a pre-release decision with information that only became available after "
    "release. Do not call anything a root cause. Then list the unknowns, what worked, 1-4 proposed regression "
    "tests and 1-4 proposed preventive controls, each naming the hypothesis IDs it addresses. Proposals are for a "
    "human to review; they are not decisions."
)


def _flat(text: str) -> str:
    return " ".join(text.split())


def _sources(bundle: EvidenceBundle) -> dict[str, dict[str, str]]:
    """Every artifact by its evidence ID and by its file name, whitespace-flattened for the quote check."""
    out: dict[str, dict[str, str]] = {}
    for a in bundle.artifacts():
        for key in {a.ref, a.name}:
            out[key.lower()] = {"content": _flat(a.content)}
    return out


def _check_quotes(quotes: list[Quote], sources: dict) -> list[dict]:
    """Engine bind_claims, one quote per claim, keyed by source; returns status per quote."""
    if not quotes:
        return []
    links = {"q": [EvidenceLink(source_id=q.source.strip().strip("[]").lower(), part="content", quote=_flat(q.quote))
                   for q in quotes]}
    bound = bind_claims({"q": "quote check"}, links, sources)["q"]
    return [{"source": q.source, "status": c["status"]} for q, c in zip(quotes, bound.quote_checks)]


def _categories(bundle: EvidenceBundle, refs: list[str]) -> set[str]:
    return {a.category for ref in refs for a in guards.cited_artifacts(ref, bundle)}


def check_investigation(inv: QualityInvestigation, bundle: EvidenceBundle, levels: list[str],
                        loop_activities: list[str], trace: TraceabilityResult | None,
                        validation: ValidationAssessment | None) -> list[GuardNote]:
    """Apply every check in place. Returns the notes, each naming the rule that changed something."""
    key = "3-hypotheses"
    strong = {norm(level) for level in levels[:2]}
    possible, weakest = levels[2], levels[-1]
    sources = _sources(bundle)
    signal_ids = guards.verified_signal_ids(trace, bundle)
    notes: list[GuardNote] = []

    # Engine-set fields are never accepted from an answer.
    for h in inv.hypotheses:
        h.cited_sources = [q.source for q in h.supporting]
        h.check_status, h.quote_checks = "", []
    for item in (*inv.proposed_regression_tests, *inv.proposed_controls):
        item.review_flags = []

    for h in inv.hypotheses:
        if h.layer not in LAYERS:
            match = next((l for l in LAYERS if guards.squash(l) == guards.squash(h.layer)), None)
            notes.append(GuardNote(f"{key}: {h.id} named layer '{h.layer}', which the methodology does not define"
                                   + (f"; read as '{match}'." if match else "; kept for review."),
                                   H_LAYER, "HYPOTHESIS", subject=h.id, original=h.layer, corrected=match or h.layer))
            h.layer = match or h.layer

        # Engine G-CITATION-UNRESOLVED and G-EVIDENCE-REF over the cited sources.
        found, _ = guards.reject_unresolved_citations([(h, h.id, "confidence", "cited_sources")], strong, weakest,
                                                     bundle, signal_ids, key)
        notes += found
        notes += guards._downgrade_unsupported([(h, h.id, "confidence", "cited_sources")], strong, weakest,
                                               bundle, signal_ids, key)

        # Quote provenance (engine bind_claims).
        h.quote_checks = ([{"role": "supporting", **c} for c in _check_quotes(h.supporting, sources)]
                          + [{"role": "contradicting", **c} for c in _check_quotes(h.contradicting, sources)])
        verified_support = [c for c in h.quote_checks if c["role"] == "supporting" and c["status"] == "VERIFIED_QUOTE"]
        verified_contra = [c for c in h.quote_checks if c["role"] == "contradicting" and c["status"] == "VERIFIED_QUOTE"]
        if norm(h.confidence) in strong and not verified_support:
            was, h.confidence = h.confidence, possible
            notes.append(GuardNote(
                f"{key}: {h.id} was {was}, but none of its supporting quotes was found in the source it cites; "
                f"lowered to {possible}.", H_QUOTE, "HYPOTHESIS", subject=h.id, original=was, corrected=possible))

        # Engine G-ABSENCE: an absence cannot be read from evidence nobody collected.
        notes += guards.downgrade_absence_claims([(h, f"{h.layer} {h.loop_activity}", "confidence", "statement")],
                                                 strong, weakest, bundle, key)

        # Support that exists only after release cannot confirm a pre-release cause (hindsight rule).
        support_categories = _categories(bundle, [c["source"] for c in verified_support])
        if (h.layer != "Production detection gap" and support_categories
                and support_categories <= POST_RELEASE_CATEGORIES and norm(h.confidence) in strong):
            was, h.confidence = h.confidence, possible
            notes.append(GuardNote(
                f"{key}: {h.id} is supported only by evidence produced after release ("
                f"{', '.join(sorted(support_categories))}); that shows what was learned, not what was knowable "
                f"before release. Lowered to {possible}.", H_POST_RELEASE, "HYPOTHESIS", subject=h.id,
                original=was, corrected=possible))

        # Regression selection is derived by the engine from the test-relevance rows, never asserted.
        gap = getattr(validation, "regression_selection_gap", "") if validation else ""
        if (guards.REGRESSION_ACTIVITY in guards.squash(h.loop_activity)
                and gap != guards.GAP_SUPPORTED and norm(h.confidence) != norm(weakest)):
            was, h.confidence = h.confidence, weakest
            notes.append(GuardNote(
                f"{key}: {h.id} attributes the escape to regression selection, but the engine-derived "
                f"regression-selection gap is {gap or 'not assessed'} (it needs a test classified DETECTING that "
                f"was not run); set to {weakest}.", H_REGRESSION, "HYPOTHESIS", subject=h.id,
                original=was, corrected=weakest))

        if verified_contra:
            if norm(h.confidence) in strong:
                was, h.confidence = h.confidence, possible
                notes.append(GuardNote(
                    f"{key}: {h.id} has a contradicting quote found in {', '.join(c['source'] for c in verified_contra)}; "
                    f"lowered to {possible} until a reviewer resolves the conflict.", H_CONTRADICTED, "HYPOTHESIS",
                    subject=h.id, original=was, corrected=possible))
            h.check_status = "CONTRADICTED"
        elif verified_support and norm(h.confidence) != norm(weakest):
            h.check_status = "SUPPORTED"
        else:
            h.check_status = "NOT ESTABLISHED"

    for w in inv.what_worked:
        w.quote_checks = _check_quotes(w.supporting, sources)

    # Proposals: basis and the methodology's action-quality filter.
    status = {h.id: h.check_status for h in inv.hypotheses}
    activities = {guards.squash(a) for a in loop_activities}
    for item in (*inv.proposed_regression_tests, *inv.proposed_controls):
        unknown = [a for a in item.addresses if a not in status]
        established = [a for a in item.addresses if status.get(a) == "SUPPORTED"]
        if unknown:
            item.review_flags.append(f"addresses {', '.join(unknown)}, which is not a hypothesis in this result")
        if not established:
            item.review_flags.append("none of the hypotheses it addresses is SUPPORTED after checks; "
                                     "treat as exploratory, not as a fix for an established gap")
        text = " ".join(str(v) for v in item.model_dump(exclude={"review_flags", "addresses"}).values()).lower()
        vague = [p for p in VAGUE_PHRASES if p in text]
        if vague:
            item.review_flags.append(f"uses vague wording the methodology rejects: {', '.join(vague)}")
        if isinstance(item, ProposedControl) and guards.squash(item.loop_activity) not in activities:
            item.review_flags.append(f"loop activity '{item.loop_activity}' is not one of the methodology's ten")
        for flag in item.review_flags:
            notes.append(GuardNote(f"{key}: proposal {item.id}: {flag}.", H_VAGUE if "vague" in flag else H_PROPOSAL_BASIS,
                                   "PROPOSAL", subject=item.id))
    return notes


ROOT_CAUSE = re.compile(r"\broot[- ]cause\b", re.I)
