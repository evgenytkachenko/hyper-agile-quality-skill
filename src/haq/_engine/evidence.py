"""Case folder -> normalized evidence bundle.

The categories are deliberately generic. Future connectors map their own systems into
these categories; nothing here knows where an artifact originally came from."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field, PrivateAttr

from .errors import EvidenceError

# file stem -> evidence category. The single place the case-file convention is defined.
CATEGORY_BY_STEM = {
    "production-issue": "production_issue",
    "originating-story": "originating_work",
    "requirements": "requirements",
    "documentation": "documentation",
    "code-change": "implementation_changes",
    "fix-change": "remediation_changes",
    "tests": "test_evidence",
    "ci": "ci_evidence",
    "release": "release_evidence",
    "production-learning": "production_evidence",
}
FALLBACK_CATEGORY = "additional_evidence"
CATEGORIES = (*CATEGORY_BY_STEM.values(), FALLBACK_CATEGORY)
# Categories whose absence is normal and is not reported as an evidence limitation.
OPTIONAL_CATEGORIES = {"remediation_changes"}
# Roles of a change relative to the defect being assessed.
ORIGINATING, REMEDIATION, UNKNOWN_ROLE = "ORIGINATING", "REMEDIATION", "UNKNOWN"
FULL, COMPACTED, OMITTED = "FULL", "COMPACTED", "OMITTED"
SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt"}
# The reviewer's answer key for a historical case. It records what really happened, so
# it must never reach the model: it is read only by the post-run evaluation.
ANSWER_KEY_STEM = "answer-key"
# Files that are never evidence: the folder's own description, and the answer key.
IGNORED_STEMS = {"readme", ANSWER_KEY_STEM}


# An identity is a whole token: not inside a longer identifier or file name on either side ("release-" before it, ".md",
# a digit or a path after it). A full stop that ends a sentence, and a ':' that starts a qualifier, may follow it.
_LEFT = r"(?<![\w.:#@-])"
_RIGHT = r"(?![\w/#@-]|\.\w)"


class EvidenceArtifact(BaseModel):
    name: str
    category: str
    content: str
    source_path: str
    truncated: bool = False
    # Stable identifier used to cite this artifact, e.g. "jira:SHOP-1", "testiny:TC-7".
    # Empty for a file in a hand-written case folder, which is cited by its file name.
    evidence_id: str = ""
    # Priority for the model's working set: 1 is always kept, 3 is dropped first.
    # None means "decide from the category".
    tier: int | None = None
    # DIRECT or INFERRED, when the artifact was found through a recorded relationship.
    relation: str = ""
    # For changes: ORIGINATING, REMEDIATION or UNKNOWN.
    role: str = ""
    # Shorter, deterministic representations of the same evidence, prepared when the
    # artifact was collected, from most to least detailed. Never shown unless the working
    # set selects one.
    compact_forms: list[str] = Field(default_factory=list)
    # FULL, COMPACTED or OMITTED once a working set has been built.
    treatment: str = ""

    @property
    def ref(self) -> str:
        """How findings cite this artifact: its evidence ID, or its file name."""
        return self.evidence_id or self.name

    @property
    def heading(self) -> str:
        label = f"[{self.ref}]" + (f" {self.name}" if self.name != self.ref else "")
        return f"### {label} (category: {self.category})"

    @property
    def compact(self) -> str:
        """The most detailed compact form, or an empty string."""
        return self.compact_forms[0] if self.compact_forms else ""


class EvidenceBundle(BaseModel):
    case_id: str
    production_issue: list[EvidenceArtifact] = Field(default_factory=list)
    originating_work: list[EvidenceArtifact] = Field(default_factory=list)
    requirements: list[EvidenceArtifact] = Field(default_factory=list)
    documentation: list[EvidenceArtifact] = Field(default_factory=list)
    implementation_changes: list[EvidenceArtifact] = Field(default_factory=list)
    # Changes made after the defect was reported, to fix it. Never the introducing change.
    remediation_changes: list[EvidenceArtifact] = Field(default_factory=list)
    test_evidence: list[EvidenceArtifact] = Field(default_factory=list)
    ci_evidence: list[EvidenceArtifact] = Field(default_factory=list)
    release_evidence: list[EvidenceArtifact] = Field(default_factory=list)
    production_evidence: list[EvidenceArtifact] = Field(default_factory=list)
    additional_evidence: list[EvidenceArtifact] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    # The collected relationships, by the source ID of each item they tie (wdl). Kept beside the bundle, never in it:
    # not serialized, so the snapshot and every digest of the bundle are as they were. None for a hand-written case.
    _relations: dict[str, list[str]] | None = PrivateAttr(default=None)
    # The same relationships as recorded pairs of the items they tie, with what records them (xkn: a DIRECT link may rest on one).
    _ties: list[tuple[str, str, str]] = PrivateAttr(default_factory=list)
    # Citable passages of the issues, by reference (ond): built from the snapshot's records, beside the bundle, never in it.
    _passages: dict[str, tuple[str, str, str]] = PrivateAttr(default_factory=dict)

    def set_passages(self, records: list[dict]) -> None:
        """Index each issue record's passages under stable references: KEY/title, KEY/type, KEY/status,
        KEY/affected-versions, KEY/fix-versions, KEY/components, KEY/link-N (metadata); KEY/dN for the description's
        paragraphs and KEY/cN for its comments (substance). Derived from the record only, so the same snapshot gives the
        same references. Comment authors are not part of a passage."""
        passages: dict[str, tuple[str, str, str]] = {}
        for record in records:
            key = str(record.get("id") or "")
            if not key:
                continue
            for name, field in (("title", "title"), ("type", "type"), ("status", "status"), ("affected-versions", "affected_versions"),
                                ("fix-versions", "fix_versions"), ("components", "components")):
                value = record.get(field)
                text = ", ".join(map(str, value)) if isinstance(value, list) else str(value or "")
                if text.strip():
                    passages[f"{key}/{name}"] = (key, "metadata", text.strip())
            for n, link in enumerate(record.get("links") or [], start=1):
                passages[f"{key}/link-{n}"] = (key, "metadata", f"{link.get('relation', '')}: {link.get('target_id', '')} — "
                                                                f"{link.get('target_title', '')}".strip())
            paragraphs = [p.strip() for p in str(record.get("description") or "").split("\n\n") if p.strip()]
            for n, paragraph in enumerate(paragraphs, start=1):
                passages[f"{key}/d{n}"] = (key, "description", " ".join(paragraph.split()))
            for n, comment in enumerate(record.get("comments") or [], start=1):
                body = " ".join(str(comment.get("body") or "").split())
                if body:
                    passages[f"{key}/c{n}"] = (key, "comment", body)
        self._passages = passages

    def passage(self, ref: str) -> tuple[str, str, str] | None:
        """(issue key, section, text) of a passage reference, or None."""
        return self._passages.get(ref.strip().strip("[]").strip())

    def passages_of(self, key: str) -> list[tuple[str, str, str]]:
        """(reference, section, text) of one issue's passages, in index order."""
        return [(ref, section, text) for ref, (owner, section, text) in self._passages.items() if owner == key]

    def set_relationships(self, rows: list) -> None:
        """Index collected relationships (dicts as stored, or Relationship models) by the items they tie."""
        relations: dict[str, list[str]] = {}
        for row in rows:
            raw = row if isinstance(row, dict) else row.model_dump()
            kind, source, target = (str(raw.get(k, "")) for k in ("relationship_type", "source", "target"))
            direct = raw.get("direct_or_inferred") or "UNKNOWN"
            said = (f"recorded issue link: {source} {kind.removeprefix('issue link:').strip()} {target} ({direct})"
                    if kind.startswith("issue link:") else f"recorded {kind}: {source} to {target} ({direct})")
            for item in {source, target}:
                relations.setdefault(item, []).append(said)
            self._ties.append((source, target, said))
        self._relations = relations

    def recorded_ties(self) -> list[tuple[str, str, str]]:
        """(source item, target item, how it is recorded) for every collected relationship."""
        return list(self._ties)

    def named(self, text: str) -> list[EvidenceArtifact]:
        """The evidence registry (xkn): the artifacts whose canonical identity, its evidence ID or its file name as the
        collector recorded it, is written in `text` exactly, as a whole token (case aside). Nothing is matched by
        similarity, prefix or construction: `github-deployment-7001.md` names nothing when the artifact is
        `release-github-deployment-7001.md`, and `testiny:TC-1801.md` names nothing when it is `testiny:TC-1801`. A
        token may be followed by a qualifier after ':' or a space (`jira-PW-1060.md: TC-2101`); what the qualifier
        claims is checked by the caller."""
        found = []
        for artifact in self.artifacts():
            for identity in dict.fromkeys(i for i in (artifact.evidence_id, artifact.name) if i):
                if re.search(rf"{_LEFT}{re.escape(identity)}{_RIGHT}", text, flags=re.I):
                    found.append(artifact)
                    break
        return found

    def heading(self, artifact: EvidenceArtifact) -> str:
        """How a prompt heads an artifact. A collected work item is headed by what ties it to the case as recorded, with no
        role: the collector files every linked issue that is not a parent as originating work, which is a storage
        category, not what the records say about it (wdl). A hand-written case keeps the category its author gave."""
        if artifact.category != "originating_work" or self._relations is None:
            return artifact.heading
        label = f"[{artifact.ref}]" + (f" {artifact.name}" if artifact.name != artifact.ref else "")
        ties = self._relations.get(artifact.ref.partition(":")[2] or artifact.ref) or ["no recorded relationship"]
        return f"### {label} (linked work item; {'; '.join(dict.fromkeys(ties))})"

    def artifacts(self, categories: tuple[str, ...] = CATEGORIES) -> list[EvidenceArtifact]:
        return [a for category in categories for a in getattr(self, category)]

    def render(self, categories: tuple[str, ...] = CATEGORIES) -> str:
        """Prompt text for the artifacts in the given categories."""
        blocks = [f"{self.heading(a)}\n{a.content}" for a in self.artifacts(categories)]
        return "\n\n".join(blocks) if blocks else "(no artifacts in these categories)"

    def manifest(self) -> str:
        lines = [
            f"- [{a.ref}] — {a.category}, {len(a.content)} characters"
            + (" (truncated)" if a.truncated else "")
            + (" (compact form; the full artifact is in the evidence snapshot)" if a.treatment == COMPACTED else "")
            for a in self.artifacts()
        ]
        return "\n".join(lines)


def load_case(case_dir: Path, max_chars_per_artifact: int) -> EvidenceBundle:
    if not case_dir.is_dir():
        raise EvidenceError(f"Case folder does not exist: {case_dir}")

    bundle = EvidenceBundle(case_id=case_dir.resolve().name)
    for path in sorted(case_dir.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.stem.lower() in IGNORED_STEMS:
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            bundle.limitations.append(f"Skipped unsupported file type: {path.name}")
            continue
        content = path.read_text(encoding="utf-8", errors="replace").strip()
        if not content:
            bundle.limitations.append(f"Skipped empty file: {path.name}")
            continue
        truncated = len(content) > max_chars_per_artifact
        if truncated:
            bundle.limitations.append(
                f"{path.name} was truncated to the first {max_chars_per_artifact} characters "
                f"(of {len(content)})."
            )
            content = content[:max_chars_per_artifact]
        category = CATEGORY_BY_STEM.get(path.stem.lower(), FALLBACK_CATEGORY)
        getattr(bundle, category).append(
            EvidenceArtifact(
                name=path.name,
                category=category,
                content=content,
                source_path=str(path),
                truncated=truncated,
            )
        )

    if not bundle.artifacts():
        raise EvidenceError(
            f"No supported evidence files found in {case_dir} "
            f"(supported: {', '.join(sorted(SUPPORTED_SUFFIXES))})."
        )
    for category in CATEGORY_BY_STEM.values():
        if category not in OPTIONAL_CATEGORIES and not getattr(bundle, category):
            bundle.limitations.append(
                f"No {category.replace('_', ' ')} artifact was provided in the case folder."
            )
    return bundle
