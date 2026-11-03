"""Run an investigation: evidence -> three answered steps -> deterministic checks -> report.

    1-trace         engine pass "1-traceability"        engine guards (links, citations, signals)
    2-validation    engine pass "3-validation-release"  engine guards (test relevance, derived gap,
                                                        citations, absence claims, activity holds)
    3-hypotheses    this skill's hypothesis step         engine guard functions + H-* checks

Code fixes the order, what each step sees and every check. The answer provider (scripted,
local model or agent) only proposes. Nothing writes outside the output folder.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from . import ENGINE_SOURCE_COMMIT, __version__
from ._engine import guards
from ._engine.errors import HyperAgileError, PassOutputError
from ._engine.masking import mask, mask_text
from ._engine.methodology import Methodology
from ._engine.providers.base import ModelProvider
from .adapters import LoadedCase, load_evidence
from .hypotheses import QualityInvestigation, answer_problems, check_investigation
from .prompts import STEPS, StepSpec, approx_tokens, schema, system_prompt, user_prompt

METHODOLOGY_DIR = Path(__file__).parent / "_methodology"

_THINKING = re.compile(r"<think>.*?</think>", re.S)
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(raw: str) -> str:
    """The JSON object in an answer (same rule as the engine's orchestrator)."""
    text = _THINKING.sub("", raw)
    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in the response")
    return text[start:end + 1]


@dataclass
class Investigation:
    case: LoadedCase
    provider_label: str
    provider_name: str
    model: str
    results: dict[str, BaseModel] = field(default_factory=dict)
    raw: dict[str, BaseModel] = field(default_factory=dict)
    checks: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    methodology_hashes: dict[str, str] = field(default_factory=dict)
    # per step: sha256 of every masked attempt, the files they were kept in, the accepted one, exchange bindings
    attempts: dict[str, list[str]] = field(default_factory=dict)
    attempt_files: dict[str, list[str]] = field(default_factory=dict)
    accepted: dict[str, str] = field(default_factory=dict)
    bindings: dict[str, str] = field(default_factory=dict)

    @property
    def trace(self):
        return self.results.get("1-trace")

    @property
    def validation(self):
        return self.results.get("2-validation")

    @property
    def hypotheses(self) -> QualityInvestigation | None:
        return self.results.get("3-hypotheses")  # type: ignore[return-value]


def _record_attempt(inv: "Investigation", raw_dir: Path | None, step: str, raw: str) -> str:
    """Keep every answer as received (masked), before it is validated, so a failed answer is never lost."""
    masked = mask_text(raw)
    inv.attempts.setdefault(step, []).append(hashlib.sha256(masked.encode("utf-8")).hexdigest())
    if raw_dir is not None:
        n = 1
        while (raw_dir / f"{step}.attempt-{n}.txt").exists():
            n += 1
        (raw_dir / f"{step}.attempt-{n}.txt").write_text(masked, encoding="utf-8")
        inv.attempt_files.setdefault(step, []).append(f"raw/{step}.attempt-{n}.txt")
    return masked


def _parse(masked: str, output: type[BaseModel], levels: list[str]) -> BaseModel:
    """Masked answer text -> validated model. Raises ValueError/ValidationError with masked content only."""
    value = output.model_validate(mask(json.loads(extract_json(masked))))
    problems = answer_problems(value, levels)
    if problems:
        raise ValueError("; ".join(problems))
    return value


def _ask(provider: ModelProvider, inv: "Investigation", raw_dir: Path | None, step: StepSpec, system: str,
         user: str, json_schema: dict, levels: list[str]) -> tuple[str, BaseModel]:
    """One answer, validated against the step schema and vocabulary. One repair attempt for a model, as in the
    engine; a saved (scripted or exchange) answer is never retried."""
    if hasattr(provider, "current_step"):
        provider.current_step = step.key
    where = f" Every attempt is kept under {raw_dir}." if raw_dir else ""
    masked = _record_attempt(inv, raw_dir, step.key, provider.generate(system, user, json_schema=json_schema))
    try:
        return masked, _parse(masked, step.output, levels)
    except (ValueError, ValidationError) as first:
        if provider.name in ("scripted", "exchange"):
            raise PassOutputError(f"The saved answer for step {step.key} cannot be used: "
                                  f"{mask_text(str(first))[:2000]}{where}") from first
        repair = (f"{user}\n\n# Your previous answer could not be used\n\n{mask_text(str(first))[:2000]}\n\n"
                  "Answer again with one JSON object that matches the schema exactly.")
        masked = _record_attempt(inv, raw_dir, step.key, provider.generate(system, repair, json_schema=json_schema))
        try:
            return masked, _parse(masked, step.output, levels)
        except (ValueError, ValidationError) as second:
            raise PassOutputError(f"Step {step.key}: the answer could not be used after one repair attempt: "
                                  f"{mask_text(str(second))[:500]}{where}") from second


def run_investigation(case_dir: Path, provider: ModelProvider, *, variant_dir: Path | None = None,
                      out_dir: Path | None = None, context_tokens: int | None = None) -> Investigation:
    methodology = Methodology.load(METHODOLOGY_DIR)
    case = load_evidence(case_dir, variant_dir)
    levels = methodology.confidence_levels()
    inv = Investigation(case=case, provider_label=mask_text(getattr(provider, "label", provider.name)),
                        provider_name=provider.name, model=mask_text(provider.model),
                        methodology_hashes=methodology.hashes())
    raw_dir = out_dir / "raw" if out_dir else None
    if raw_dir:
        raw_dir.mkdir(parents=True, exist_ok=True)

    for step in STEPS:
        system = system_prompt(step, methodology)
        user = user_prompt(step, methodology, case.bundle, inv.results, case.title)
        size = approx_tokens(system) + approx_tokens(user)
        if context_tokens and size > 0.9 * context_tokens:
            inv.warnings.append(f"{step.key}: the prompt is about {size} tokens, close to or above the configured "
                                f"context of {context_tokens}; the runtime may truncate it silently.")
        # What a saved (exchange) answer must be bound to, besides the request text itself.
        provider.binding_inputs = {
            "tool": __version__, "engine_source_commit": ENGINE_SOURCE_COMMIT,
            "evidence_files_sha256": case.files, "variant": case.variant,
            "methodology_sha256": inv.methodology_hashes,
            "earlier_answers_sha256": {k: v for k, v in inv.accepted.items()},
        }
        masked, value = _ask(provider, inv, raw_dir, step, system, user, schema(step, methodology), levels)
        inv.accepted[step.key] = hashlib.sha256(masked.encode("utf-8")).hexdigest()
        inv.raw[step.key] = value.model_copy(deep=True)

        if step.engine_pass is not None:
            # Engine keys: the guards look up earlier results under the engine's pass names.
            engine_results = {"1-traceability": inv.results["1-trace"]} if "1-trace" in inv.results else {}
            notes = guards.apply_after_pass(step.engine_pass.key, value, engine_results, case.bundle, methodology)
        else:
            notes = check_investigation(value, case.bundle, levels, methodology.loop_activities(),  # type: ignore[arg-type]
                                        inv.trace, inv.validation)
        for note in notes:
            if isinstance(note, guards.GuardNote):
                inv.checks.append({"step": step.key, **note.record(step.key)})
            else:
                inv.checks.append({"step": step.key, "guard_id": "ENGINE-NOTE", "reason": str(note).partition(": ")[2] or str(note)})
        inv.results[step.key] = value
    inv.bindings = dict(getattr(provider, "bindings", {}) or {})
    return inv


# ------------------------------------------------------------------ outputs and human decisions

MARKER = "haq-output.json"
PREVIOUS = "previous-run"
GENERATED = ("report.md", "results.json", "checks.json", "run.json")
DECISIONS = "decisions.yaml"


def is_digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def short_digest(value: object) -> str:
    """For messages: a value read from someone's file is shown only if it is a digest."""
    return f"{value[:12]}…" if is_digest(value) else "(not a digest)"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def result_digest(inv: Investigation) -> str:
    """What a person's decisions review: the checked results and everything they were derived from. No timestamps."""
    payload = {
        "tool": __version__, "engine_source_commit": ENGINE_SOURCE_COMMIT,
        "case_id": inv.case.bundle.case_id, "variant": inv.case.variant,
        "evidence_files_sha256": inv.case.files, "methodology_sha256": inv.methodology_hashes,
        "answers": {"provider": inv.provider_name, "model": inv.model, "accepted_sha256": inv.accepted},
        "checked": {k: v.model_dump(mode="json") for k, v in inv.results.items()},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def decisions_state(out_dir: Path) -> str:
    """absent | untouched (exactly the template this tool wrote) | edited (anything else, including unknown)."""
    path = out_dir / DECISIONS
    if not path.exists():
        return "absent"
    try:
        run = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
        if run.get("decisions_template_sha256") == _sha(path):
            return "untouched"
    except (OSError, ValueError):
        pass
    return "edited"


def _archive_decisions(out_dir: Path) -> Path:
    path = out_dir / DECISIONS
    try:
        bound = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("result_sha256")
    except (OSError, yaml.YAMLError, AttributeError):
        bound = None
    # The name comes from a file a person wrote: use it only if it is a digest, so it cannot form a path.
    stem = f"decisions.superseded-{bound[:12] if is_digest(bound) else 'unbound'}"
    n, target = 1, out_dir / f"{stem}.yaml"
    while target.exists() or target.is_symlink():
        n += 1
        target = out_dir / f"{stem}-{n}.yaml"
    if target.parent.resolve() != out_dir.resolve():
        raise HyperAgileError("Refusing to archive decisions outside the output folder.")
    path.rename(target)
    return target


def prepare_out_dir(out_dir: Path, overwrite: bool, archive_decisions: bool = False) -> list[str]:
    """Make the output folder safe to write into, before any answer is requested. Returns notes to print.

    - A new or empty folder is used and marked as a haq output folder.
    - A haq folder whose run did not finish (only raw attempts) is reused, so a step-by-step exchange can continue.
    - A finished run is replaced only with --overwrite, which replaces the generated files and raw attempts.
    - A decisions.yaml a person may have edited is never overwritten or deleted: the run is refused unless
      --archive-decisions is given, which renames it to decisions.superseded-<result>.yaml first.
    """
    notes: list[str] = []
    if out_dir.exists() and any(out_dir.iterdir()):
        if not (out_dir / MARKER).is_file():
            raise HyperAgileError(f"{out_dir} is not empty and is not a haq output folder. Choose a new folder.")
        state = decisions_state(out_dir)
        if state == "edited" and not archive_decisions:
            raise HyperAgileError(
                f"{out_dir / DECISIONS} may contain a person's decisions, and a new run would produce a result they "
                "did not review. Nothing was changed. Choose a new --out folder, or pass --archive-decisions to keep "
                "them as decisions.superseded-<result>.yaml and start a fresh, unreviewed decisions.yaml.")
        finished = (out_dir / "run.json").is_file()
        if finished and not overwrite:
            raise HyperAgileError(f"{out_dir} holds a finished investigation. Choose a new folder, or pass "
                                  "--overwrite to replace its report, results, checks, run record and raw attempts "
                                  "(decisions.yaml is never overwritten).")
        if state == "edited":
            notes.append(f"Kept the earlier decisions as {_archive_decisions(out_dir).name}.")
        if finished:
            # Keep the previous result until the new one is written (write_outputs removes it); if this run
            # fails, it stays in previous-run/ and nothing is lost.
            previous = out_dir / PREVIOUS
            if previous.exists():
                shutil.rmtree(previous)
            previous.mkdir()
            for name in (*GENERATED, *((DECISIONS,) if state == "untouched" else ()), "raw"):
                if (out_dir / name).exists():
                    (out_dir / name).rename(previous / name)
            notes.append(f"The previous result was moved to {previous}; it is removed when this run finishes.")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / MARKER).write_text(json.dumps({"tool": "hyper-agile-quality-skill", "version": __version__}) + "\n",
                                  encoding="utf-8")
    return notes


def write_outputs(inv: Investigation, out_dir: Path) -> dict[str, Path]:
    from .report import decisions_template, render_report

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {name.split(".")[0]: out_dir / name for name in GENERATED}
    paths["decisions"] = out_dir / DECISIONS
    if paths["decisions"].exists():
        # prepare_out_dir has already moved edited decisions aside; anything here now was not expected.
        raise HyperAgileError(f"{paths['decisions']} already exists; refusing to overwrite it.")
    digest = result_digest(inv)
    report = render_report(inv)
    template = decisions_template(inv, digest)
    paths["report"].write_text(report, encoding="utf-8")
    paths["results"].write_text(json.dumps({
        "result_sha256": digest,
        "checked": {k: v.model_dump(mode="json") for k, v in inv.results.items()},
        "as_answered": {k: v.model_dump(mode="json") for k, v in inv.raw.items()},
        "limitations": inv.case.bundle.limitations,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["checks"].write_text(json.dumps(inv.checks, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["decisions"].write_text(template, encoding="utf-8")
    paths["run"].write_text(json.dumps({
        "tool": f"hyper-agile-quality-skill {__version__}",
        "engine_source_commit": ENGINE_SOURCE_COMMIT,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "case_id": inv.case.bundle.case_id,
        "variant": inv.case.variant,
        "answers": {"provider": inv.provider_name, "label": inv.provider_label, "model": inv.model,
                    "accepted_sha256": inv.accepted, "attempt_files": inv.attempt_files,
                    "exchange_bindings": inv.bindings},
        "methodology_sha256": inv.methodology_hashes,
        "evidence_files_sha256": inv.case.files,
        "result_sha256": digest,
        "report_sha256": hashlib.sha256(report.encode()).hexdigest(),
        "decisions_template_sha256": hashlib.sha256(template.encode()).hexdigest(),
        "warnings": inv.warnings,
    }, indent=1) + "\n", encoding="utf-8")
    if (out_dir / PREVIOUS).is_dir() and (out_dir / MARKER).is_file():
        shutil.rmtree(out_dir / PREVIOUS)
    return paths


def check_decisions(out_dir: Path) -> tuple[bool, list[str]]:
    """Whether decisions.yaml reviews the result now in the folder, and what it records."""
    run = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    try:
        data = yaml.safe_load((out_dir / DECISIONS).read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return False, [f"No {DECISIONS} in {out_dir}."]
    except yaml.YAMLError as exc:
        return False, [f"{DECISIONS} is not readable YAML ({type(exc).__name__})."]
    lines, ok = [], True
    if not isinstance(data, dict) or data.get("result_sha256") != run.get("result_sha256"):
        ok = False
        named = data.get("result_sha256") if isinstance(data, dict) else None
        lines.append(f"{DECISIONS} is not bound to this result (it names {short_digest(named)}, the result is "
                     f"{short_digest(run.get('result_sha256'))}). Its decisions do not apply to this report.")
    items = {**(data.get("hypotheses") or {}), **(data.get("proposals") or {})} if isinstance(data, dict) else {}
    decided = {k: v.get("decision") for k, v in items.items() if isinstance(v, dict) and v.get("decision")}
    lines.append(f"{len(decided)} of {len(items)} item(s) decided" + (": " + ", ".join(f"{k}={v}" for k, v in decided.items()) if decided else "."))
    return ok, lines
