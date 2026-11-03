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
from types import UnionType
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError

from ._engine.passes import ENGINE_SET

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


_KIND = {dict: "an object", list: "a list", str: "text", bool: "true or false", int: "a number", float: "a number",
         type(None): "null"}
MAX_SHAPE_PROBLEMS = 50


def _kind(value: Any) -> str:
    return _KIND.get(type(value), "a value")


class _Shape:
    """What conforming an answer to its schema removed. Holds locations and type names only, never content."""

    def __init__(self) -> None:
        self.dropped = 0
        self.problems: list[str] = []
        self.total = 0

    def omit(self, path: str, expected: str, value: Any) -> str:
        self.total += 1
        if len(self.problems) < MAX_SHAPE_PROBLEMS:
            self.problems.append(f"{path or '(answer)'}: expected {expected}, got {_kind(value)}")
        return f"[OMITTED: expected {expected}, got {_kind(value)}]"


def _expected(annotation: Any) -> str:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return "an object"
    if get_origin(annotation) is list:
        return "a list"
    if get_origin(annotation) in (Union, UnionType):
        return " or ".join(dict.fromkeys(_expected(a) for a in get_args(annotation)))
    return _KIND.get(annotation, "a value of a supported shape")


def _fits(value: Any, annotation: Any) -> bool:
    """Whether a value has the outer shape the annotation asks for (contents are checked by conform)."""
    if annotation is Any:
        return False                                    # nothing free-form is kept
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return isinstance(value, dict)
    origin = get_origin(annotation)
    if origin is list:
        return isinstance(value, list)
    if origin in (Union, UnionType):
        return any(_fits(value, arm) for arm in get_args(annotation))
    if annotation is str:
        return isinstance(value, str)
    if annotation is bool:
        return isinstance(value, bool)
    if annotation in (int, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if annotation is type(None):
        return value is None
    return False                                        # dict-typed and any other shape: never kept from an answer


def _conform(value: Any, annotation: Any, path: str, shape: _Shape) -> Any:
    if not _fits(value, annotation):
        return shape.omit(path, _expected(annotation), value)
    if get_origin(annotation) in (Union, UnionType):
        arm = next(a for a in get_args(annotation) if _fits(value, a))
        return _conform(value, arm, path, shape)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        kept = {}
        for key, item in value.items():
            field = annotation.model_fields.get(key)
            if field is None or ENGINE_SET in (field.description or ""):
                shape.dropped += 1
                continue
            kept[key] = _conform(item, field.annotation, f"{path}.{key}" if path else key, shape)
        return kept
    if get_origin(annotation) is list:
        (inner,) = get_args(annotation) or (Any,)
        return [_conform(item, inner, f"{path}[{n}]", shape) for n, item in enumerate(value)]
    return value                                        # a scalar of the expected type


def conform(value: Any, model: type[BaseModel]) -> tuple[Any, int, list[str]]:
    """Keep only what the step's schema asks the answer for, in the shape it asks for, at every depth.

    - Keys outside the schema, and fields the engine sets itself, are dropped (counted). A key name may abbreviate a
      credential in a way no pattern can tell apart from an ordinary word, so unknown keys are never kept.
    - A value whose shape differs from the schema's (an object or list where text is expected, a list of lists, a
      scalar where an object is expected, ...) is replaced by a marker naming the expected and received shape; its
      content is not kept. Each such location is reported, so the answer is rejected rather than used.
    Returns (conformed value, keys dropped, shape problems)."""
    shape = _Shape()
    kept = _conform(value, model, "", shape)
    problems = list(shape.problems)
    if shape.total > len(problems):
        problems.append(f"... and {shape.total - len(problems)} more location(s) of the wrong shape")
    return kept, shape.dropped, problems


def prune(value: Any, model: type[BaseModel]) -> tuple[Any, int]:
    """conform() without the shape problems, for callers that only need the kept value and the dropped count."""
    kept, dropped, _ = conform(value, model)
    return kept, dropped


def intake(raw: str, model: type[BaseModel] | None = None) -> tuple[dict | None, dict]:
    """(sanitized object or None, the record to keep for this attempt). The record never holds unsanitized text.
    With `model`, the answer is conformed to that schema (see conform) before anything is kept; a record whose
    status is "wrong_shape" lists the problems, and the caller must reject the answer."""
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
    dropped, problems = 0, []
    if model is not None:
        clean, dropped, problems = conform(clean, model)
    record = {"status": "parsed", "characters_received": len(raw), "answer": clean}
    if dropped:
        record["keys_not_kept"] = f"{dropped} key(s) outside the answer schema are not kept."
    if problems:
        record["status"] = "wrong_shape"
        record["shape_problems"] = problems
        record["omitted"] = ("Values whose shape differs from the schema are replaced by [OMITTED: ...] markers; "
                             "their content is not kept.")
    if outside:
        record["outside_object"] = f"{outside} character(s) outside the JSON object (reasoning, prose or fences) are not kept."
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
