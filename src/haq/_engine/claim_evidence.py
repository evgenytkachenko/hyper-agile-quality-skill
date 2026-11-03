"""Per-field provenance, deliberately unable to certify semantic support."""
from __future__ import annotations

import hashlib
from typing import Literal
from pydantic import BaseModel, Field, model_serializer


class EvidenceLink(BaseModel):
    source_id: str
    part: str
    quote: str


class ClaimEvidence(BaseModel):
    claim: str
    links: list[EvidenceLink] = Field(default_factory=list)
    # These are observations at generation, never authority on reload.
    quote_checks: list[dict[str, str]] = Field(default_factory=list)
    semantic_status: Literal["UNVERIFIED"] = "UNVERIFIED"


class EvidenceLinked(BaseModel):
    claim_evidence: dict[str, ClaimEvidence] = Field(default_factory=dict)

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        data = handler(self)
        if not self.claim_evidence:
            data.pop("claim_evidence", None)
        return data


def bind_claims(claims: dict[str, str], links: dict[str, list[EvidenceLink]],
                sources: dict[str, dict[str, str]]) -> dict[str, ClaimEvidence]:
    """Exact source/part/quote checks. A true quote may still contradict its claim.

    Unknown field keys are retained as unverified observations, never assigned to a
    different claim. Empty claims/links are explicit; legacy callers can omit the ledger.
    """
    out = {}
    for field in dict.fromkeys([*claims, *links]):
        checks = []
        for link in links.get(field, []):
            parts = sources.get(link.source_id)
            text = parts.get(link.part) if parts is not None else None
            status = ("UNKNOWN_SOURCE" if parts is None else "WRONG_PART" if text is None
                      else "MISSING_QUOTE" if not link.quote.strip() or link.quote not in text
                      else "VERIFIED_QUOTE")
            checks.append({"status": status, "source_sha256": hashlib.sha256(text.encode()).hexdigest()
                           if text is not None else ""})
        out[field] = ClaimEvidence(claim=claims.get(field, ""), links=links.get(field, []), quote_checks=checks)
    return out


def describe_claims(claims: dict[str, ClaimEvidence]) -> str:
    if not claims:
        return "Per-field provenance unavailable (legacy or absent); semantic support UNVERIFIED."
    return "\n".join(f"- {field}: semantic support UNVERIFIED; " +
                     (", ".join(c["status"] for c in value.quote_checks) or "NO_LINKS")
                     for field, value in sorted(claims.items()))


def required_link_failures(claims: dict[str, ClaimEvidence], required: tuple[str, ...]) -> list[str]:
    """Read a freshly bound ledger, not saved verdicts. Provenance only, never entailment.

    One valid link cannot launder an invalid companion. Unknown/optional keys remain
    observable but do not supply or invalidate any required field.
    """
    failures = []
    for field in required:
        entry = claims.get(field)
        if entry is None or not entry.claim.strip():
            failures.append(f"{field}: EMPTY_CLAIM")
        elif not entry.links:
            failures.append(f"{field}: NO_LINKS")
        elif len(entry.quote_checks) != len(entry.links) or any(
                check.get('status') != 'VERIFIED_QUOTE' for check in entry.quote_checks):
            failures.append(f"{field}: " + ', '.join(check.get('status', 'UNVERIFIED') for check in entry.quote_checks))
    return failures
