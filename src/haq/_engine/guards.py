"""Deterministic evidence-discipline guards.

Each guard runs right after the pass whose output it checks, so that every later pass,
and the final report, is built from the corrected structured result. A guard never
writes analysis: it assigns IDs, downgrades claims the evidence files do not support,
and derives verdicts from the model's own structured answers. Every change is returned
as a note for the run log.

What the guards can and cannot check:

- They can check that an identifier or a quoted passage really occurs in the artifact a
  claim cites. They cannot check that the passage means what the model says it means.
- A DIRECT traceability link needs a recorded reference: one artifact containing
  identifiers of both items, or a quote found verbatim in an artifact.
- A claim at one of the two strongest confidence levels needs at least one evidence
  reference that names a case artifact (or a critical-signal ID) and cites no identifier
  absent from that artifact.
- Every citation is checked by itself (imw). One that does not resolve to evidence
  collected for the assessment is removed from the finding and recorded. When other
  citations of the finding do check out, a strong level it held is lowered all the same,
  to the level a finding with no reference that checks out gets: which part of the claim
  the rejected citation was meant to support cannot be read from the answer, so the
  remaining citations are not taken to support all of it. When none checks out, the
  reference rule above lowers it, as before."""

from __future__ import annotations

import re
from collections.abc import Callable

from pydantic import BaseModel

from .evidence import EvidenceBundle
from .methodology import Methodology
from .passes import (
    ACTIVITY_STATUS,
    ActionPlan,
    CausalAssessment,
    CausalFinding,
    KeyClaim,
    LoopAssessment,
    MissedOpportunity,
    RequirementsAssessment,
    TraceabilityResult,
    TraceLink,
    ValidationAssessment,
    decision_answer,
)

DIRECT, INFERRED = "DIRECT", "INFERRED"
DETECTING = "DETECTING"
NOT_DETECTING = "RELATED BUT NOT DETECTING"
# A test known only from a remediation change: it cannot show a pre-release gap.
REMEDIATION_TEST = "ADDED OR REFERENCED BY THE FIX ONLY"
UNCERTAIN = "UNCERTAIN"
GAP_SUPPORTED, GAP_NOT_SUPPORTED = "SUPPORTED", "NOT SUPPORTED"
REGRESSION_ACTIVITY = "selectregression"
# The weakest activity status, as passes.py already describes it to the model.
ACTIVITY_UNKNOWN = "UNKNOWN / INSUFFICIENT EVIDENCE"
assert ACTIVITY_UNKNOWN in ACTIVITY_STATUS

# Identifiers of work items: issue/test/incident keys, PR numbers, versions.
_ITEM_ID = re.compile(r"[A-Z][A-Z0-9]*-\d+|#\d+|\b\d+\.\d+\.\d+\b")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
MIN_QUOTE_CHARS = 12


# Guard IDs. Each names one rule; a note that changed a finding carries the ID of the rule that did it.
G_EVIDENCE_REF = "G-EVIDENCE-REF"                  # a strong claim needs a reference that checks out
G_ABSENCE = "G-ABSENCE"                            # an absence cannot be read from evidence nobody collected
G_CAUSAL_LIMIT = "G-CAUSAL-LIMIT"                  # a fix is never the cause; an uncollected origin is never named
G_NO_DETECTING_TEST = "G-NO-DETECTING-TEST"        # "a relevant test existed" needs a test classified DETECTING
G_MISSED_OPPORTUNITY = "G-MISSED-OPPORTUNITY-GAP"  # a missed opportunity in regression selection needs a supported gap
G_REMEDIATION_TEST = "G-REMEDIATION-TEST"          # a test known only from the fix is not pre-release coverage
G_MATERIAL_DIFFERENCE = "G-MATERIAL-DIFFERENCE"    # "could detect" with recorded material differences is uncertain
G_UNASSESSED_RELEVANCE = "G-UNASSESSED-RELEVANCE"  # a stated lack of assessment cannot be a decided comparison
G_GAP_DERIVED = "G-GAP-DERIVED"                    # the regression-selection gap is derived, never asserted
G_CITATION = "G-CITATION-UNRESOLVED"               # each citation must resolve to collected evidence by itself
G_TRACE_SUPPORT = "G-TRACE-SUPPORT"                # a pass-1 link or signal holds only what its verified citations support (xkn)
G_DECISION_ANSWER = "G-DECISION-ANSWER"            # a decision claim's answer is YES, NO or UNKNOWN; anything else is unresolved (cu0)


class GuardNote(str):
    """A run-log note that also says, as data, which finding a guard changed and by which
    rule. It is a string like any other note; the fields are what attribution is read from,
    so that no report has to guess a guard from the wording of its note."""

    guard_id = finding_type = qualifier = subject = original = corrected = ""

    def __new__(cls, text: str, guard_id: str, finding_type: str, qualifier: str = "", subject: str = "",
                original: str = "", corrected: str = "") -> "GuardNote":
        note = super().__new__(cls, text)
        note.guard_id, note.finding_type, note.qualifier, note.subject = guard_id, finding_type, qualifier, subject
        note.original, note.corrected = original, corrected
        return note

    def record(self, pass_key: str) -> dict:
        # The note starts with the pass it belongs to; the reason is the rest.
        record = {"guard_id": self.guard_id, "after_pass": pass_key, "finding_type": self.finding_type,
                "qualifier": self.qualifier, "subject": self.subject, "original": self.original,
                "corrected": self.corrected, "reason": str(self).partition(": ")[2] or str(self)}
        if hasattr(self, "superseded_proposal"):
            record["superseded_proposal"] = self.superseded_proposal
            record["effective_interpretation"] = self.effective_interpretation
        return record


def _finding_of(obj: BaseModel, label: str) -> tuple[str, str]:
    """(finding type, qualifier) of the finding an object holds, named as its annotation is."""
    if isinstance(obj, CausalFinding):
        return "CAUSAL_LAYER", obj.layer
    if isinstance(obj, KeyClaim):
        return "DECISION_CLAIM", label
    if isinstance(obj, MissedOpportunity):
        return "EARLIEST_MISSED_OPPORTUNITY", ""
    return "LOOP_ACTIVITY_FINDING", label


def norm(text: str) -> str:
    return " ".join(text.upper().split())


def squash(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def _is_none(text: str) -> bool:
    """Whether a free-text field says there is nothing to report."""
    squashed = squash(text)
    return squashed in {"", "na", "no", "nil"} or squashed.startswith(("none", "nomaterial"))


def _material_constraint(original: str) -> str:
    return ("Detectability remains uncertain: the proposed detecting conclusion conflicts with the row's stated "
            "material differences." if original == "YES" else
            "Detectability remains uncertain: the proposed non-detecting conclusion states no material difference.")


def restore_test_row_constraints(value: BaseModel, audit: object, weakest: str) -> None:
    """Reconstruct a guard's runtime constraint, never a model-supplied directive.

    The saved receipt must uniquely match the current guarded row and the guard's
    condition is rechecked. No metadata text is executed or promoted to authority.
    Missing/legacy/mismatched audit leaves the saved result as-is.
    """
    if not isinstance(value, ValidationAssessment) or not isinstance(audit, list):
        return
    for row in value.test_relevance:
        if sum(other.test == row.test for other in value.test_relevance) != 1:
            continue
        notes = [n for n in audit if isinstance(n, dict) and n.get("after_pass") == "3-validation-release"
                 and n.get("guard_id") == G_MATERIAL_DIFFERENCE and n.get("subject") == row.test]
        if len(notes) != 1:
            continue
        note = notes[0]
        original = note.get("original")
        prior = note.get("superseded_proposal")
        if (original not in ("YES", "NO") or note.get("corrected") != UNCERTAIN
                or note.get("finding_type") != "TEST_COULD_DETECT_FAILURE"
                or not isinstance(prior, dict) or prior.get("status") != "SUPERSEDED_UNVERIFIED_PROPOSAL"
                or not isinstance(prior.get("reasoning"), str) or not isinstance(prior.get("confidence"), str)):
            continue
        if (norm(row.could_this_test_detect_the_failure) != UNCERTAIN or row.classification != UNCERTAIN
                or row.confidence != weakest or (original == "YES") == _is_none(row.material_differences)):
            continue
        constraint = _material_constraint(original)
        expected = {"reasoning": "Effective unresolved row constraints: " + constraint, "confidence": weakest}
        if note.get("effective_interpretation") != expected or (row.reasoning, row.confidence) != (expected["reasoning"], weakest):
            continue
        row.constrain_interpretation("could_this_test_detect_the_failure", constraint, weakest)


def item_ids(text: str) -> set[str]:
    return set(_ITEM_ID.findall(text))


def contains_id(text: str, identifier: str) -> bool:
    # A pull-request number is written directly after its repository name ("org/repo#12"),
    # so it may follow a letter. Any other identifier must start at a word boundary.
    before = "" if identifier.startswith("#") else r"(?<![A-Za-z0-9])"
    return re.search(rf"{before}{re.escape(identifier)}(?!\d)", text) is not None


def _flat(text: str) -> str:
    return " ".join(text.lower().split())


# ------------------------------------------------------------ evidence references


_RELATIONSHIP_REF = re.compile(r"relationship:(rel-\d+)")


def cited_artifacts(ref: str, bundle: EvidenceBundle) -> list:
    """The artifacts an evidence reference names: by the exact evidence ID or file name the collector recorded, as a whole
    token (the evidence registry, `EvidenceBundle.named`; xkn), or by a recorded relationship ID. Nothing is resolved by
    similarity or by building a file name from an identifier."""
    named = bundle.named(ref)
    for relationship_id in _RELATIONSHIP_REF.findall(ref):
        named += [a for a in bundle.artifacts()
                  if f"relationship:{relationship_id}" in a.content and a not in named]
    return named


def valid_refs(refs: list[str], bundle: EvidenceBundle, signal_ids: set[str]) -> list[str]:
    """References that name a case artifact (or a known critical-signal ID) and cite no
    identifier or date that is absent from the artifacts they name."""
    valid = []
    for ref in refs:
        named = cited_artifacts(ref, bundle)
        if not named:
            # A critical signal is cited through its provenance (xkn): `signal_ids` holds only the signals whose own source
            # resolves and holds what they say (verified_signal_ids). The signal object existing is not support.
            if any(re.search(rf"(?<![\w-]){re.escape(signal_id)}(?![\w-])", ref) for signal_id in signal_ids):
                valid.append(ref)
            continue
        # What the reference claims beyond naming the artifact itself.
        rest = ref
        for artifact in named:
            for token in (artifact.ref, artifact.name):
                rest = re.sub(re.escape(token), " ", rest, flags=re.I)
        cited = item_ids(_RELATIONSHIP_REF.sub(" ", rest)) | set(_DATE.findall(rest))
        # Compact forms are checked too: an identifier may sit in text the model saw in full.
        if all(any(contains_id(a.content, c) or any(contains_id(f, c) for f in a.compact_forms) for a in named)
               for c in cited):
            valid.append(ref)
    return valid


# What a model writes in a citation list when it has nothing to cite: not a citation.
_NO_CITATION = {"", "none", "n/a", "na", "unknown", "-"}


def reject_unresolved_citations(
    items: list[tuple[BaseModel, str, str | None, str]],
    strong: set[str],
    weak: str,
    bundle: EvidenceBundle,
    signal_ids: set[str],
    pass_key: str,
) -> tuple[list[str], set[int]]:
    """items: (object, label, confidence attribute or None, evidence attribute). Removes every
    citation that does not resolve, by itself, to evidence collected for this assessment
    (valid_refs of that one citation), and lowers a strong level the object held to `weak`.
    The model's own answer is kept unchanged in the pass's raw output; each removal is a note
    whose original and corrected values are the citation lists. Returns the notes and the
    ids of the objects that lost a citation."""
    notes, touched = [], set()
    for obj, label, confidence_attr, evidence_attr in items:
        refs = list(getattr(obj, evidence_attr))
        rejected = [r for r in refs if r.strip().lower() not in _NO_CITATION and not valid_refs([r], bundle, signal_ids)]
        if not rejected:
            continue
        touched.add(id(obj))
        kept = [r for r in refs if r not in rejected]
        setattr(obj, evidence_attr, kept)
        finding_type, qualifier = _finding_of(obj, label)
        subject = ""
        if hasattr(obj, "could_this_test_detect_the_failure"):
            finding_type, qualifier, subject = "TEST_COULD_DETECT_FAILURE", "", label
        listed = ", ".join(f"'{r}'" for r in rejected)
        notes.append(GuardNote(
            f"{pass_key}: '{label}' cited {listed}, which names no evidence collected for this assessment "
            f"(or an identifier the evidence it names does not hold); removed from its citations. "
            f"Remaining: {', '.join(kept) or 'none'}.",
            G_CITATION, finding_type, qualifier, subject=subject, original="; ".join(refs), corrected="; ".join(kept),
        ))
        current = getattr(obj, confidence_attr) if confidence_attr else ""
        # With no citation left that checks out, G-EVIDENCE-REF lowers the level, as it always has.
        if confidence_attr and norm(current) in strong and valid_refs(kept, bundle, signal_ids):
            setattr(obj, confidence_attr, weak)
            notes.append(GuardNote(
                f"{pass_key}: '{label}' was {current}, but its citation {listed} does not resolve to collected "
                "evidence, and which part of the claim it supported cannot be established; the remaining citations "
                f"are not taken to support the whole claim. Lowered to {weak}.",
                G_CITATION, finding_type, qualifier, subject=subject, original=current, corrected=weak,
            ))
    return notes, touched


def _downgrade_unsupported(
    items: list[tuple[BaseModel, str, str, str]],
    strong: set[str],
    weak: str,
    bundle: EvidenceBundle,
    signal_ids: set[str],
    pass_key: str,
) -> list[str]:
    """items: (object, label, confidence attribute, evidence attribute)."""
    notes = []
    for obj, label, confidence_attr, evidence_attr in items:
        current = getattr(obj, confidence_attr)
        if norm(current) not in strong:
            continue
        if valid_refs(getattr(obj, evidence_attr), bundle, signal_ids):
            continue
        setattr(obj, confidence_attr, weak)
        notes.append(GuardNote(
            f"{pass_key}: '{label}' was {current} without any evidence reference that "
            f"checks out against the case artifacts; downgraded to {weak}.",
            G_EVIDENCE_REF, *_finding_of(obj, label), original=current, corrected=weak,
        ))
    return notes


# ------------------------------------------------------------ absence claims

# A finding that says something did not exist or did not happen.
_ABSENCE = re.compile(r"\b(?:no|none|not|never|without|lack\w*|absen\w+|missing)\b|n't\b", re.I)
_RELEASE_BASIS = ("ci_evidence", "release_evidence", "originating_work", "implementation_changes")
_INTENT_BASIS = ("originating_work", "requirements", "documentation")
# Which evidence would have to be collected before an absence can be established, by
# causal layer and by Quality Loop activity (squashed names; the first match applies).
_ABSENCE_BASIS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("productiondetection", ("production_evidence",)),
    ("monitorproduction", ("production_evidence",)),
    ("releasedecision", _RELEASE_BASIS),
    ("releasewithinformedconfidence", _RELEASE_BASIS),
    ("detection", ("test_evidence", "ci_evidence")),
    ("automatewhatisrepeatable", ("test_evidence",)),
    (REGRESSION_ACTIVITY, ("test_evidence",)),
    ("analyzechangeimpact", ("implementation_changes",)),
    ("prevention", _INTENT_BASIS),
    ("clarifyintent", _INTENT_BASIS),
    ("identifyrisk", _INTENT_BASIS),
    ("definetestexpectations", (*_INTENT_BASIS, "test_evidence")),
)
_CLAIM_BASIS = {
    "relevant_test_existed": ("test_evidence",),
    "relevant_test_was_executed": ("test_evidence", "ci_evidence", "release_evidence"),
    "signal_failed_before_release": _RELEASE_BASIS,
    "warning_evidence_available_to_release_decision": _RELEASE_BASIS,
    "release_signal_acted_upon": _RELEASE_BASIS,
}


def _collected(bundle: EvidenceBundle, categories: tuple[str, ...]) -> bool:
    """Whether any of the categories holds evidence an absence could be read from. A test
    found only by search shows that similar wording exists, not what the test coverage is."""
    return any(
        not (category == "test_evidence" and a.relation == INFERRED)
        for category in categories for a in getattr(bundle, category)
    )


def _not_collected(bundle: EvidenceBundle, categories: tuple[str, ...]) -> str:
    names = [
        c.replace("_", " ") + (" (other than tests found only by search)" if c == "test_evidence" and bundle.test_evidence else "")
        for c in categories
    ]
    return f"no {', '.join(names)} was collected"


def downgrade_absence_claims(
    items: list[tuple[BaseModel, str, str, str]], strong: set[str], weak: str, bundle: EvidenceBundle, key: str,
) -> list[str]:
    """items: (object, name, confidence attribute, finding attribute). That evidence was
    not collected does not show that what it would record does not exist."""
    notes = []
    for obj, name, confidence_attr, finding_attr in items:
        basis = next((cats for token, cats in _ABSENCE_BASIS if token in squash(name)), None)
        current = getattr(obj, confidence_attr)
        if basis is None or norm(current) not in strong or _collected(bundle, basis):
            continue
        if not _ABSENCE.search(getattr(obj, finding_attr)):
            continue
        setattr(obj, confidence_attr, weak)
        notes.append(GuardNote(
            f"{key}: '{name}' was {current} for a finding that something did not exist or did not "
            f"happen, but {_not_collected(bundle, basis)}, so the absence cannot be established; set to {weak}.",
            G_ABSENCE, *_finding_of(obj, name), original=current, corrected=weak,
        ))
    return notes


def downgrade_absence_answers(causal: CausalAssessment, weakest: str, bundle: EvidenceBundle, key: str) -> list[str]:
    """A decision claim answered NO is an absence claim."""
    notes = []
    claims = causal.decision_claims
    for name, basis in _CLAIM_BASIS.items() if claims is not None else ():
        claim = getattr(claims, name)
        if norm(claim.answer) != "NO" or _collected(bundle, basis):
            continue
        claim.answer, claim.confidence = "UNKNOWN", weakest
        notes.append(GuardNote(
            f"{key}: '{name}' was answered NO, but {_not_collected(bundle, basis)}, so the absence "
            "cannot be established; answer set to UNKNOWN.",
            G_ABSENCE, "DECISION_CLAIM", name, original="NO", corrected="UNKNOWN",
        ))
    return notes


# ------------------------------------------------------------ incomplete causal chains

NO_INTRODUCING_CHANGE = "The available evidence does not identify the change that introduced the defect."
# Two findings that are never the same one. How the defect works (the observed defect
# mechanism, `defect_mechanism`) can be read from the production issue. Which change
# introduced it (the 'Defect introduction' layer) cannot: only an implementation change
# that is tied to the failure and is not a fix shows that.
OBSERVED_MECHANISM = "Observed defect mechanism"

# A sentence that attributes the introduction of the defect to something.
# "the change that introduced the defect" names nothing, so a relative clause alone is not one.
_ATTRIBUTES_INTRODUCTION = re.compile(
    r"\b(?:was|were|been|is|got)\s+(?:first\s+|originally\s+|likely\s+|probably\s+)?introduced\s+"
    r"(?:by|in|into|when|with|during|through|via|after|as\s+part\s+of|on|at|due\s+to|because)\b|"
    r"(?<!\bthat\s)(?<!\bwhich\s)(?<!\bwhat\s)\bintroduced\s+(?:the|this|a)\s+(?:defect|bug|regression|failure|problem|issue)\b"
    r"(?!\s+(?:tests?|suite|check|case|run|fix)\b)|"
    r"\b(?:is|was)\s+the\s+(?:change|commit|pull\s+request|pr|story|release)\s+(?:that|which)\s+introduced\b|"
    r"\b(?:defect|bug|regression|failure)\s+(?:originated|originates)\s+(?:in|from|with|when)\b|"
    r"\b(?:originating|introducing)\s+(?:change|commit|pull\s+request|pr|story|release)\s+(?:is|was)\s+"
    r"(?!not\b|un\w+|never\b|missing\b|absent\b)", re.I)
# Read in the few words before it: a negation, a question or a recommendation attributes nothing.
_NOT_ATTRIBUTED = re.compile(
    r"\b(?:not|never|no|without|whether|if|when|where|which|what|who|how|should|must|would|could|may|might|cannot|"
    r"unknown|unclear|to be|needs? to|recommend\w*|ensure\w*|determine\w*|identif\w*|establish\w*|find out)\b|n't\b", re.I)
_ATTRIBUTION_WINDOW = 48


def attributes_introduction(sentence: str) -> bool:
    """Whether a sentence says which change, or when, introduced the defect. Used only to
    keep prose consistent with a 'Defect introduction' that is already UNKNOWN: what that
    finding is, is decided from the evidence and never from wording."""
    if NO_INTRODUCING_CHANGE in sentence:
        return False
    return any(not _NOT_ATTRIBUTED.search(sentence[max(0, m.start() - _ATTRIBUTION_WINDOW):m.start()])
               for m in _ATTRIBUTES_INTRODUCTION.finditer(sentence))


def introduction_is_unknown(causal: CausalAssessment | None, weakest: str) -> bool:
    """The 'Defect introduction' layer of an assessment is at the weakest confidence level."""
    if causal is None:
        return False
    layers = [layer for layer in causal.layers if "defectintroduction" in squash(layer.layer)]
    return bool(layers) and all(norm(layer.confidence) == norm(weakest) for layer in layers)
_PR_NUMBER = re.compile(r"#(\d+)")


def remediation_names(bundle: EvidenceBundle) -> list[str]:
    return [a.name for a in bundle.remediation_changes]


def remediation_tokens(bundle: EvidenceBundle) -> set[str]:
    """Strings that identify a remediation change in prose: artifact names and PR numbers."""
    tokens = set(remediation_names(bundle))
    for artifact in bundle.remediation_changes:
        tokens.update(f"#{n}" for n in _PR_NUMBER.findall(artifact.source_path))
    return tokens


def introducing_change_unknown(bundle: EvidenceBundle) -> bool:
    """No originating work and no change that could have introduced the defect."""
    return not bundle.originating_work and not bundle.implementation_changes


def evidence_constraints(bundle: EvidenceBundle) -> str | None:
    """Facts about the evidence itself that every pass must respect."""
    lines = []
    for name in remediation_names(bundle):
        lines.append(
            f"- [{name}] is a REMEDIATION change: it was made after the defect was reported, "
            "to fix it. Use it only as post-release learning (what was fixed, what tests "
            "were added, what was believed to be wrong). Never present it as the change that "
            "introduced the defect, and never use it to judge what was knowable before release."
        )
    for artifact in bundle.implementation_changes:
        if artifact.relation == INFERRED:
            lines.append(
                f"- [{artifact.ref}] is a CANDIDATE change, collected by inference (a search hit, or "
                "because it changed a file the issue names). No artifact ties it to the defect. "
                "Name it as the change that introduced the defect only when its own content shows "
                "the mechanism the evidence describes; otherwise report it as a candidate."
            )
    for artifact in bundle.test_evidence:
        if artifact.role == "REMEDIATION":
            lines.append(
                f"- [{artifact.ref}] is a test known only from a remediation change. It is not "
                "evidence of coverage that existed before release: do not treat it as a test "
                "that was available and left unselected or unexecuted, and do not base a "
                "regression-selection or release finding on it. It may be reported as what was "
                "added after discovery."
            )
    if introducing_change_unknown(bundle):
        lines.append(
            f"- {NO_INTRODUCING_CHANGE} No originating work and no originating implementation "
            "change was collected. Do not name or imply an introducing change, story or "
            "release unless an artifact states it, and do not construct a causal chain to "
            "fill the gap."
        )
        lines.append(
            "- HOW the defect works is a separate question from WHICH CHANGE introduced it, "
            "and it is not unknown merely because the introducing change is. If an artifact "
            "describes the technical mechanism or root cause (for example an analysis "
            "recorded in a comment on the production issue), report that mechanism in "
            "defect_mechanism, cite the artifact, and say that the analysis was made "
            "after the defect was reported. Do not report it under 'Defect introduction': "
            "that layer stays UNKNOWN, because how a defect works does not show which change "
            "introduced it. If an artifact records a classification or a "
            "release attribution (a field or a label on the issue), report it with its "
            "source as what was recorded, not as something you established."
        )
        lines.append(
            "- The 'Prevention gap' layer is UNKNOWN unless an artifact other than a "
            "remediation change supports a finding."
        )
        lines.append(
            "- That gap does not make the other layers unknown. Assess test and detection "
            "coverage, regression selection, execution and release evidence, production "
            "detection, remediation and learning independently, each from the evidence "
            "that exists for it."
        )
    if not lines:
        return None
    return "# Constraints from the evidence\n\n" + "\n".join(lines)


def _independent_refs(refs: list[str], bundle: EvidenceBundle, signal_ids: set[str]) -> list[str]:
    """Valid references that do not rest on a remediation change."""
    remediation = {a.name for a in bundle.remediation_changes}
    return [
        r for r in valid_refs(refs, bundle, signal_ids)
        if not any(a.name in remediation for a in cited_artifacts(r, bundle))
    ]


def _loose(text: str) -> str:
    """For comparing a copied passage with its source: formatting marks and spacing are
    ignored, every letter, digit and path character is kept."""
    return " ".join(re.sub(r"[^a-z0-9./:_-]+", " ", text.lower()).split())


def mechanism_claim(causal: CausalAssessment, bundle: EvidenceBundle) -> str:
    """The confidence the model gave its account of how the defect works when it wrote that
    account under 'Defect introduction': read only when that finding and the recorded
    mechanism cite the same artifact, and before the layer itself is corrected."""
    mechanism = causal.defect_mechanism
    if mechanism is None or norm(mechanism.described_in_evidence) != "YES":
        return ""
    sources = {a.name for r in mechanism.evidence for a in cited_artifacts(r, bundle)}
    for layer in causal.layers:
        if "defectintroduction" in squash(layer.layer) and sources & {a.name for r in layer.evidence for a in cited_artifacts(r, bundle)}:
            return layer.confidence
    return ""


def verify_mechanism(causal: CausalAssessment, bundle: EvidenceBundle, signal_ids: set[str], key: str,
                     levels: list[str] | None = None, claimed: str = "") -> list[str]:
    """A recorded mechanism must come from an artifact other than a fix, and its
    specifics must be in that artifact as written.

    Its confidence rests on a supporting evidence span, never on the model's word:

      strongest level   a passage of a cited artifact that is not a fix was found in that
                        artifact, and it names what the stated mechanism names. The
                        mechanism may be a paraphrase: its own wording is not compared.
      second level      the mechanism cites such an artifact, and no such span was verified.
      third level       nothing was verified and the model stated no confidence.

    The model's own confidence (`confidence`, or `claimed` when it wrote the mechanism
    under 'Defect introduction') can lower the result and never raise it. The span and
    the artifacts it was found in are stored with the mechanism. It never says which
    change introduced the defect."""
    mechanism = causal.defect_mechanism
    if mechanism is None or norm(mechanism.described_in_evidence) != "YES":
        if mechanism is not None:
            mechanism.confidence = ""
        return []
    notes = []
    mechanism.evidence = _independent_refs(mechanism.evidence, bundle, signal_ids)
    remediation = {a.name for a in bundle.remediation_changes}
    sources = [a for r in mechanism.evidence for a in cited_artifacts(r, bundle) if a.name not in remediation]
    if not sources or not mechanism.mechanism.strip():
        causal.defect_mechanism = type(mechanism)(described_in_evidence="NO")
        return [f"{key}: the recorded defect mechanism was removed: it cites no artifact other than a remediation change."]
    text = " ".join(_loose(a.content) for a in sources)
    quote = _loose(mechanism.evidence_quote)
    holding = [a for a in sources if quote in _loose(a.content)] if len(quote) >= MIN_QUOTE_CHARS else []
    mechanism.quote_verified = bool(holding)
    direct = mechanism.quote_verified and supports(mechanism.evidence_quote, f"{mechanism.mechanism} {mechanism.location}")
    mechanism.supporting_span = _as_written(mechanism.evidence_quote, holding[0].content) if direct else ""
    mechanism.supporting_span_sources = list(dict.fromkeys(a.ref for a in holding)) if direct else []
    if levels:
        rank = {norm(level): index for index, level in enumerate(levels)}
        stated = next((v for v in (mechanism.confidence, claimed) if norm(v) in rank), "")
        ceiling = 0 if direct else 1
        index = max(rank[norm(stated)], ceiling) if stated else (0 if direct else 2)
        mechanism.confidence = levels[min(index, len(levels) - 1)]
        if stated and rank[norm(stated)] < ceiling:
            notes.append(
                f"{key}: the observed defect mechanism was {stated}; it is {mechanism.confidence} because "
                + ("the passage quoted for it does not name what the mechanism names, so it is not a direct supporting span."
                   if mechanism.quote_verified else "no supporting passage was found in the cited artifact."))
    if mechanism.evidence_quote.strip() and not mechanism.quote_verified:
        notes.append(f"{key}: the passage quoted for the defect mechanism was not found in the cited artifact; it is not shown as a quotation.")
        mechanism.evidence_quote = ""
    for name, label in (("location", "location"), ("recorded_fix", "recorded fix")):
        value = getattr(mechanism, name)
        # Every specific term (a file, a line, a function name) has to be in the source.
        missing = [t for t in _SPECIFIC.findall(value) if _loose(t) not in text]
        if missing:
            notes.append(
                f"{key}: the {label} of the defect mechanism names {', '.join(missing[:4])}, "
                "which the cited artifact does not contain; it was removed."
            )
            setattr(mechanism, name, "")
    return notes


# Words that say nothing about what a mechanism is about.
_GENERIC = frozenset("""
    that this with when from which have does into then than were will because there their where what while been being
    after before should would could also only very more most some such each other about cause causes caused causing root
    defect defects issue issues problem problems failure failures fails failed error errors wrong incorrect behavior
    behaviour expected actual result results happens happen""".split())


def _terms(text: str) -> tuple[set[str], set[str]]:
    """(the specific identifiers a text names, the things it names). Words are compared on
    their first six letters, so that 'closes' and 'closed' are one thing."""
    specific = {_loose(t) for t in _SPECIFIC.findall(text)}
    words = {w[:6] for w in re.findall(r"[a-z][a-z0-9]{3,}", text.lower()) if w not in _GENERIC}
    return specific, words


def supports(span: str, statement: str) -> bool:
    """Whether a passage of evidence is about the same things as a statement made from it:
    it names a file, line or identifier the statement names, or at least two of the things
    the statement names. The statement's wording is not compared, so a paraphrase is
    supported by the passage it paraphrases, and an unrelated passage supports nothing."""
    span_specific, span_words = _terms(span)
    specific, words = _terms(statement)
    return bool(span_specific & specific) or len(span_words & words) >= 2


def _as_written(quote: str, content: str) -> str:
    """The passage as the artifact writes it. The model's copy is used only to find it."""
    tokens = _loose(quote).split()
    found = re.search(r"[^A-Za-z0-9./:_-]+".join(re.escape(t) for t in tokens), content, re.I) if tokens else None
    return " ".join((found.group(0) if found else quote).split())


# File names, paths with line numbers, and code identifiers.
_SPECIFIC = re.compile(r"[\w./-]+\.[A-Za-z]{1,5}(?::\d+)?|\b[a-z]+(?:[A-Z][a-z0-9]+)+\b|\b\w+_\w+\b")


def enforce_causal_limits(causal: CausalAssessment, bundle: EvidenceBundle, weakest: str,
                          signal_ids: set[str], key: str) -> list[str]:
    """A fix is never the cause, and an introducing change nobody collected is never named.

    How the defect works is a different finding (`defect_mechanism`) and is left as it
    is. It never carries 'Defect introduction': with no originating work and no
    implementation change collected, that layer is UNKNOWN whatever its finding cites."""
    notes = []
    unknown = introducing_change_unknown(bundle)
    has_remediation = bool(bundle.remediation_changes)
    for layer in causal.layers:
        name = squash(layer.layer)
        if "defectintroduction" in name and unknown:
            if norm(layer.confidence) != norm(weakest):
                said = " ".join(layer.finding.split())
                notes.append(GuardNote(
                    f"{key}: 'Defect introduction' was replaced with UNKNOWN: the evidence holds no originating "
                    "work and no change that could have introduced the defect. The production issue, a "
                    "description of how the defect works and a remediation change do not show which change "
                    f"introduced it. The model's finding was: \"{said[:240]}\"",
                    G_CAUSAL_LIMIT, "CAUSAL_LAYER", layer.layer, original=layer.confidence, corrected=weakest,
                ))
            elif layer.finding != NO_INTRODUCING_CHANGE or layer.evidence:
                notes.append(
                    f"{key}: 'Defect introduction' wording/evidence normalized; confidence remains {weakest}. "
                    "No originating work or introducing change was collected. "
                    f"The model's finding was: \"{' '.join(layer.finding.split())[:240]}\""
                )
            layer.finding, layer.confidence, layer.evidence = NO_INTRODUCING_CHANGE, weakest, []
        elif ("defectintroduction" in name or "prevention" in name) and has_remediation:
            if norm(layer.confidence) != norm(weakest) and not _independent_refs(layer.evidence, bundle, signal_ids):
                was, layer.confidence = layer.confidence, weakest
                notes.append(GuardNote(
                    f"{key}: '{layer.layer}' rested only on remediation changes, which cannot "
                    f"show how the defect was introduced or what was knowable earlier; set to {weakest}.",
                    G_CAUSAL_LIMIT, "CAUSAL_LAYER", layer.layer, original=was, corrected=weakest,
                ))
                if "defectintroduction" in name:   # a fix says what was changed afterwards, never what introduced the defect
                    layer.finding, layer.evidence = f"{NO_INTRODUCING_CHANGE} The finding cited only the fix.", []
    claims = causal.decision_claims
    if claims is not None and has_remediation:
        claim = claims.implementation_contradicted_requirement
        if norm(claim.answer) != "UNKNOWN" and not _independent_refs(claim.evidence_refs, bundle, signal_ids):
            was = norm(claim.answer)
            claim.answer, claim.confidence = "UNKNOWN", weakest
            notes.append(GuardNote(
                f"{key}: the claim about the implementation contradicting a requirement rested "
                "only on remediation changes; answer set to UNKNOWN.",
                G_CAUSAL_LIMIT, "DECISION_CLAIM", "implementation_contradicted_requirement", original=was, corrected="UNKNOWN",
            ))
    if claims is not None:
        claim = claims.implementation_contradicted_requirement
        no_requirement = not bundle.artifacts(("originating_work", "requirements", "documentation"))
        if norm(claim.answer) != "UNKNOWN" and (no_requirement or norm(claims.requirement_was_explicit.answer) == "UNKNOWN"):
            was = norm(claim.answer)
            claim.answer, claim.confidence = "UNKNOWN", weakest
            notes.append(GuardNote(
                f"{key}: whether the implementation contradicted a requirement was answered although "
                + ("the evidence holds no requirement" if no_requirement else "it is unknown whether the requirement was explicit")
                + "; answer set to UNKNOWN.",
                G_CAUSAL_LIMIT, "DECISION_CLAIM", "implementation_contradicted_requirement", original=was, corrected="UNKNOWN",
            ))
    return notes


def verify_attributions(causal: CausalAssessment, bundle: EvidenceBundle, key: str) -> list[str]:
    """A recorded classification or release attribution must be on the production issue
    as written."""
    if not causal.recorded_attributions:
        return []
    text = " ".join(_loose(a.content) for a in bundle.production_issue)
    kept, notes = [], []
    for item in causal.recorded_attributions:
        value = _loose(item.value)
        if value and value in text:
            kept.append(item)
        else:
            notes.append(f"{key}: the recorded attribution '{item.value}' is not on the production issue as written; it was removed.")
    causal.recorded_attributions = kept
    return notes


# ------------------------------------------------------------ pass 1


def assign_signal_ids(trace: TraceabilityResult) -> None:
    for index, signal in enumerate(trace.critical_signals, start=1):
        signal.id = f"signal-{index:03d}"


# Identifiers of the "kind:number" form the collectors write ("run:55", "deployment:7001", "ci-run:90073").
_KIND_NUMBER = re.compile(r"(?<![\w:-])[a-z][a-z-]*:\d+(?![\w]|\.\d)", re.I)
# A version, also when written with a "v" ("v3.5.0", "release:v3.5.0").
_VERSION = re.compile(r"(?<![\w.])v?(\d+\.\d+\.\d+)(?![\w.]|\.\d)", re.I)


def identifiers(text: str) -> set[str]:
    """The identifiers a pass-1 item or statement names: work-item keys, PR numbers, versions and kind:number IDs."""
    return item_ids(text) | {m.group(0) for m in _KIND_NUMBER.finditer(text)} | {m.group(1) for m in _VERSION.finditer(text.replace(":", " "))}


def _written(text: str, identifier: str) -> bool:
    """`identifier` in `text`; a version also as "v" and the version, the way release records write it."""
    return contains_id(text, identifier) or (bool(re.fullmatch(r"\d+\.\d+\.\d+", identifier)) and contains_id(text.lower(), f"v{identifier}"))


def _holds(artifact, identifier: str) -> bool:
    return _written(artifact.content, identifier) or any(_written(f, identifier) for f in artifact.compact_forms)


def _is_citation(ref: str) -> bool:
    return bool(ref.strip()) and ref.strip().lower() not in _NO_CITATION


def signal_support(signal, bundle: EvidenceBundle) -> tuple[list, list[str]]:
    """(the collected artifacts a critical signal's source names, the identifiers its description names that none of them
    holds). The provenance of a signal (xkn): it is verified only when its source resolves exactly and holds what the
    signal says it does."""
    sources = cited_artifacts(signal.source_artifact, bundle) if _is_citation(signal.source_artifact) else []
    missing = sorted(i for i in identifiers(signal.description) if not any(_holds(a, i) for a in sources))
    return sources, missing


def verified_signal_ids(trace: TraceabilityResult | None, bundle: EvidenceBundle) -> set[str]:
    """The critical signals a later finding may cite: those whose provenance holds, recomputed from the evidence (a stored
    trace written before xkn has no flag to read). A signal whose source does not resolve supports nothing downstream."""
    if trace is None:
        return set()
    out = set()
    for signal in trace.critical_signals:
        sources, missing = signal_support(signal, bundle)
        if signal.id and sources and not missing:
            out.add(signal.id)
    return out


def validate_trace_citations(trace: TraceabilityResult, bundle: EvidenceBundle, levels: list[str]) -> list[str]:
    """Every pass-1 citation resolves exactly to collected evidence, or it is not evidence (xkn). An unresolved citation is
    taken out of its field, kept with the field it was in under `unresolved_citations`, and noted; nothing is mapped to a
    similar name. A critical signal is then verified from what remains (signal_support); one that is not supports nothing
    and drops to the weakest level. Links are reassessed by validate_links."""
    notes, weakest = [], levels[-1]

    def take(obj, field: str, label: str, finding_type: str) -> None:
        ref = getattr(obj, field)
        if not _is_citation(ref) or cited_artifacts(ref, bundle):
            return
        obj.unresolved_citations = [*obj.unresolved_citations, f"{field}: {ref}"]
        setattr(obj, field, "")
        notes.append(GuardNote(
            f"1-traceability: {label} cited '{ref}' as its {field}, which names no evidence collected for this assessment "
            "(no artifact has that evidence ID or file name); removed as evidence and kept as an unresolved citation.",
            G_CITATION, finding_type, subject=label, original=ref, corrected=""))

    for link in trace.links:
        for field in ("source_artifact", "target_artifact"):
            take(link, field, f"link '{link.from_item} → {link.to_item}'", "TRACE_LINK")
    for event in trace.timeline:
        take(event, "source", f"timeline event '{brief_text(event.event)}'", "TIMELINE_EVENT")
    for signal in trace.critical_signals:
        take(signal, "source_artifact", f"critical signal {signal.id}", "CRITICAL_SIGNAL")
        sources, missing = signal_support(signal, bundle)
        signal.verified = bool(sources) and not missing
        if signal.verified or norm(signal.confidence) == norm(weakest):
            continue
        why = ("its source is not in the collected evidence" if not sources else
               f"its source {sources[0].ref} does not hold {', '.join(missing)}, which it says")
        notes.append(GuardNote(
            f"1-traceability: critical signal {signal.id} was {signal.confidence}, but {why}; it supports nothing and is "
            f"held at {weakest}. Later findings cannot cite it as evidence.",
            G_TRACE_SUPPORT, "CRITICAL_SIGNAL", subject=signal.id, original=signal.confidence, corrected=weakest))
        signal.confidence = weakest
    return notes


def brief_text(text: str, limit: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _recorded_tie(link: TraceLink, bundle: EvidenceBundle) -> str:
    """How a collected relationship record ties the two items of a link, or "" (the items are matched by an identifier
    both name, or exactly as written)."""
    def same(item: str, endpoint: str) -> bool:
        ids = identifiers(item)
        return item.strip().lower() == endpoint.strip().lower() or bool(ids and ids & identifiers(endpoint))
    for source, target, said in bundle.recorded_ties():
        if (same(link.from_item, source) and same(link.to_item, target)) or (same(link.from_item, target) and same(link.to_item, source)):
            return said
    return ""


def mentions(text: str, item: str) -> bool:
    """Whether `text` names a pass-1 item: by an identifier the item names, or by the item as written (a commit SHA, a
    file path, "ci / unit"). Case aside; nothing is matched by similarity."""
    if any(_written(text, i) for i in identifiers(item)):
        return True
    written = " ".join(item.split()).lower()
    return len(written) >= 2 and re.search(rf"(?<![\w-]){re.escape(written)}(?![\w-])", " ".join(text.split()).lower()) is not None


def link_support(link: TraceLink, bundle: EvidenceBundle) -> tuple[str, str]:
    """(what records the relationship, if anything: DIRECT support; what supports it at all: any support), from verified
    evidence only. DIRECT needs a record of the relationship itself: a collected relationship record that ties the two
    items; or a cited artifact that is one item's own (its identity or title names it) and names the other; or a quoted
    passage, found in a cited artifact, that names both items, or names the other item in one item's own artifact. Two identifiers written together in some artifact the link does
    not cite record nothing (xkn). A link is supported at all by a recorded tie or a cited artifact that names either
    item; with neither it is unresolved."""
    cited = list({id(a): a for ref in (link.source_artifact, link.target_artifact) if _is_citation(ref)
                  for a in cited_artifacts(ref, bundle)}.values())
    tie = _recorded_tie(link, bundle)
    if tie:
        return tie, tie

    def own(artifact, item: str) -> bool:
        title = next((line for line in artifact.content.splitlines() if line.strip()), "")
        return mentions(f"{artifact.evidence_id} {artifact.name} {title}", item)

    def holds(artifact, item: str) -> bool:
        return mentions(artifact.content, item) or any(mentions(f, item) for f in artifact.compact_forms)

    for artifact in cited:
        for mine, other in ((link.from_item, link.to_item), (link.to_item, link.from_item)):
            if own(artifact, mine) and holds(artifact, other):
                return f"{artifact.ref} records {other}", artifact.ref
    # A quoted passage records the relationship when it is in a cited artifact and names both items, or names the other
    # item and is in one item's own artifact. A passage that names one item only records nothing about the other.
    quote, said = _flat(link.evidence_quote), link.evidence_quote
    if len(quote) >= MIN_QUOTE_CHARS:
        for artifact in cited:
            if quote not in _flat(artifact.content):
                continue
            if (mentions(said, link.from_item) and mentions(said, link.to_item)) or (
                    own(artifact, link.from_item) and mentions(said, link.to_item)) or (own(artifact, link.to_item) and mentions(said, link.from_item)):
                return f"the quoted passage is in {artifact.ref}", artifact.ref
    named = [a for a in cited if holds(a, link.from_item) or holds(a, link.to_item)]
    return "", ", ".join(a.ref for a in named)


def validate_links(trace: TraceabilityResult, bundle: EvidenceBundle, levels: list[str]) -> list[str]:
    """Each link is reassessed from the verified evidence that remains after validate_trace_citations (link_support). A
    DIRECT link without a record of the relationship becomes INFERRED; an inferred link is never at the strongest level;
    a link that no verified evidence supports is unresolved, at the weakest level. The relationship type is the model's
    reading either way: a record of a reference does not establish what the reference means."""
    notes = []
    strongest, next_level, weakest = levels[0], levels[1], levels[-1]
    for link in trace.links:
        label = f"{link.from_item} → {link.to_item}"
        direct, support = link_support(link, bundle)
        link.verified_support = direct or support
        if norm(link.direct_or_inferred) == DIRECT and not direct:
            link.direct_or_inferred = INFERRED
            notes.append(GuardNote(
                f"1-traceability: link '{label}' was claimed as DIRECT but nothing it cites records it (no collected "
                "relationship record ties the two items, no cited artifact of one item names the other, and no quoted "
                "passage was found in a cited artifact); relabelled INFERRED.",
                G_TRACE_SUPPORT, "TRACE_LINK", subject=label, original=DIRECT, corrected=INFERRED))
        elif norm(link.direct_or_inferred) != DIRECT:
            link.direct_or_inferred = INFERRED
        if not link.verified_support and norm(link.confidence) != norm(weakest):
            notes.append(GuardNote(
                f"1-traceability: link '{label}' was {link.confidence}, but no evidence it cites resolves and names either "
                f"item, and no collected relationship record ties them; unresolved, held at {weakest}.",
                G_TRACE_SUPPORT, "TRACE_LINK", subject=label, original=link.confidence, corrected=weakest))
            link.confidence = weakest
        elif link.direct_or_inferred == INFERRED and norm(link.confidence) == norm(strongest):
            link.confidence = next_level
            notes.append(
                f"1-traceability: inferred link '{label}' cannot be {strongest}; "
                f"downgraded to {next_level}."
            )
    return notes


def inferred_links(trace: TraceabilityResult) -> list[TraceLink]:
    return [link for link in trace.links if link.direct_or_inferred == INFERRED]


# ------------------------------------------------------------ pass 3


def derive_selection_gap(validation: ValidationAssessment, tied: Callable[[str], bool] | None = None) -> str:
    """Whether a regression-selection gap follows from the test-relevance entries as they
    stand. A gap needs a test that could detect the failure and was not run.

    With `tied`, only the entries of tests tied to the failure by a recorded reference count (w6e): a test found by
    similarity is a candidate for investigation, and its reading neither supports nor blocks the gap. With none tied
    the result is as for no entries. NOT SUPPORTED means a gap is not established by the evidence; it does not show
    that coverage was adequate (5ee)."""
    entries = [t for t in validation.test_relevance if tied is None or tied(t.test)]
    not_run = [t for t in entries
               if norm(t.was_selected_or_executed) != "YES" and t.classification != REMEDIATION_TEST]
    if any(t.classification == DETECTING and norm(t.was_selected_or_executed) == "NO" for t in not_run):
        return GAP_SUPPORTED
    if any(t.classification != NOT_DETECTING for t in not_run):
        return UNCERTAIN
    return GAP_NOT_SUPPORTED


def assess_test_relevance(
    validation: ValidationAssessment,
    strong: set[str],
    weakest: str,
    bundle: EvidenceBundle,
    signal_ids: set[str],
    tied: Callable[[str], bool] | None = None,
    unresolved: set[int] = frozenset(),
) -> list[str]:
    """Classify each candidate test and derive whether a regression-selection gap is
    supported. A gap needs a test that could detect the failure and was not run. `tied`: see derive_selection_gap.
    `unresolved`: ids of the entries that lost a citation (reject_unresolved_citations); with none left that checks
    out, the entry is treated as one without any (G-EVIDENCE-REF)."""
    notes = []
    from_fix = {a.name for a in bundle.test_evidence if a.role == "REMEDIATION"}
    # The gap as the model's own answers imply it, before any of them is corrected below.
    as_answered = validation.model_copy(deep=True)
    for test in as_answered.test_relevance:
        test.classification = {"YES": DETECTING, "NO": NOT_DETECTING}.get(norm(test.could_this_test_detect_the_failure), UNCERTAIN)
    implied, reclassified = derive_selection_gap(as_answered, tied), []
    for test in validation.test_relevance:
        material_note = None
        answer = norm(test.could_this_test_detect_the_failure)
        cited = [a for a in cited_artifacts(" ".join([test.test, *test.evidence]), bundle) if a.category == "test_evidence"]
        named = [a for a in cited if a.ref.lower() in test.test.lower() or a.ref.split(":")[-1].lower() in test.test.lower()] or cited
        if named and all(a.name in from_fix for a in named):
            test.classification = REMEDIATION_TEST
            if answer == "YES" or norm(test.was_selected_or_executed) == "NO":
                notes.append(GuardNote(
                    f"3-validation-release: '{test.test}' is known only from a fix made after the "
                    "defect was reported. It is not counted as a test that existed and was left "
                    "unselected before release.",
                    G_REMEDIATION_TEST, "TEST_COULD_DETECT_FAILURE", subject=test.test, original=answer, corrected=REMEDIATION_TEST,
                ))
                reclassified.append(notes[-1])
            continue
        if answer in {"YES", "NO"} and re.search(
            r"\b(?:(?:has|have) not (?:yet )?been|not yet) (?:assessed|evaluated|determined)\b", test.reasoning, re.I
        ):
            notes.append(GuardNote(
                f"3-validation-release: '{test.test}' states that detectability has not been assessed, "
                "but supplies a decided comparison. Treated as UNCERTAIN for review; wording is not proof of detectability.",
                G_UNASSESSED_RELEVANCE, "TEST_COULD_DETECT_FAILURE", subject=test.test, original=answer, corrected=UNCERTAIN,
            ))
            reclassified.append(notes[-1])
            answer, test.confidence = UNCERTAIN, weakest
        if answer == "NO" and _is_none(test.material_differences):
            answer = UNCERTAIN
            notes.append(GuardNote(
                f"3-validation-release: '{test.test}' was marked not detecting without a stated material difference. "
                "Treated as UNCERTAIN for review; matching words do not establish detectability.",
                G_MATERIAL_DIFFERENCE, "TEST_COULD_DETECT_FAILURE", subject=test.test, original="NO", corrected=UNCERTAIN,
            ))
            reclassified.append(notes[-1])
            material_note = notes[-1]
        if answer == "YES" and not _is_none(test.material_differences):
            answer = UNCERTAIN
            notes.append(GuardNote(
                f"3-validation-release: '{test.test}' was marked able to detect the "
                "failure although material differences from the failing condition are "
                "recorded; treated as UNCERTAIN.",
                G_MATERIAL_DIFFERENCE, "TEST_COULD_DETECT_FAILURE", subject=test.test, original="YES", corrected=UNCERTAIN,
            ))
            reclassified.append(notes[-1])
            material_note = notes[-1]
        if answer == "YES" and id(test) in unresolved and valid_refs(test.evidence, bundle, signal_ids):
            answer = UNCERTAIN
            notes.append(GuardNote(
                f"3-validation-release: '{test.test}' was marked able to detect the failure, but a citation "
                "it gave does not resolve to collected evidence; treated as UNCERTAIN.",
                G_CITATION, "TEST_COULD_DETECT_FAILURE", subject=test.test, original="YES", corrected=UNCERTAIN,
            ))
            reclassified.append(notes[-1])
        if answer == "YES" and not valid_refs(test.evidence, bundle, signal_ids):
            answer = UNCERTAIN
            notes.append(GuardNote(
                f"3-validation-release: '{test.test}' was marked able to detect the "
                "failure without an evidence reference that checks out; treated as UNCERTAIN.",
                G_EVIDENCE_REF, "TEST_COULD_DETECT_FAILURE", subject=test.test, original="YES", corrected=UNCERTAIN,
            ))
            reclassified.append(notes[-1])
        if answer not in {"YES", "NO"}:
            answer = UNCERTAIN
        test.could_this_test_detect_the_failure = answer
        test.classification = {"YES": DETECTING, "NO": NOT_DETECTING}.get(answer, UNCERTAIN)
        if material_note is not None:
            constraint = _material_constraint(material_note.original)
            material_note.superseded_proposal = test.constrain_interpretation(
                "could_this_test_detect_the_failure", constraint, weakest)
            material_note.effective_interpretation = {"reasoning": test.reasoning, "confidence": test.confidence}
        test.refresh_interpretation(weakest)
        if answer != "YES" and norm(test.confidence) in strong and not valid_refs(
            test.evidence, bundle, signal_ids
        ):
            test.confidence = weakest

    validation.regression_selection_gap = derive_selection_gap(validation, tied)
    if validation.regression_selection_gap != implied:
        # The gap changed because the tests it is derived from were reclassified: say by which rule.
        causes = " ".join(str(n).partition(": ")[2] for n in reclassified) or "The classification of the tests it is derived from changed."
        notes.append(GuardNote(
            f"3-validation-release: the regression-selection gap is {validation.regression_selection_gap}, not {implied} as the "
            f"model's own answers about each test would imply. {causes}",
            G_GAP_DERIVED, "REGRESSION_SELECTION_GAP", original=implied, corrected=validation.regression_selection_gap,
        ))
    return notes


def derive_release_decision_gap(causal: CausalAssessment) -> str:
    """Whether a release-decision gap follows from the three release claims as they stand.
    A gap needs a failed signal bearing on the defect that was in front of the release
    decision and was left standing. None of the three answers implies another."""
    claims = causal.decision_claims
    if claims is None:
        return ""
    existed, available, acted = (norm(getattr(claims, name).answer) for name in (
        "signal_failed_before_release", "warning_evidence_available_to_release_decision", "release_signal_acted_upon"))
    if existed == "NO" or available == "NO" or acted == "YES":
        return GAP_NOT_SUPPORTED
    if (existed, available, acted) == ("YES", "YES", "NO"):
        return GAP_SUPPORTED
    return UNCERTAIN


# ------------------------------------------------------------ dispatch


def validate_decision_answers(causal: CausalAssessment, weakest: str, pass_key: str) -> list[str]:
    """A decision claim's confidence is read only with a valid answer (cu0). An answer that is not YES, NO or UNKNOWN
    (missing, a confidence label, a contradiction, a sentence) is unresolved: UNKNOWN at the weakest level, whatever
    confidence came with it, and the claim says so. No answer is guessed from it. The original stays in the stored
    response and in the note. A valid answer is only spelled in the vocabulary; its confidence is left to the rules."""
    notes = []
    claims = causal.decision_claims
    for name in type(claims).model_fields if claims is not None else ():
        claim = getattr(claims, name)
        answer = decision_answer(claim.answer)
        if answer is not None:
            claim.answer = answer
            continue
        was, confidence = claim.answer, claim.confidence
        claim.answer, claim.confidence = "UNKNOWN", weakest
        claim.claim = (f"Not resolved: the answer given was {was!r}, which is not YES, NO or UNKNOWN, so no answer is "
                       f"established. Model's claim: {claim.claim}")
        notes.append(GuardNote(
            f"{pass_key}: '{name}' had the answer {was!r} at {confidence or '(no confidence)'}, which is not YES, NO or "
            f"UNKNOWN; answer set to UNKNOWN and confidence to {weakest}.",
            G_DECISION_ANSWER, "DECISION_CLAIM", name, original=str(was or ""), corrected="UNKNOWN",
        ))
    return notes


def hold_activity_interpretations(value: BaseModel, bundle: EvidenceBundle, levels: list[str],
                                  signal_ids: set[str], key: str) -> list[str]:
    """Canonical model-interpretation boundary; no opportunity status is used as a fact proxy."""
    notes = []
    strong = {norm(level) for level in levels[:2]}
    if isinstance(value, (RequirementsAssessment, ValidationAssessment, LoopAssessment)):
        for finding in value.activities:
            # These are model-authored interpretations. A resolving reference (including a
            # provenance-verified critical signal) is not independent support for their meaning.
            # Recorded execution/release facts remain in their separate deterministic outputs.
            linked = bool(valid_refs(finding.evidence, bundle, signal_ids))
            finding.evidence_status = "EVIDENCE_LINKED_REVIEW_REQUIRED" if linked else "NOT_ESTABLISHED"
            finding.evidence_status_reason = ("References resolve, but the activity interpretation has no independently verified semantic support."
                                              if linked else "No resolving evidence supports this activity interpretation.")
            if norm(finding.status) in strong:
                was, finding.status = finding.status, ACTIVITY_UNKNOWN
                notes.append(GuardNote(
                    f"{key}: '{finding.activity}' was {was}; citation provenance does not establish the activity interpretation. "
                    "Held unresolved; this does not change independently recorded execution or release facts.",
                    "G-ACTIVITY-ESTABLISHMENT", "ACTIVITY", subject=finding.activity, original=was, corrected=ACTIVITY_UNKNOWN,
                ))
    return notes


def apply_after_pass(
    key: str,
    value: BaseModel,
    results: dict[str, BaseModel],
    bundle: EvidenceBundle,
    methodology: Methodology,
    tied: Callable[[str], bool] | None = None,
) -> list[str]:
    """Apply the guards for one pass in place and return notes for the run log. `tied` tells which tests the failure is
    tied to by a recorded reference (the reconciler's graph); without it every entry counts, as before (w6e)."""
    levels = methodology.confidence_levels()
    strong, weakest = {norm(level) for level in levels[:2]}, levels[-1]
    trace = value if isinstance(value, TraceabilityResult) else results.get("1-traceability")
    notes: list[str] = []
    if isinstance(value, TraceabilityResult):
        assign_signal_ids(value)
        notes += validate_trace_citations(value, bundle, levels)
    # Only signals whose provenance holds may be cited by a later finding (xkn).
    signal_ids = verified_signal_ids(trace, bundle)

    def activities(result: BaseModel) -> list[tuple[BaseModel, str, str, str]]:
        return [(a, a.activity, "status", "evidence") for a in result.activities]

    def absences(result: BaseModel) -> list[tuple[BaseModel, str, str, str]]:
        return [(a, a.activity, "status", "finding") for a in result.activities]

    def cite(items: list[tuple[BaseModel, str, str | None, str]], weak: str) -> set[int]:
        found, touched = reject_unresolved_citations(items, strong, weak, bundle, signal_ids, key)
        notes.extend(found)
        return touched

    def cited(result: BaseModel) -> list[tuple[BaseModel, str, str | None, str]]:
        return [(a, a.activity, "status", "evidence") for a in result.activities]

    if isinstance(value, TraceabilityResult):
        notes += validate_links(value, bundle, levels)
    elif isinstance(value, RequirementsAssessment):
        notes += _downgrade_unsupported(
            activities(value), strong, ACTIVITY_UNKNOWN, bundle, signal_ids, key
        )
        cite(cited(value), ACTIVITY_UNKNOWN)
        notes += downgrade_absence_claims(absences(value), strong, ACTIVITY_UNKNOWN, bundle, key)
    elif isinstance(value, ValidationAssessment):
        unresolved = cite([(t, t.test, "confidence", "evidence") for t in value.test_relevance], weakest)
        notes += assess_test_relevance(value, strong, weakest, bundle, signal_ids, tied, unresolved)
        notes += _downgrade_unsupported(
            activities(value), strong, ACTIVITY_UNKNOWN, bundle, signal_ids, key
        )
        cite(cited(value), ACTIVITY_UNKNOWN)
        notes += downgrade_absence_claims(absences(value), strong, ACTIVITY_UNKNOWN, bundle, key)
    elif isinstance(value, CausalAssessment):
        # Never accept engine status supplied by a model or a stored response. Reconciliation recomputes it.
        if value.decision_claims is not None:
            for name in type(value.decision_claims).model_fields:
                said = getattr(value.decision_claims, name)
                said.evidence_status = "NOT_ESTABLISHED"
                said.evidence_status_reason = "Not assessed against verified support."
                said.verified_support_refs = []
        notes += validate_decision_answers(value, weakest, key)   # first: every rule below reads the answer
        items = [(layer, layer.layer, "confidence", "evidence") for layer in value.layers]
        missed = value.earliest_reasonable_missed_opportunity
        items.append((missed, "earliest reasonable missed opportunity", "confidence", "evidence"))
        if value.decision_claims is not None:
            items += [
                (getattr(value.decision_claims, name), name, "confidence", "evidence_refs")
                for name in type(value.decision_claims).model_fields
            ]
        notes += _downgrade_unsupported(items, strong, weakest, bundle, signal_ids, key)
        cite([*items, *((a, a.value, None, "evidence") for a in value.recorded_attributions or [])], weakest)
        notes += downgrade_absence_claims(
            [(layer, layer.layer, "confidence", "finding") for layer in value.layers], strong, weakest, bundle, key
        )
        notes += downgrade_absence_answers(value, weakest, bundle, key)
        claimed = mechanism_claim(value, bundle)   # read before the layer it was written under is corrected
        notes += enforce_causal_limits(value, bundle, weakest, signal_ids, key)
        notes += verify_mechanism(value, bundle, signal_ids, key, levels, claimed)
        if value.defect_mechanism is not None:   # after the quote check, which reads only the artifacts a citation names
            cite([(value.defect_mechanism, "defect mechanism", None, "evidence")], weakest)
        notes += verify_attributions(value, bundle, key)
        validation = results.get("3-validation-release")
        gap = getattr(validation, "regression_selection_gap", "")
        claims = value.decision_claims
        if (
            claims is not None
            and gap
            and norm(claims.relevant_test_existed.answer) == "YES"
            and not any(t.classification == DETECTING for t in validation.test_relevance)
        ):
            claims.relevant_test_existed.answer = "UNKNOWN"
            claims.relevant_test_existed.confidence = weakest
            notes.append(GuardNote(
                f"{key}: the claim that a relevant test existed was YES, but the "
                "test-relevance assessment classifies no test as DETECTING; answer set to "
                "UNKNOWN.",
                G_NO_DETECTING_TEST, "DECISION_CLAIM", "relevant_test_existed", original="YES", corrected="UNKNOWN",
            ))
        value.release_decision_gap = derive_release_decision_gap(value)
        if (
            REGRESSION_ACTIVITY in squash(missed.activity)
            and gap in {GAP_NOT_SUPPORTED, UNCERTAIN}
            and norm(missed.confidence) != norm(weakest)
        ):
            was, missed.confidence = missed.confidence, weakest
            notes.append(GuardNote(
                f"{key}: the earliest missed opportunity is anchored to regression "
                f"selection, but the test-relevance assessment is {gap}; confidence set "
                f"to {weakest}.",
                G_MISSED_OPPORTUNITY, "EARLIEST_MISSED_OPPORTUNITY", original=was, corrected=weakest,
            ))
    elif isinstance(value, LoopAssessment):
        notes += _downgrade_unsupported(
            activities(value), strong, ACTIVITY_UNKNOWN, bundle, signal_ids, key
        )
        cite(cited(value), ACTIVITY_UNKNOWN)
        notes += downgrade_absence_claims(absences(value), strong, ACTIVITY_UNKNOWN, bundle, key)
    elif isinstance(value, ActionPlan):
        cite([(a, a.action, None, "evidence") for a in value.actions], weakest)
    notes += hold_activity_interpretations(value, bundle, levels, signal_ids, key)
    return notes


# ------------------------------------------------------------ presentation boundary (xkn)

CITATION_FIELDS = ("source_artifact", "target_artifact", "source", "evidence", "evidence_refs", "supporting_span_sources")


def citation_audit(results: dict[str, BaseModel], bundle: EvidenceBundle) -> list[dict]:
    """Every citation still in an authoritative field of the results that names no collected evidence (or a critical
    signal whose provenance does not hold), checked as G-CITATION checks it, before anything is presented. Unresolved
    citations kept for diagnostics (`unresolved_citations`) are not authoritative and are not read. Empty when every guard
    did its work."""
    signals = verified_signal_ids(results.get("1-traceability"), bundle)
    found = []

    def walk(node, path: str, key: str) -> None:
        if isinstance(node, dict):
            for name, value in node.items():
                if name in CITATION_FIELDS:
                    for ref in value if isinstance(value, list) else [value]:
                        if isinstance(ref, str) and _is_citation(ref) and not valid_refs([ref], bundle, signals):
                            found.append({"pass": key, "field": f"{path}.{name}", "citation": ref})
                elif name != "unresolved_citations":
                    walk(value, f"{path}.{name}", key)
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]", key)

    for key, value in results.items():
        if isinstance(value, BaseModel):
            walk(value.model_dump(), "", key)
    return found


_BRACKETED = re.compile(r"\[([^\[\]\n]{2,200})\](?!\()")
_CITATION_SHAPE = re.compile(r"^(?:[a-z][\w-]*:\S+|[\w][\w.-]*\.(?:md|json|txt)|signal-\d+)$", re.I)


def mark_unresolved_citations(text: str, bundle: EvidenceBundle, signal_ids: set[str]) -> tuple[str, list[str]]:
    """The report text with every bracketed citation that names no collected evidence marked as unresolved (xkn), and
    the citations marked. Only what is shaped like a citation is read (an evidence ID, a file name, a signal ID); the
    text is otherwise unchanged, and nothing is replaced by a similar name."""
    flagged: list[str] = []

    def mark(match: re.Match) -> str:
        parts = [p.strip() for p in re.split(r"[,;]", match.group(1))]
        bad = [p for p in parts if _CITATION_SHAPE.match(p) and not valid_refs([p], bundle, signal_ids)]
        if not bad:
            return match.group(0)
        flagged.extend(bad)
        return f"{match.group(0)} (unresolved citation, not in the collected evidence: {', '.join(bad)})"

    return _BRACKETED.sub(mark, text), flagged


# ------------------------------------------------------------ prompt block


def constraints_block(results: dict[str, BaseModel]) -> str | None:
    """Engine-validated facts later passes must not contradict."""
    lines = []
    trace = results.get("1-traceability")
    if isinstance(trace, TraceabilityResult):
        for signal in trace.critical_signals:
            if signal.id and not signal.verified:
                lines.append(
                    f"- {signal.id} is not verified: its source is not in the collected evidence, or does not hold what it "
                    f"says. Do not cite {signal.id} as evidence, and do not state what it says as established."
                )
        for link in trace.links:
            if not link.verified_support and link.unresolved_citations:
                lines.append(
                    f"- The relationship {link.from_item} → {link.to_item} is unresolved: the evidence it cited "
                    f"({'; '.join(link.unresolved_citations)}) is not in the collected evidence."
                )
        for link in inferred_links(trace):
            lines.append(
                f"- The relationship {link.from_item} → {link.to_item} is INFERRED. No "
                "artifact records it. Never describe it as a reference, link or citation "
                "that one artifact makes to the other."
            )
    validation = results.get("3-validation-release")
    if isinstance(validation, ValidationAssessment) and validation.regression_selection_gap:
        lines.append(
            f"- Regression-selection gap: {validation.regression_selection_gap}. A "
            "regression-selection gap exists only when a test that could detect this "
            "failure existed and was not selected or executed."
        )
        for test in validation.test_relevance:
            if test.classification == REMEDIATION_TEST:
                lines.append(
                    f"- {test.test} is known only from the fix. It did not protect the release "
                    "and is not a regression-selection gap."
                )
            elif test.classification == NOT_DETECTING:
                lines.append(
                    f"- {test.test} is {NOT_DETECTING}: {test.material_differences} Do not "
                    "state or imply that running it could have caught this failure."
                )
            elif test.classification == UNCERTAIN:
                lines.append(
                    f"- Whether {test.test} could have detected this failure is "
                    f"{UNCERTAIN}. Present it as an open question, not as a cause."
                )
    if not lines:
        return None
    return (
        "# Engine-validated constraints\n\nThese were checked against the case artifacts "
        "and the earlier structured results. Your output must be consistent with them.\n\n"
        + "\n".join(lines)
    )


# ------------------------------------------------------------ final prose checks

_DIRECT_TERMS = re.compile(
    r"\b(?:references?|referenced|referencing|links? to|linked (?:to|from|in)|cites?|cited|"
    r"mentions?|mentioned|explicitly|directly)\b",
    re.I,
)
_NEGATION = re.compile(r"\b(?:no|not|never|without|inferred|neither|lacks?|absent)\b", re.I)
_COULD_DETECT = re.compile(
    r"\b(?:could|would|might|may)(?: have| potentially| possibly)*"
    r"(?: \w+){0,2}? (?:detect\w*|caught|catch|expos\w*|uncover\w*|reveal\w*|identif\w*|found)\b",
    re.I,
)


def _sentences(markdown: str) -> list[str]:
    out = []
    for line in markdown.splitlines():
        out += [s.strip() for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()]
    return out


_INTRODUCED = re.compile(r"\b(?:introduc\w+|root cause|caused|causing|regress\w*|originat\w+) ", re.I)
_FIX_WORDS = re.compile(r"\b(?:fix\w*|remediat\w*|resolv\w*|correct\w*|after the (?:defect|issue)|repair\w*)\b", re.I)


def remediation_misuse(narrative: str, bundle: EvidenceBundle) -> list[tuple[str, str]]:
    """Report sentences that present a remediation change as what introduced the defect."""
    found = []
    tokens = remediation_tokens(bundle)
    for sentence in _sentences(narrative):
        named = next((t for t in sorted(tokens) if t in sentence), None)
        if named and _INTRODUCED.search(sentence + " ") and not _FIX_WORDS.search(sentence) and not _NEGATION.search(sentence):
            found.append((
                f"remediation-as-cause:{named}",
                f"The report text presents {named} as introducing the defect, but it is a "
                f"REMEDIATION change made after the defect was reported. Sentence: \"{sentence}\"",
            ))
    return found


# A statement that a fix exists and took effect.
_FIX_CLAIM = re.compile(
    r"\b(?:implemented|applied|deployed|merged|shipped|released|delivered)\s+(?:the\s+|a\s+)?fix\b"
    r"|\bfix(?:es)?\s+(?:(?:was|were|is|has been|have been)\s+)?(?:successfully\s+)?"
    r"(?:implemented|applied|deployed|merged|shipped|released|resolved|stabilized|restored|corrected|eliminated|worked)\b"
    r"|\b(?:was|were|has been|have been|is now)\s+(?:successfully\s+)?(?:fixed|remediated|patched)\b"
    r"|\b(?:after|since|following|with) the fix\b|\bpost-fix\b",
    re.I,
)
# A fix that is proposed, wanted or absent is not a claim that one was made.
_FIX_PROPOSED = re.compile(
    r"\b(?:suggest\w*|recommend\w*|propos\w*|should|would|could|must|needs?|pending|planned|"
    r"to be|no|not|never|without|yet)\b|n't\b",
    re.I,
)
# What an artifact writes when a fix exists.
_FIX_RECORDED = re.compile(
    r"^- (?:Resolved|Fix versions): \S|\bhotfix\b|\b(?:fixed|resolved) (?:in|by|on|with)\b"
    r"|\bfix(?:es)? (?:(?:was|were|has been|have been|is)\s+)?(?:merged|deployed|released|shipped|implemented|applied|verified)\b",
    re.I | re.M,
)
NO_FIX_RECORDED = "the evidence records no fix: no remediation change was collected and no artifact states that one was made"


def fix_recorded(bundle: EvidenceBundle) -> bool:
    """A remediation change was collected, or an artifact itself says a fix was made."""
    return bool(bundle.remediation_changes) or any(_FIX_RECORDED.search(a.content) for a in bundle.artifacts())


def claims_a_fix(text: str) -> bool:
    return bool(_FIX_CLAIM.search(text)) and not _FIX_PROPOSED.search(text)


def unrecorded_fix_claims(narrative: str, bundle: EvidenceBundle) -> list[tuple[str, str]]:
    """Report sentences that present a fix as made although the evidence records none."""
    if fix_recorded(bundle):
        return []
    return [
        (
            f"unrecorded-fix:{index}",
            f"The report text presents a fix as made, but {NO_FIX_RECORDED}. Sentence: \"{sentence}\"",
        )
        for index, sentence in enumerate(s for s in _sentences(narrative) if claims_a_fix(s))
    ]


def prose_inconsistencies(narrative: str, results: dict[str, BaseModel]) -> list[tuple[str, str]]:
    """(key, message) for report sentences that contradict the validated structure:
    an inferred link written as a direct reference, or a test classified as not
    detecting written as able to catch the failure. Lexical and sentence-level, so it
    catches the plain cases only."""
    found: list[tuple[str, str]] = []
    sentences = _sentences(narrative)
    trace = results.get("1-traceability")
    if isinstance(trace, TraceabilityResult):
        for link in inferred_links(trace):
            ids_from, ids_to = item_ids(link.from_item), item_ids(link.to_item)
            if not ids_from or not ids_to:
                continue
            for sentence in sentences:
                if (
                    any(contains_id(sentence, i) for i in ids_from)
                    and any(contains_id(sentence, i) for i in ids_to)
                    and _DIRECT_TERMS.search(sentence)
                    and not _NEGATION.search(sentence)
                ):
                    found.append(
                        (
                            f"direct-claim:{link.from_item}->{link.to_item}",
                            f"The report text presents {link.from_item} → {link.to_item} "
                            "as a direct reference, but the validated traceability link "
                            f"is INFERRED. Treat it as inferred. Sentence: \"{sentence}\"",
                        )
                    )
                    break
    validation = results.get("3-validation-release")
    if isinstance(validation, ValidationAssessment):
        for test in validation.test_relevance:
            if test.classification != NOT_DETECTING:
                continue
            ids = item_ids(test.test) or {test.test}
            for sentence in sentences:
                if (
                    any(i in sentence for i in ids)
                    and _COULD_DETECT.search(sentence)
                    and not _NEGATION.search(sentence)
                ):
                    found.append(
                        (
                            f"test-claim:{test.test}",
                            f"The report text suggests {test.test} could have caught "
                            f"the failure, but it is classified {NOT_DETECTING} "
                            f"({test.material_differences}). Sentence: \"{sentence}\"",
                        )
                    )
                    break
    return found
