"""How an answer is made safe before anything keeps or shows it.

Policy:

- A parseable answer is decoded first (so JSON escapes such as ``\\u0067hp_...`` become the text they encode),
  then sanitized recursively: every string value and every key is masked with the engine's patterns, and the whole
  value under a sensitive key (password, secret, token, API key, credential, cookie, ...) is replaced. Only this
  sanitized structure is kept, validated, shown in a repair prompt or written anywhere.
- Text outside the JSON object (reasoning, prose, code fences) is not kept; its length is recorded.
- An answer that cannot be parsed cannot be sanitized safely, because a secret may sit in text that no pattern
  recognizes once escaped or cut. None of its content is kept or echoed: only its length and the parser's reason,
  which names a position, never content.
- Validation errors are described by field location and message only, never by the offending input.
"""

from __future__ import annotations

import json
import re
from typing import Any, get_args

from pydantic import BaseModel, ValidationError

from ._engine.masking import MASK, mask_text

# Broader than the engine's exact-name list: any key that names a credential, wherever it appears in the name.
_SEP = r"[_.\- ]"   # separators between words in a key name: snake, kebab, dotted, spaced (camelCase needs none)
SENSITIVE_KEY = re.compile(
    r"(?i)(pass(?:word|wd|phrase)|(?:^|SEP)pass$|pwd|secret|token|api(?:SEP)?key|access(?:SEP)?key|"
    r"private(?:SEP)?key|credential|authori[sz]ation|(?:^|SEP)auth(?:$|SEP)|auth(?:SEP)?header|oauth|cookie|"
    r"sess(?:ion)?(?:SEP)?id|bearer|signature|connection(?:SEP)?string|(?:^|SEP)dsn$)".replace("SEP", _SEP))

_THINKING = re.compile(r"<think>.*?</think>", re.S)
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, dict):
        return {mask_text(str(k)): (MASK if SENSITIVE_KEY.search(str(k)) and value[k] not in (None, "", [], {})
                                    else sanitize(value[k]))
                for k in value}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return value


def _json_span(raw: str) -> tuple[str, int]:
    """The JSON object in an answer (same rule as the engine's orchestrator) and how many characters lie outside it."""
    text = _THINKING.sub("", raw)
    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in the answer")
    span = text[start:end + 1]
    return span, len(raw) - len(span)


def _model_of(annotation: Any) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in get_args(annotation):
        found = _model_of(arg)
        if found is not None:
            return found
    return None


def prune(value: Any, model: type[BaseModel]) -> tuple[Any, int]:
    """Keep only the keys the step's schema defines, at every depth; return the kept value and how many were dropped.

    A key outside the schema is never used, and its name may abbreviate a credential in a way no pattern can tell
    apart from an ordinary word (dbPass, bypass), so it is not kept at all."""
    if not isinstance(value, dict):
        return value, 0
    kept, dropped = {}, 0
    for key, item in value.items():
        field = model.model_fields.get(key)
        if field is None:
            dropped += 1
            continue
        inner = _model_of(field.annotation)
        if inner is not None and isinstance(item, dict):
            item, n = prune(item, inner)
            dropped += n
        elif inner is not None and isinstance(item, list):
            pruned = [prune(x, inner) for x in item]
            item, dropped = [x for x, _ in pruned], dropped + sum(n for _, n in pruned)
        kept[key] = item
    return kept, dropped


def intake(raw: str, model: type[BaseModel] | None = None) -> tuple[dict | None, dict]:
    """(sanitized object or None, the record to keep for this attempt). The record never holds unsanitized text.
    With `model`, keys outside that schema are dropped before anything is kept (their number is recorded)."""
    try:
        span, outside = _json_span(raw)
        decoded = json.loads(span)
    except RecursionError:
        return None, {"status": "unparseable", "characters_received": len(raw),
                      "reason": "the JSON is nested too deeply to decode", "omitted": OMITTED}
    except json.JSONDecodeError as exc:
        return None, {"status": "unparseable", "characters_received": len(raw),
                      "reason": f"invalid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}", "omitted": OMITTED}
    except ValueError as exc:
        return None, {"status": "unparseable", "characters_received": len(raw), "reason": str(exc), "omitted": OMITTED}
    if not isinstance(decoded, dict):
        return None, {"status": "unparseable", "characters_received": len(raw),
                      "reason": f"the answer is a JSON {type(decoded).__name__}, not an object", "omitted": OMITTED}
    try:
        clean = sanitize(decoded)
        json.dumps(clean, ensure_ascii=False).encode("utf-8")   # unpaired surrogate escapes cannot be kept as text
    except (RecursionError, UnicodeEncodeError) as exc:
        reason = ("the JSON is nested too deeply to sanitize" if isinstance(exc, RecursionError)
                  else "the JSON contains unpaired surrogate escapes")
        return None, {"status": "unparseable", "characters_received": len(raw), "reason": reason, "omitted": OMITTED}
    dropped = 0
    if model is not None:
        clean, dropped = prune(clean, model)
    record = {"status": "parsed", "characters_received": len(raw), "answer": clean}
    if dropped:
        record["keys_not_kept"] = f"{dropped} key(s) outside the answer schema are not kept."
    if outside:
        record["omitted"] = f"{outside} character(s) outside the JSON object (reasoning, prose or fences) are not kept."
    return clean, record


OMITTED = "The answer text is not kept or shown: it could not be parsed, so it cannot be sanitized safely."


def describe(exc: Exception) -> str:
    """A validation problem without the offending input."""
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc'])) or '(root)'}: {e['msg']}"
                         for e in exc.errors(include_input=False, include_url=False))
    return mask_text(str(exc))


def canonical(clean: dict) -> str:
    return json.dumps(clean, ensure_ascii=False)
