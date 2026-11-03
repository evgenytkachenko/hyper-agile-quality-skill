"""Masks credential-like content before anything collected from a source system is
saved or shown. Applied to raw payloads, normalized evidence and error messages."""

from __future__ import annotations

import re
from typing import Any

MASK = "[REDACTED]"

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S), MASK),
    (re.compile(r"(?i)\b(authorization\s*[:=]\s*)(?:(?:bearer|basic|token)\s+)?[^\s\"',;]+"), rf"\1{MASK}"),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/-]{16,}=*"), rf"\1{MASK}"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), MASK),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), MASK),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"), MASK),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), MASK),
    (re.compile(r"\bATATT[A-Za-z0-9_=-]{20,}"), MASK),  # Atlassian API tokens
    (re.compile(r"\b(?:secret|ntn)_[A-Za-z0-9]{30,}\b"), MASK),  # Notion tokens
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+"), MASK),
    (
        re.compile(
            r"(?i)([?&](?:access_token|api[_-]?key|apikey|token|key|secret|password|signature|sig)=)[^&\s\"'<>]+"
        ),
        rf"\1{MASK}",
    ),
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s/:@]+:)[^\s/@]+(@)"), rf"\1{MASK}\2"),
    (
        re.compile(
            r"(?i)((?<![a-z])(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|auth[_-]?token|token)"
            r"\s*[\"']?\s*[:=]\s*[\"']?)(?=[^\s\"'<>,&\[]*\d)[^\s\"'<>,&\[]{8,}"
        ),
        rf"\1{MASK}",
    ),
)
# Dictionary keys whose values are never kept, whatever they look like.
_SECRET_KEYS = re.compile(
    r"(?i)^(authorization|x-api-key|api[_-]?key|token|access[_-]?token|refresh[_-]?token|"
    r"password|secret|client[_-]?secret|private[_-]?key|cookie|set-cookie)$"
)


def mask_text(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def mask(value: Any) -> Any:
    """Recursively mask strings in JSON-like data."""
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, dict):
        return {
            k: MASK if isinstance(k, str) and _SECRET_KEYS.match(k) and v else mask(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [mask(v) for v in value]
    return value
