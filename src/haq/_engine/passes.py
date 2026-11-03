"""The assessment passes: what each one is asked, which methodology excerpts and evidence
categories it sees, which earlier results it builds on, and the shape of its output.

The methodology text itself is never restated here. Each pass names the files/sections to
load from methodology/, and the task text only tells the model what this pass must produce."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr, model_validator
from pydantic.json_schema import SkipJsonSchema

from .evidence import CATEGORIES
from .methodology import Methodology

CONFIDENCE = "An evidence confidence level exactly as defined in the methodology excerpts."
ACTIVITY_STATUS = (
    "An evidence confidence level exactly as defined in the methodology excerpts, "
    "or NOT APPLICABLE, or UNKNOWN / INSUFFICIENT EVIDENCE."
)
CITATIONS = "Artifact file names and identifiers that support this, e.g. 'tests.md: TC-12'."
SIGNAL_IDS = (
    "IDs (for example signal-001) of the pass 1 critical signals that the findings in this "
    "result rely on. Empty list if none."
)
# Fields whose description contains this marker are filled in by the engine after the
# pass returns. They are removed from the schema shown to the model (see model_schema).
ENGINE_SET = "Set by the engine"


# ---------------------------------------------------------------- output models


class TraceLink(BaseModel):
    from_item: str
    to_item: str
    source_artifact: str = Field("", description="The evidence ID of the artifact that describes from_item, copied exactly as it is written in brackets in the evidence index (for example jira:PW-140). Never build a file name from an ID.")
    target_artifact: str = Field("", description="The evidence ID of the artifact that describes to_item, copied exactly as it is written in brackets in the evidence index (for example jira:PW-140). Never build a file name from an ID.")
    relationship_type: str = Field(
        "",
        description="Short verb phrase, e.g. references, implements, tested by, released "
        "in, detected by.",
    )
    direct_or_inferred: str = Field(
        "INFERRED",
        description="Exactly one of: DIRECT, INFERRED. DIRECT only when an artifact "
        "explicitly records the relationship: a link field, a URL, or an identifier of one "
        "item written in the other item's artifact. A relationship based on a matching "
        "issue key in a name, branch naming, timing, feature terminology or commit context "
        "is INFERRED.",
    )
    evidence_quote: str = Field(
        "",
        description="For DIRECT: the exact text, copied from an artifact, that records the "
        "relationship. For INFERRED: empty string.",
    )
    confidence: str = Field(description=CONFIDENCE)
    basis: str = Field(description="The explicit reference or reasoning behind this link.")
    unresolved_citations: list[str] = Field(default_factory=list, description=f"{ENGINE_SET}: citations that named no collected evidence (xkn), as given.")
    verified_support: str = Field("", description=f"{ENGINE_SET}: the verified evidence that supports it, empty when unresolved (xkn).")


class TimelineEvent(BaseModel):
    when: str = Field(description="Date/time as stated in the evidence, or 'unknown'.")
    event: str
    source: str = Field(description="The evidence ID of the artifact the event comes from, copied exactly as it is written in brackets in the evidence index.")
    unresolved_citations: list[str] = Field(default_factory=list, description=f"{ENGINE_SET}: citations that named no collected evidence (xkn), as given.")


class CriticalSignal(BaseModel):
    id: str = Field("", description=f"{ENGINE_SET}: stable ID such as signal-001.")
    source_artifact: str = Field(description="The evidence ID of the artifact this signal comes from, copied exactly as it is written in brackets in the evidence index.")
    description: str = Field(description="What the signal says, concretely, not summarized away.")
    timing: str = Field(description="Exactly one of: pre-release, post-release.")
    relevance: str = Field(
        description="Exactly one of: HIGH, MEDIUM, LOW — how directly this bears on "
        "requirement interpretation, a known limitation, risk, the release decision, or "
        "validation depth."
    )
    confidence: str = Field(description=CONFIDENCE)
    unresolved_citations: list[str] = Field(default_factory=list, description=f"{ENGINE_SET}: citations that named no collected evidence (xkn), as given.")
    verified: bool | None = Field(None, description=f"{ENGINE_SET}: whether its source resolves to collected evidence that holds what it says (xkn).")


class TraceabilityResult(BaseModel):
    production_problem: str = Field(
        description="What happened, expected vs actual behavior, impact, how it was detected."
    )
    links: list[TraceLink]
    timeline: list[TimelineEvent]
    known_before_release: list[str]
    learned_after_release: list[str]
    ambiguities: list[str]
    missing_evidence: list[str]
    critical_signals: list[CriticalSignal] = Field(
        description="Specific evidence — a comment, a decision, a caveat, a stated "
        "limitation — that could materially change requirement interpretation, risk, the "
        "release decision, or validation depth. Look past the obvious artifacts for things "
        "like an unresolved comment thread or a commitment that was never followed up on. "
        "An empty list is a real answer only if nothing like this was found."
    )


class ActivityFinding(BaseModel):
    activity: str = Field(description="Quality Loop activity name as written in the methodology.")
    finding: str
    status: str = Field(description=ACTIVITY_STATUS)
    evidence: list[str] = Field(description=CITATIONS)
    evidence_status: str = Field("NOT_ESTABLISHED", description=f"{ENGINE_SET}: activity interpretation support, distinct from citation provenance.")
    evidence_status_reason: str = Field("No independent semantic support verified.", description=f"{ENGINE_SET}: why this activity interpretation remains unresolved.")


class RequirementsAssessment(BaseModel):
    activities: list[ActivityFinding]
    missing_evidence: list[str]
    used_critical_signal_ids: list[str] = Field(default_factory=list, description=SIGNAL_IDS)


class TestRelevance(BaseModel):
    """Whether one existing test could actually have exposed the production failure."""

    __test__ = False  # not a pytest class

    test: str = Field(description="Test, test case or suite identifier as written in the evidence.")
    tested_trigger_condition: str = Field(
        description="The trigger or condition this test exercises, as the evidence states it."
    )
    tested_state: str = Field(description="The user or system state the test sets up.")
    expected_behavior: str = Field(description="What the test asserts.")
    failing_production_condition: str = Field(
        description="The trigger and state under which the production failure occurred."
    )
    overlap: str = Field(description="What the test and the failing condition have in common.")
    material_differences: str = Field(
        description="Differences between the tested condition and the failing production "
        "condition that would let the test pass while the defect exists. 'None' if none."
    )
    could_this_test_detect_the_failure: str = Field(
        description="Exactly one of: YES, NO, UNCERTAIN. YES only if the test, as "
        "described in the evidence, exercises the failing condition itself. The same "
        "feature area, similar terminology or adjacent behavior is not enough."
    )
    was_selected_or_executed: str = Field(
        description="Exactly one of: YES, NO, UNKNOWN — for the release under assessment."
    )
    confidence: str = Field(description=CONFIDENCE)
    reasoning: str
    evidence: list[str] = Field(description=CITATIONS)
    classification: str = Field(
        "",
        description=f"{ENGINE_SET}: DETECTING, RELATED BUT NOT DETECTING, or UNCERTAIN.",
    )

    # Runtime-only constraints from actual deterministic corrections. Never accepted
    # from model JSON or used as authority when loading an old result.
    _unresolved_constraints: dict[str, str] = PrivateAttr(default_factory=dict)

    def constrain_interpretation(self, field: str, constraint: str, weakest: str) -> dict:
        original = {"status": "SUPERSEDED_UNVERIFIED_PROPOSAL", "reasoning": self.reasoning,
                    "confidence": self.confidence}
        self._unresolved_constraints[field] = constraint
        self.refresh_interpretation(weakest)
        return original

    def refresh_interpretation(self, weakest: str) -> None:
        active = [text for field, text in self._unresolved_constraints.items()
                  if getattr(self, field).strip().upper() in {"UNKNOWN", "UNCERTAIN"}]
        if active:
            self.reasoning = "Effective unresolved row constraints: " + " ".join(active)
            self.confidence = weakest


class ValidationAssessment(BaseModel):
    activities: list[ActivityFinding]
    test_coverage_failure_mode: str = Field(
        description="Which test-coverage failure mode from the methodology applies and why, "
        "or UNKNOWN with what is missing."
    )
    ci_evidence_provided: str = Field(
        description="What the CI evidence actually demonstrated about the failing behavior."
    )
    release_signals: list[str] = Field(
        description="Signals bearing on this defect that were available at release time."
    )
    missing_evidence: list[str]
    test_relevance: list[TestRelevance] = Field(
        default_factory=list,
        description="One entry for every existing test, test case or suite that the "
        "evidence presents as related to the failing behavior, whether or not it was run "
        "for this release. Empty list only if the evidence names no such test.",
    )
    presented_test_inventory: dict = Field(default_factory=lambda: {"status": "unknown", "reason": "No saved actual admission inventory."},
        description=f"{ENGINE_SET}: structural row coverage of actual admitted test content, not semantic or connector completeness.")
    regression_selection_gap: str = Field(
        "",
        description=f"{ENGINE_SET} from test_relevance: SUPPORTED, NOT SUPPORTED, or UNCERTAIN.",
    )
    used_critical_signal_ids: list[str] = Field(default_factory=list, description=SIGNAL_IDS)


class CausalFinding(BaseModel):
    layer: str = Field(description="Causal layer name as written in the methodology.")
    finding: str = Field(description="The finding, or that no finding applies to this layer.")
    confidence: str = Field(description=CONFIDENCE)
    evidence: list[str] = Field(description=CITATIONS)
    alternative_explanations: list[str]


class DefectMechanism(BaseModel):
    """How the defect works, as an artifact records it. Kept in separate fields so that
    the specifics (where, what, the recorded fix) are not paraphrased away."""

    described_in_evidence: str = Field(
        description="Exactly one of: YES, NO. YES only when an artifact itself describes "
        "the technical mechanism or root cause. NO leaves the other fields empty."
    )
    location: str = Field(
        "", description="Where the defect is, copied exactly as the artifact writes it: "
        "file path, line number, component, function. Empty when the artifact names none."
    )
    mechanism: str = Field("", description="What goes wrong and why, with the artifact's own technical terms.")
    recorded_fix: str = Field(
        "", description="The fix the artifact itself proposes or records, in its own terms. "
        "Empty when it records none. Not a fix taken from a remediation change."
    )
    evidence_quote: str = Field(
        "", description="The sentence or sentences of the artifact that state the root "
        "cause, copied character for character. Do not paraphrase or shorten words."
    )
    evidence: list[str] = Field(default_factory=list, description=CITATIONS)
    analysis_timing: str = Field(
        "unknown", description="Exactly one of: pre-release, post-release, unknown — when the analysis was written."
    )
    quote_verified: bool = Field(False, description=f"{ENGINE_SET}: whether evidence_quote was found in a cited artifact.")
    supporting_span: str = Field(
        "", description=f"{ENGINE_SET}: the passage of a cited artifact that was found in it and names what the mechanism names, as the artifact writes it."
    )
    supporting_span_sources: list[str] = Field(
        default_factory=list, description=f"{ENGINE_SET}: the evidence IDs of the artifacts that passage was found in."
    )
    confidence: str = Field(
        "", description="Exactly one of the confidence levels: how well the cited artifact supports this account of how "
        "the defect works (its trigger, state, expected and observed behavior). It says nothing about which change "
        "introduced the defect. Empty when described_in_evidence is NO. The engine sets the final value: the strongest "
        "level needs a quoted passage that is in the cited artifact and is about this mechanism, whatever is stated here."
    )


class RecordedAttribution(BaseModel):
    """Something the production issue records about the defect's origin: a
    classification, a release attribution, a root-cause category. Reported as recorded,
    not as established by the assessment."""

    value: str = Field(description="The recorded value, copied exactly, e.g. a classification or a label naming a release.")
    recorded_as: str = Field(description="Where it is recorded: the field's name as written, or 'label'.")
    meaning: str = Field("", description="One sentence: what it says about the defect's origin.")
    evidence: list[str] = Field(default_factory=list, description=CITATIONS)


class MissedOpportunity(BaseModel):
    activity: str = Field(
        description="The Quality Loop activity it is anchored to, or 'None identified'."
    )
    explanation: str
    confidence: str = Field(description=CONFIDENCE)
    evidence: list[str] = Field(default_factory=list, description=CITATIONS)


DECISION_ANSWERS = ("YES", "NO", "UNKNOWN")


def decision_answer(text: str | None) -> str | None:
    """A decision claim's answer in its vocabulary, or None when it is not one of YES, NO, UNKNOWN: missing, a confidence
    label, a contradiction ("YES/NO") or a sentence (cu0). Case, surrounding whitespace, quotes or emphasis and a final
    full stop are not part of the answer; nothing else is read into it, so no answer is guessed from a label or prose."""
    token = " ".join(str(text or "").split()).strip("\"'`*_ ").rstrip(".").strip().upper()
    return token if token in DECISION_ANSWERS else None


class KeyClaim(BaseModel):
    answer: str = Field(description="Exactly one of: YES, NO, UNKNOWN.")
    claim: str = Field(description="One sentence stating what the evidence shows.")
    evidence_refs: list[str] = Field(description=CITATIONS)
    confidence: str = Field(description=CONFIDENCE)
    rests_on: str = Field("", description=f"{ENGINE_SET}: what the claim rests on: for one that presupposes another, SATISFIED, INDEPENDENT or NOT ESTABLISHED, and why (9fz); for an absence the records decide, ESTABLISHED with its scope and chain, or NOT ESTABLISHED with what blocks it (d20).")

    evidence_status: str = Field("NOT_ESTABLISHED", description=f"{ENGINE_SET}: ESTABLISHED, EVIDENCE_LINKED_REVIEW_REQUIRED or NOT_ESTABLISHED; never inferred from confidence or citation resolution alone (5xg).")
    evidence_status_reason: str = Field("Not assessed against verified support.", description=f"{ENGINE_SET}: verified support or the condition still missing (5xg).")
    verified_support_refs: list[str] = Field(default_factory=list, description=f"{ENGINE_SET}: references supplied by the independent support rule, not the model (5xg).")


class DecisionClaims(BaseModel):
    """The decision-driving claims of the assessment, each tied to evidence."""

    requirement_was_explicit: KeyClaim = Field(
        description="Did a requirement available before implementation explicitly define "
        "the behavior that failed in production?"
    )
    implementation_contradicted_requirement: KeyClaim = Field(
        description="Did the implementation contradict or omit behavior that a requirement "
        "explicitly defined?"
    )
    relevant_test_existed: KeyClaim = Field(
        description="Did a test exist before release that exercises the failing condition "
        "itself (not merely adjacent behavior)?"
    )
    relevant_test_was_executed: KeyClaim = Field(
        description="Was such a test executed for this release?"
    )
    signal_failed_before_release: KeyClaim = Field(
        description="Did any test, check or review bearing on this defect fail or raise a "
        "warning before release?"
    )
    warning_evidence_available_to_release_decision: KeyClaim = Field(
        description="Does the evidence show that information bearing on this defect was in "
        "front of whoever made the release decision?"
    )
    # Has a default so that results saved before this question existed still load. The model
    # is asked for it like every other field (see model_schema).
    release_signal_acted_upon: KeyClaim = Field(
        default_factory=lambda: KeyClaim(answer="UNKNOWN", claim="", evidence_refs=[], confidence="UNKNOWN"),
        description="Was a failed or warning signal bearing on this defect acted upon before the "
        "release went ahead: the release held, the failure investigated, re-run or fixed, or the "
        "failure explicitly accepted? NO only when the evidence shows the release went ahead with "
        "that signal standing and records nothing done about it. UNKNOWN when no such signal is in "
        "evidence, or when nothing records what was done.",
    )


class CausalAssessment(BaseModel):
    layers: list[CausalFinding]
    earliest_reasonable_missed_opportunity: MissedOpportunity
    hindsight_check: str = Field(
        description="How pre-release knowledge was kept separate from post-release learning."
    )
    decision_claims: DecisionClaims | None = None
    defect_mechanism: DefectMechanism | None = None
    recorded_attributions: list[RecordedAttribution] | None = None
    release_decision_gap: str = Field(
        "",
        description=f"{ENGINE_SET} from the three release decision claims (a signal failed before release, it was "
        "available to the release decision, it was acted upon): SUPPORTED, NOT SUPPORTED, or UNCERTAIN.",
    )
    used_critical_signal_ids: list[str] = Field(default_factory=list, description=SIGNAL_IDS)


class LoopAssessment(BaseModel):
    activities: list[ActivityFinding]
    used_critical_signal_ids: list[str] = Field(default_factory=list, description=SIGNAL_IDS)


CORRECTIVE_ACTION, INVESTIGATIVE_ACTION = "CORRECTIVE_ACTION", "INVESTIGATIVE_ACTION"


class Action(BaseModel):
    """One proposed action. The engine validates it afterwards (flow/actions.py): what a
    pass writes here is a proposal, never a validated recommendation."""

    kind: Literal["CORRECTIVE_ACTION", "INVESTIGATIVE_ACTION"] = Field(
        description="CORRECTIVE_ACTION changes how work is done so that this failure mode does not recur. "
        "INVESTIGATIVE_ACTION establishes evidence that is missing before a control can be prescribed.")
    target_activity: str = Field(
        description="The Quality Loop activity this action changes, by its exact name, or 'None' for an action that only "
        "establishes missing evidence or traceability.")
    target_finding: str = Field(description="The causal layer or finding of the earlier results that this action answers, by its name.")
    action: str = Field(description="WHAT changes, concretely, in one sentence.")
    destination: str = Field(description="WHERE it changes: the system, record or workflow step.")
    reason: str = Field(description="WHY: the evidence-backed finding that justifies it.")
    owner_type: str = Field(description="WHO: the kind of role that owns it. Never a named person.")
    how: str = Field(description="HOW it is carried out: the concrete change to the process or system.")
    recurrence_protection: str = Field(description="RECURRENCE: how this prevents the same failure mode from recurring.")
    priority: str
    evidence: list[str] = Field(description=CITATIONS)
    intervention_id: str = Field(
        "", description="The ID of the candidate intervention this action adapts to the case, or empty when it adapts none.")

    @model_validator(mode="before")
    @classmethod
    def _earlier_form(cls, value: Any) -> Any:
        """A result saved before actions were structured names no kind, target or HOW. It is
        read as it is: the engine works those out, and says that it did."""
        if isinstance(value, dict):
            value = {"kind": "", "target_activity": "", "target_finding": "", "how": "", **value}
            if value["kind"] not in (CORRECTIVE_ACTION, INVESTIGATIVE_ACTION):
                investigative = re.match(r"\s*(?:investigate|determine|establish|find out|identify (?:whether|which|the origin))\b",
                                         str(value.get("action", "")), re.I)
                value["kind"], value["kind_declared"] = (INVESTIGATIVE_ACTION if investigative else CORRECTIVE_ACTION), False
        return value

    # False when the kind above was worked out by the engine because the result named none.
    kind_declared: SkipJsonSchema[bool] = True


class ActionPlan(BaseModel):
    actions: list[Action]
    what_worked: list[str]
    reusable_learning: list[str]
    open_questions: list[str]


class Challenge(BaseModel):
    target: str = Field(description="The specific claim, link, finding, or action challenged.")
    problem: str
    recommended_revision: str


class Contradiction(BaseModel):
    claim_a: str
    source_pass_a: str = Field(description="Which pass's result claim_a comes from.")
    claim_b: str
    source_pass_b: str = Field(description="Which pass's result claim_b comes from.")
    severity: str = Field(description="Exactly one of: HIGH, MEDIUM, LOW.")
    resolution: str = Field(
        description="How this was resolved from the evidence, naming which claim stands "
        "and why; or, if it cannot be resolved, exactly 'UNRESOLVED: preserved as an open "
        "question' — never leave both claims standing as facts."
    )


class SignalDismissal(BaseModel):
    signal_id: str = Field(description="ID of a pass 1 critical signal, e.g. signal-002.")
    reason: str = Field(description="Why the signal is not material to the conclusions.")


class CriticalReview(BaseModel):
    challenges: list[Challenge]
    contradictions: list[Contradiction] = Field(
        description="Every contradiction found between passes' claims, including but not "
        "limited to the candidates listed in the prompt. An empty list is a real answer "
        "only if none were found."
    )
    confirmed_sound: list[str] = Field(description="Conclusions that survived the review.")
    summary: str
    used_critical_signal_ids: list[str] = Field(
        default_factory=list,
        description="IDs of the pass 1 critical signals that the reviewed conclusions, or "
        "your revisions to them, depend on. Empty list if none.",
    )
    dismissed_critical_signals: list[SignalDismissal] = Field(
        default_factory=list,
        description="Critical signals you reviewed and found not material, each with the "
        "reason. Empty list if none.",
    )


def check_critical_review(result: BaseModel, methodology: Methodology) -> str | None:
    """Every challenge and every contradiction must actually say something, not just
    exist as an empty structural placeholder."""
    assert isinstance(result, CriticalReview)
    for challenge in result.challenges:
        if not challenge.recommended_revision.strip():
            return f"challenge '{challenge.target}' has no recommended_revision"
    for c in result.contradictions:
        if not c.resolution.strip():
            return f"contradiction between {c.source_pass_a} and {c.source_pass_b} has no resolution"
    return None


def check_causal_assessment(result: BaseModel, methodology: Methodology) -> str | None:
    assert isinstance(result, CausalAssessment)
    if result.decision_claims is None:
        return "decision_claims is missing; every decision-driving claim must be answered"
    if result.defect_mechanism is None:
        return "defect_mechanism is missing; set described_in_evidence to YES or NO"
    if result.recorded_attributions is None:
        return "recorded_attributions is missing; use an empty list when the issue records none"
    return None


def model_schema(model: type[BaseModel]) -> dict:
    """JSON Schema given to the model: every property required, engine-set fields removed.

    The Pydantic models keep defaults so that older saved results still load; the model
    itself is asked for every field so that none is silently skipped."""
    schema = model.model_json_schema()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                for name in [
                    n for n, p in properties.items() if ENGINE_SET in p.get("description", "")
                ]:
                    del properties[name]
                node["required"] = list(properties)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return schema


def pass_schema(spec: "PassSpec", methodology: Methodology) -> dict:
    """The JSON Schema one pass's model is given: model_schema, plus the counts the pass's
    check requires and JSON Schema can state. The Quality Loop mapping has exactly one entry
    per methodology activity (az3), as check_all_loop_activities and the task say."""
    schema = model_schema(spec.output)
    if spec.output is LoopAssessment:
        count = len(methodology.loop_activities())
        schema["properties"]["activities"].update(minItems=count, maxItems=count)
    return schema


def pass_task(spec: "PassSpec", methodology: Methodology) -> str:
    """One pass's task as the model is given it: the fixed text, and for the Quality Loop
    mapping the number and names of the activities its schema and check require (az3)."""
    if spec.output is not LoopAssessment:
        return spec.task
    names = methodology.loop_activities()
    return (f"{spec.task} The activities list has exactly {len(names)} entries, one for each of "
            f"these activities and no other: " + "; ".join(names) + ".")


# ---------------------------------------------------------------- output checks


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def check_all_loop_activities(result: BaseModel, methodology: Methodology) -> str | None:
    """Every activity defined in the methodology must be assessed exactly once."""
    assert isinstance(result, LoopAssessment)
    given = [_normalize(a.activity) for a in result.activities]
    expected = methodology.loop_activities()
    missing = [name for name in expected if not any(_normalize(name) in g for g in given)]
    if missing:
        return f"missing Quality Loop activities: {', '.join(missing)}"
    if len(given) != len(expected):
        return f"expected exactly {len(expected)} activities, got {len(given)}"
    return None


# ---------------------------------------------------------------- pass definitions


@dataclass(frozen=True)
class PassSpec:
    key: str
    title: str
    task: str
    # (methodology doc key, section heading prefix or None for the whole file)
    methodology: tuple[tuple[str, str | None], ...]
    # evidence categories shown in full
    evidence: tuple[str, ...] = ()
    # keys of earlier passes whose results are included
    prior: tuple[str, ...] = ()
    # structured output model; None means the pass returns Markdown
    output: type[BaseModel] | None = None
    check: Callable[[BaseModel, Methodology], str | None] | None = None
    # "categories": the evidence categories above, bounded by the evidence budget.
    # "referenced": only the artifacts cited by the earlier results under review.
    evidence_mode: str = "categories"
    # Planning estimates of this pass's own structured output, in tokens, used only by
    # `plan-assessment` before any result exists. A real run uses the actual sizes.
    planned_output_tokens: int = 1500
    planned_tokens_per_test: int = 0


CONFIDENCE_LEVELS = ("evidence-and-actions", "Evidence confidence levels")

PASSES: tuple[PassSpec, ...] = (
    PassSpec(
        key="1-traceability",
        title="Traceability and timeline",
        task=(
            "Reconstruct the evidence chain from the production problem back to the "
            "originating work, the implementing change, the tests, CI, and the release. "
            "Give every link its own confidence level and its basis. Mark every link DIRECT "
            "or INFERRED: DIRECT only when an artifact explicitly records the relationship, "
            "and then quote the exact text; never present an inferred relationship as a "
            "reference that one artifact makes to another. Name every ambiguity "
            "instead of resolving it silently. Build an evidence-supported timeline, then "
            "split what was known before release from what was learned after release. "
            "Separately, read every artifact specifically looking for critical signals: a "
            "comment, a decision, a caveat, or a stated limitation that could materially "
            "change requirement interpretation, risk, the release decision, or validation "
            "depth — especially an open question in a comment thread that was never "
            "resolved, or a commitment that was never followed up on. A root-cause analysis, "
            "a classification or a release attribution recorded on the issue (in a comment, a "
            "field or a label) is a critical signal too: record what it says, where it is "
            "recorded, and whether it was written before or after release. Record each one "
            "even if it does not change your other conclusions; later passes depend on seeing it."
        ),
        methodology=(
            ("skill", "Phase 2"),
            ("skill", "Phase 4"),
            ("skill", "Phase 5"),
            CONFIDENCE_LEVELS,
        ),
        evidence=CATEGORIES,
        output=TraceabilityResult,
        planned_output_tokens=2500,
        planned_tokens_per_test=60,
    ),
    PassSpec(
        key="2-intent-risk-requirements",
        title="Intent, risk, and requirements",
        task=(
            "Using only what was knowable before release, assess these four Quality Loop "
            "activities and no others: Clarify intent, Identify risk, Define test "
            "expectations, Create reusable quality artifacts. One entry per activity."
            " List in used_critical_signal_ids the ID of every pass 1 critical signal your "
            "findings rely on."
        ),
        methodology=(
            ("quality-loop", None),
            ("tool-mapping", "Issue tracker"),
            ("tool-mapping", "Documentation system"),
            CONFIDENCE_LEVELS,
        ),
        evidence=("production_issue", "originating_work", "requirements", "documentation"),
        prior=("1-traceability",),
        output=RequirementsAssessment,
        planned_output_tokens=1000,
    ),
    PassSpec(
        key="3-validation-release",
        title="Validation and release evidence",
        task=(
            "Assess these five Quality Loop activities and no others: Automate what is "
            "repeatable, Analyze change impact, Select regression intelligently, Release "
            "with informed confidence, Monitor production. One entry per activity. State "
            "which test-coverage failure mode applies, what the CI evidence actually "
            "demonstrated about the failing behavior, and which signals were available at "
            "release time. For every existing test, test case or suite the evidence presents "
            "as related, add a test_relevance entry comparing exactly what it tests with the "
            "condition that failed in production. Do not treat a test as able to detect the "
            "failure because it is in the same feature area, uses similar terminology or "
            "exercises adjacent behavior: if what it tests differs materially from the "
            "failing condition, answer NO, and if the evidence does not say, answer "
            "UNCERTAIN. Report a regression-selection problem only for a test that could "
            "have detected the failure and was not selected or executed."
            " List in used_critical_signal_ids the ID of every pass 1 critical signal your "
            "findings rely on."
        ),
        methodology=(
            ("quality-loop", None),
            ("tool-mapping", "CI/CD system"),
            ("tool-mapping", "Test-management system"),
            ("evidence-and-actions", "Test-coverage failure modes"),
            CONFIDENCE_LEVELS,
        ),
        evidence=(
            "production_issue",
            "implementation_changes",
            "test_evidence",
            "ci_evidence",
            "release_evidence",
            "production_evidence",
            "additional_evidence",
        ),
        prior=("1-traceability",),
        output=ValidationAssessment,
        planned_output_tokens=1500,
        planned_tokens_per_test=200,
    ),
    PassSpec(
        key="4-causal-analysis",
        title="Causal analysis",
        task=(
            "Produce one entry for each causal layer in the methodology, in order. Run each "
            "candidate finding through the root-cause quality check and downgrade it when "
            "it does not survive. A layer with no finding is a valid entry: say so. Then "
            "answer the earliest reasonable missed opportunity question, anchored to a "
            "Quality Loop activity, or state that none was identified. For 'Defect "
            "introduction', keep two questions apart. Which change introduced the defect is "
            "the only question the 'Defect introduction' layer answers: answer it only from "
            "an implementation change that the evidence ties to this failure and that is "
            "not a fix, and cite that change. The production issue, a description of how "
            "the defect works, a similar-looking change and a remediation change do not "
            "show which change introduced it: without such a change the layer is UNKNOWN. "
            "How the defect works is a separate finding, the observed defect mechanism: "
            "report it in defect_mechanism when an artifact describes it, and not in the "
            "'Defect introduction' layer. In defect_mechanism, copy the location and "
            "the recorded fix exactly as written, including file names, line numbers and "
            "function names, and copy the sentences that state the root cause into "
            "evidence_quote without changing them. Set described_in_evidence to NO when no "
            "artifact describes the mechanism. List in recorded_attributions every "
            "classification, release attribution or root-cause category that the "
            "production issue records as a field value or as a label (for example a "
            "classification field, or a label naming a release), one entry each, with the "
            "value copied exactly; use an empty list when it records none. Then answer every "
            "question in decision_claims with YES, NO or UNKNOWN and the evidence "
            "references that support the answer; answer UNKNOWN when no artifact supports "
            "it. Whether the implementation contradicted a requirement cannot be answered "
            "YES or NO without a requirement to compare it with: answer UNKNOWN then. "
            "Whether a signal bearing on this defect failed before release, whether it was in "
            "front of the release decision, and whether it was acted upon are three separate "
            "questions: answer each from its own evidence, and do not answer one from another. "
            "A result recorded after the release shows nothing about what was known before it."
            " List in used_critical_signal_ids the ID of every pass 1 critical signal your "
            "findings rely on."
        ),
        methodology=(
            ("causal-model", None),
            ("skill", "Phase 5"),
            CONFIDENCE_LEVELS,
        ),
        evidence=("production_issue", "remediation_changes", "production_evidence", "additional_evidence"),
        prior=("1-traceability", "2-intent-risk-requirements", "3-validation-release"),
        output=CausalAssessment,
        check=check_causal_assessment,
        planned_output_tokens=2500,
    ),
    PassSpec(
        key="5-quality-loop",
        title="Quality Loop mapping",
        task=(
            "Assess every activity of the Hyper-Agile Quality Loop, one entry per activity, "
            "in the methodology's order, using the activity names exactly as written. "
            "Consolidate the earlier pass results rather than re-deriving them. Keep "
            "NOT APPLICABLE and UNKNOWN / INSUFFICIENT EVIDENCE where they are the honest "
            "answer. Do not produce any numerical score or rating."
            " List in used_critical_signal_ids the ID of every pass 1 critical signal your "
            "findings rely on."
        ),
        methodology=(("quality-loop", None), CONFIDENCE_LEVELS),
        prior=(
            "1-traceability",
            "2-intent-risk-requirements",
            "3-validation-release",
            "4-causal-analysis",
        ),
        output=LoopAssessment,
        check=check_all_loop_activities,
        planned_output_tokens=1800,
    ),
    PassSpec(
        key="6-actions-learning",
        title="Actions and reusable learning",
        task=(
            "Propose 3 to 5 actions, applying the action-quality filter to every action. Each action is a proposal: the "
            "engine checks it afterwards against the earliest opportunity, the findings and the evidence, and an action it "
            "cannot ground is reported as unsupported. Aim each action at the earliest reasonable missed opportunity stated "
            "below, or at a later opportunity that is supported. Where a candidate intervention listed below fits, adapt it to "
            "this case and give its ID in intervention_id; do not copy it, and do not use one that does not fit. "
            "Every action states all of: WHAT changes (action), WHERE (destination), WHY (reason, tied to a finding and its "
            "evidence), WHO (owner_type, a kind of role), HOW it is carried out (how), and RECURRENCE (recurrence_protection). "
            "Set kind to CORRECTIVE_ACTION for a change to how work is done, and to INVESTIGATIVE_ACTION for establishing "
            "evidence that is missing. Propose a CORRECTIVE_ACTION only for a problem the evidence shows. Where no opportunity "
            "is supported, or an activity is UNKNOWN, propose an INVESTIGATIVE_ACTION that would establish what is missing, "
            "not a control. Do not prescribe a specific threshold, tool, headcount or rewrite that no evidence calls for. No "
            "generic recommendation. Then list what worked, the reusable learning, and the open questions."
        ),
        methodology=(
            ("evidence-and-actions", "Action generation"),
            ("evidence-and-actions", "Always identify what worked"),
        ),
        # Actions follow from the validated gaps; what was done after discovery is the
        # only raw evidence this pass needs.
        evidence=("remediation_changes", "production_evidence"),
        prior=("4-causal-analysis", "5-quality-loop"),
        output=ActionPlan,
        planned_output_tokens=2200,
    ),
    PassSpec(
        key="7-critical-review",
        title="Critical review",
        task=(
            "You are now the reviewer of the draft conclusions in the earlier pass "
            "results. Review the assessment; do not redo the investigation. You have the "
            "findings, the critical signals found in pass 1, the evidence excerpts those "
            "findings cite, an index of all other evidence by ID, and a list of "
            "contradiction candidates flagged by a deterministic pre-check further below — "
            "treat that list as a starting point, not as exhaustive. A finding whose cited "
            "evidence is not among the excerpts cannot be confirmed from here: say so "
            "instead of assuming it holds. "
            "Check specifically for: important pre-release evidence (including every "
            "critical signal) that the later passes omitted or did not act on; causal "
            "conclusions contradicted by an earlier pass; a requirements-vs-implementation "
            "contradiction (e.g. a finding that the requirement was clear sitting next to "
            "one that blames an incomplete or incorrect requirement for the same defect); "
            "a test-coverage-taxonomy contradiction (e.g. 'no relevant test existed' next "
            "to 'a test existed but was not selected' for the same gap); hindsight bias; "
            "unsupported certainty; and vague, unexecutable actions. For every "
            "contradiction you confirm, resolve it from the evidence and say which claim "
            "stands and why, or mark it UNRESOLVED so it becomes an open question instead "
            "of letting the report state both claims as facts. For every other problem, "
            "say what should be revised. Also list the conclusions that hold up. Review "
            "every test_relevance entry from the validation pass and challenge any "
            "conclusion that treats a test as able to detect the failure when what it tests "
            "differs materially from the failing production condition. For every critical "
            "signal, either list its ID in used_critical_signal_ids when the conclusions "
            "depend on it, or add it to dismissed_critical_signals with the reason it is "
            "not material."
        ),
        methodology=(
            ("skill", "Phase 7"),
            ("causal-model", "Root-cause quality check"),
            ("causal-model", "Earliest reasonable missed opportunity"),
            ("evidence-and-actions", "Action generation"),
        ),
        evidence_mode="referenced",
        prior=(
            "1-traceability",
            "2-intent-risk-requirements",
            "3-validation-release",
            "4-causal-analysis",
            "5-quality-loop",
            "6-actions-learning",
        ),
        output=CriticalReview,
        check=check_critical_review,
        planned_output_tokens=1200,
    ),
    PassSpec(
        key="8-final-report",
        title="Final synthesis",
        task=(
            "Write the narrative sections of the final assessment report, in Markdown, "
            "from the earlier pass results. The output contract at the end of this prompt "
            "names every section to write and their order; the engine adds the remaining "
            "sections of the report from the validated structured results. Apply every "
            "revision recommended by the critical review: where it challenged a conclusion, "
            "use the revised conclusion, not the draft one, and treat every resolved "
            "contradiction's standing claim as the fact to report. List the reviewed "
            "artifacts and the evidence limitations under Evidence Reviewed. Introduce no "
            "claim that is absent from the earlier pass results."
        ),
        # The report template is not shown: its full section list and its instruction to keep
        # every section contradicted this pass's narrower task (9a5). The output contract
        # (Orchestrator.report_contract) is generated from the template and the parser instead.
        methodology=(),
        # Passes 2 and 3 are consolidated in the Quality Loop mapping, so the synthesis
        # works from the validated results only. It is given no raw evidence.
        prior=(
            "1-traceability",
            "4-causal-analysis",
            "5-quality-loop",
            "6-actions-learning",
            "7-critical-review",
        ),
        planned_output_tokens=2500,
    ),
)


def validate_pass_definitions(methodology: Methodology) -> None:
    """Fail early if a pass refers to a methodology section that no longer exists."""
    for spec in PASSES:
        for key, section in spec.methodology:
            methodology.text(key, section)
