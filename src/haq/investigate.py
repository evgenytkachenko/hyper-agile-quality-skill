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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ValidationError

from . import ENGINE_SOURCE_COMMIT, __version__
from ._engine import guards
from ._engine.errors import HyperAgileError, PassOutputError
from ._engine.methodology import Methodology
from ._engine.providers.base import ModelProvider
from .adapters import LoadedCase, load_evidence
from .hypotheses import QualityInvestigation, check_investigation
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

    @property
    def trace(self):
        return self.results.get("1-trace")

    @property
    def validation(self):
        return self.results.get("2-validation")

    @property
    def hypotheses(self) -> QualityInvestigation | None:
        return self.results.get("3-hypotheses")  # type: ignore[return-value]


def _ask(provider: ModelProvider, step: StepSpec, system: str, user: str, json_schema: dict,
         output: type[BaseModel]) -> tuple[str, BaseModel]:
    """One answer, validated against the step schema. One repair attempt, as in the engine."""
    if hasattr(provider, "current_step"):
        provider.current_step = step.key
    raw = provider.generate(system, user, json_schema=json_schema)
    try:
        return raw, output.model_validate_json(extract_json(raw))
    except (ValueError, ValidationError) as first:
        if provider.name in ("scripted", "exchange"):
            # A saved answer cannot be repaired by asking again: fix the file and rerun.
            raise PassOutputError(f"The saved answer for step {step.key} does not match the schema: "
                                  f"{str(first)[:2000]}") from first
        repair = (f"{user}\n\n# Your previous answer could not be used\n\n{str(first)[:2000]}\n\n"
                  "Answer again with one JSON object that matches the schema exactly.")
        raw = provider.generate(system, repair, json_schema=json_schema)
        try:
            return raw, output.model_validate_json(extract_json(raw))
        except (ValueError, ValidationError) as second:
            raise PassOutputError(f"Step {step.key}: the answer did not match the schema after one repair "
                                  f"attempt: {str(second)[:500]}") from second


def run_investigation(case_dir: Path, provider: ModelProvider, *, variant_dir: Path | None = None,
                      out_dir: Path | None = None, context_tokens: int | None = None) -> Investigation:
    methodology = Methodology.load(METHODOLOGY_DIR)
    case = load_evidence(case_dir, variant_dir)
    levels = methodology.confidence_levels()
    inv = Investigation(case=case, provider_label=getattr(provider, "label", provider.name),
                        provider_name=provider.name, model=provider.model,
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
        raw_text, value = _ask(provider, step, system, user, schema(step, methodology), step.output)
        if raw_dir:
            (raw_dir / f"{step.key}.answer.txt").write_text(raw_text, encoding="utf-8")
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
    return inv


def write_outputs(inv: Investigation, out_dir: Path) -> dict[str, Path]:
    from .report import decisions_template, render_report

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "report": out_dir / "report.md",
        "results": out_dir / "results.json",
        "checks": out_dir / "checks.json",
        "run": out_dir / "run.json",
        "decisions": out_dir / "decisions.yaml",
    }
    report = render_report(inv)
    paths["report"].write_text(report, encoding="utf-8")
    paths["results"].write_text(json.dumps({
        "checked": {k: v.model_dump(mode="json") for k, v in inv.results.items()},
        "as_answered": {k: v.model_dump(mode="json") for k, v in inv.raw.items()},
        "limitations": inv.case.bundle.limitations,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["checks"].write_text(json.dumps(inv.checks, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["decisions"].write_text(decisions_template(inv), encoding="utf-8")
    paths["run"].write_text(json.dumps({
        "tool": f"hyper-agile-quality-skill {__version__}",
        "engine_source_commit": ENGINE_SOURCE_COMMIT,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "case_id": inv.case.bundle.case_id,
        "variant": inv.case.variant,
        "answers": {"provider": inv.provider_name, "label": inv.provider_label, "model": inv.model},
        "methodology_sha256": inv.methodology_hashes,
        "evidence_files_sha256": inv.case.files,
        "report_sha256": hashlib.sha256(report.encode()).hexdigest(),
        "warnings": inv.warnings,
    }, indent=1) + "\n", encoding="utf-8")
    return paths


def prepare_out_dir(out_dir: Path, overwrite: bool) -> None:
    if out_dir.exists() and any(out_dir.iterdir()) and not overwrite:
        raise HyperAgileError(f"{out_dir} already exists and is not empty. Choose a new folder or pass --overwrite.")
    out_dir.mkdir(parents=True, exist_ok=True)
