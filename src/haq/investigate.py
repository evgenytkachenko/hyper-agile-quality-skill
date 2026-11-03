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
from ._engine.masking import mask_text
from ._engine.methodology import Methodology
from ._engine.providers.base import ModelProvider
from .adapters import LoadedCase, load_evidence
from .hypotheses import QualityInvestigation, answer_problems, check_investigation
from .sanitize import canonical, describe, intake
from .prompts import STEPS, StepSpec, approx_tokens, schema, system_prompt, user_prompt

METHODOLOGY_DIR = Path(__file__).parent / "_methodology"

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
    unparseable: dict[str, list[str]] = field(default_factory=dict)

    @property
    def trace(self):
        return self.results.get("1-trace")

    @property
    def validation(self):
        return self.results.get("2-validation")

    @property
    def hypotheses(self) -> QualityInvestigation | None:
        return self.results.get("3-hypotheses")  # type: ignore[return-value]


def _record_attempt(inv: "Investigation", raw_dir: Path | None, step: str, raw: str,
                    model: type[BaseModel] | None = None) -> dict | None:
    """Sanitize an answer (see sanitize.py) and keep the attempt record, before it is validated. Returns the
    sanitized object, or None when the answer could not be parsed; its text is then neither kept nor shown."""
    clean, record = intake(raw, model)
    text = json.dumps({"step": step, **record}, indent=1, ensure_ascii=False) + "\n"
    inv.attempts.setdefault(step, []).append(hashlib.sha256(text.encode("utf-8")).hexdigest())
    if raw_dir is not None:
        n = 1
        while (raw_dir / f"{step}.attempt-{n}.json").exists():
            n += 1
        (raw_dir / f"{step}.attempt-{n}.json").write_text(text, encoding="utf-8")
        inv.attempt_files.setdefault(step, []).append(f"raw/{step}.attempt-{n}.json")
    if clean is None:
        inv.unparseable.setdefault(step, []).append(record["reason"])
    return clean


def _parse(clean: dict | None, step: str, inv: "Investigation", output: type[BaseModel],
           levels: list[str]) -> BaseModel:
    """Sanitized answer -> validated model. Raises ValueError/ValidationError; describe() keeps inputs out."""
    if clean is None:
        raise ValueError(f"the answer could not be parsed ({inv.unparseable[step][-1]}); its text is not shown.")
    value = output.model_validate(clean)
    problems = answer_problems(value, levels)
    if problems:
        raise ValueError("; ".join(problems))
    return value


def _ask(provider: ModelProvider, inv: "Investigation", raw_dir: Path | None, step: StepSpec, system: str,
         user: str, json_schema: dict, levels: list[str]) -> tuple[dict, BaseModel]:
    """One answer, validated against the step schema and vocabulary. One repair attempt for a model, as in the
    engine; a saved (scripted or exchange) answer is never retried."""
    if hasattr(provider, "current_step"):
        provider.current_step = step.key
    where = f" Every attempt is kept, sanitized, under {raw_dir}." if raw_dir else ""
    clean = _record_attempt(inv, raw_dir, step.key, provider.generate(system, user, json_schema=json_schema),
                            step.output)
    try:
        return clean, _parse(clean, step.key, inv, step.output, levels)
    except (ValueError, ValidationError) as first:
        problem = mask_text(describe(first))[:2000]
        if provider.name in ("scripted", "exchange"):
            raise PassOutputError(f"The saved answer for step {step.key} cannot be used: {problem}{where}") from None
        repair = (f"{user}\n\n# Your previous answer could not be used\n\n{problem}\n\n"
                  "Answer again with one JSON object that matches the schema exactly.")
        clean = _record_attempt(inv, raw_dir, step.key, provider.generate(system, repair, json_schema=json_schema),
                                step.output)
        try:
            return clean, _parse(clean, step.key, inv, step.output, levels)
        except (ValueError, ValidationError) as second:
            raise PassOutputError(f"Step {step.key}: the answer could not be used after one repair attempt: "
                                  f"{mask_text(describe(second))[:500]}{where}") from None


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
        clean, value = _ask(provider, inv, raw_dir, step, system, user, schema(step, methodology), levels)
        inv.accepted[step.key] = hashlib.sha256(canonical(clean).encode("utf-8")).hexdigest()
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


def result_basis(inv: Investigation) -> dict:
    """Everything a result was derived from, apart from the checked results themselves. Recorded in run.json."""
    return {
        "tool": __version__, "engine_source_commit": ENGINE_SOURCE_COMMIT,
        "case_id": inv.case.bundle.case_id, "variant": inv.case.variant,
        "evidence_files_sha256": inv.case.files, "methodology_sha256": inv.methodology_hashes,
        "answers": {"provider": inv.provider_name, "model": inv.model, "accepted_sha256": inv.accepted},
    }


def digest_of(basis: dict, checked: dict) -> str:
    payload = {**basis, "checked": checked}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def result_digest(inv: Investigation) -> str:
    """What a person's decisions review: the checked results and everything they were derived from. No timestamps."""
    return digest_of(result_basis(inv), {k: v.model_dump(mode="json") for k, v in inv.results.items()})


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
        "result_basis": result_basis(inv),
        "artifacts_sha256": {name: _sha(out_dir / name) for name in ("report.md", "results.json", "checks.json")},
        "decisions_template_sha256": hashlib.sha256(template.encode()).hexdigest(),
        "warnings": inv.warnings,
    }, indent=1) + "\n", encoding="utf-8")
    if (out_dir / PREVIOUS).is_dir() and (out_dir / MARKER).is_file():
        shutil.rmtree(out_dir / PREVIOUS)
    return paths


def check_decisions(out_dir: Path, case_dir: Path | None = None,
                    variant_dir: Path | None = None) -> tuple[bool, list[str]]:
    """Whether decisions.yaml reviews the result now in the folder, and whether that result is intact.

    Verified: decisions.yaml names the result digest recorded in run.json; that digest is recomputed from
    results.json and the recorded basis; report.md, results.json and checks.json match the hashes recorded when they
    were written; with case_dir, the evidence files in the case folder (and variant) are re-hashed and compared.
    Not verified: a deliberate, consistent rewrite of every file (nothing is signed), and, without case_dir, whether
    the evidence changed after the run."""
    problems: list[str] = []
    try:
        run = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
        results = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, [f"FAIL: run.json or results.json is missing or unreadable ({type(exc).__name__}); "
                       "no decision here can be tied to a result."]
    if not isinstance(run, dict) or not isinstance(results, dict):
        return False, ["FAIL: run.json or results.json does not hold a JSON object; no decision here can be tied to a "
                       "result."]
    try:
        data = yaml.load((out_dir / DECISIONS).read_text(encoding="utf-8"), Loader=_StrictLoader) or {}
    except FileNotFoundError:
        return False, [f"FAIL: no {DECISIONS} in {out_dir}."]
    except DuplicateKey as exc:
        return False, [f"FAIL: {DECISIONS} repeats the key '{mask_text(str(exc))[:40]}'; a reader and this tool could "
                       "see different decisions, so none applies. Keep one entry per key."]
    except yaml.YAMLError as exc:
        return False, [f"FAIL: {DECISIONS} is not readable YAML ({type(exc).__name__})."]
    recorded = run.get("result_sha256")
    named = data.get("result_sha256") if isinstance(data, dict) else None
    if named != recorded:
        problems.append(f"{DECISIONS} names result {short_digest(named)}, but this folder's result is "
                        f"{short_digest(recorded)}. Its decisions do not apply to this report.")
    basis, checked = run.get("result_basis"), results.get("checked")
    if not isinstance(basis, dict) or not isinstance(checked, dict):
        problems.append("run.json has no recorded result basis (written by an older version?); the result cannot be "
                        "recomputed, so it cannot be verified.")
    elif digest_of(basis, checked) != recorded or results.get("result_sha256") != recorded:
        problems.append("results.json or run.json was changed after the run: the result digest recomputed from them "
                        "does not match the recorded one.")
    artifacts = run.get("artifacts_sha256")
    if not isinstance(artifacts, dict):
        problems.append("run.json has no recorded output hashes; report.md, results.json and checks.json cannot be "
                        "verified.")
    else:
        for name in ("report.md", "results.json", "checks.json"):
            path = out_dir / name
            if not path.is_file() or _sha(path) != artifacts.get(name):
                problems.append(f"{name} differs from the file this run wrote.")
    if case_dir is not None:
        try:
            current = load_evidence(case_dir, variant_dir)
        except HyperAgileError as exc:
            problems.append(f"The case folder could not be loaded to verify the evidence: {mask_text(str(exc))}")
        else:
            was = basis if isinstance(basis, dict) else {}
            if current.bundle.case_id != was.get("case_id") or current.files != was.get("evidence_files_sha256"):
                changed = sorted(set(current.files.items()) ^ set((was.get("evidence_files_sha256") or {}).items()))
                names = sorted({n for n, _ in changed})
                problems.append("The evidence differs from what this result was derived from"
                                + (f" ({len(names)} file(s): {', '.join(names[:10])})" if names else
                                   " (a different case or variant)") + ". Decisions do not carry over to it.")
    lines = [f"FAIL: {p}" for p in problems]
    if not problems:
        lines.append("OK: decisions.yaml names this result, the result recomputes from results.json and run.json, and "
                     "report.md, results.json and checks.json are as written.")
        lines.append("OK: the case folder's evidence is unchanged." if case_dir is not None else
                     "NOT CHECKED: evidence. Pass --case (and --variant) to verify the case folder has not changed.")
    decided, content = _decision_content(data, checked if isinstance(checked, dict) else {},
                                         (basis or {}).get("case_id") if isinstance(basis, dict) else None)
    if content:
        lines = [line for line in lines if not line.startswith("OK: decisions.yaml names")]
        lines[:0] = [f"FAIL: {p}" for p in content]
        problems += content
    listed = ", ".join(f"{k}={v}" for k, v in decided.items())
    if problems:
        lines.append("0 decisions apply to this result" + (f" ({len(decided)} recorded but NOT applicable: {listed})"
                                                            if decided else "."))
    else:
        lines.append(f"{len(decided)} item(s) of this result decided" + (f": {listed}" if decided else "."))
    lines.append("NOT CHECKED: the raw/ attempt records, run.json fields other than the recorded result basis and output "
                 "hashes (for example warnings and the answer-source label), and whether the installed tool and "
                 "methodology are the versions recorded in the basis.")
    lines.append("These checks detect changed or inconsistent files; they cannot detect a deliberate, consistent "
                 "rewrite of all of them, because nothing is signed.")
    return not problems, lines


DECISION_VALUES = ("accept", "reject", "investigate")
MAX_TEXT = 2000


class DuplicateKey(yaml.YAMLError):
    pass


class _StrictLoader(yaml.SafeLoader):
    """Safe YAML that refuses a key repeated within one mapping (plain safe_load keeps the last one silently)."""


def _no_duplicates(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    loader.flatten_mapping(node)
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            if key in seen:
                raise DuplicateKey(str(key))
            seen.add(key)
        except TypeError:
            pass   # unhashable keys are rejected by the base constructor below
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)


TOP_LEVEL_KEYS = {"case", "result_sha256", "hypotheses", "proposals"}
ITEM_KEYS = {"hypotheses": {"checked_status", "decision", "decided_by_role", "reason"},
             "proposals": {"decision", "decided_by_role", "reason"}}


def _decision_content(data: object, checked: dict, case_id: str | None) -> tuple[dict[str, str], list[str]]:
    """The valid decisions recorded for this result's items, and every way decisions.yaml goes beyond the template
    for that result: other keys or fields, another case, unknown items, decision values outside the template's, or a
    checked status that is not the result's. Anything outside the template could be read as a wider approval."""
    problems: list[str] = []
    hyp = checked.get("3-hypotheses") if isinstance(checked, dict) else None
    if not isinstance(hyp, dict) or not all(isinstance(hyp.get(k, []), list) for k in
                                            ("hypotheses", "proposed_regression_tests", "proposed_controls")):
        hyp = {}
        problems.append("results.json does not hold a hypotheses result in the expected form; no decision can be "
                        "matched to it.")
    statuses = {h.get("id"): h.get("check_status") for h in hyp.get("hypotheses") or [] if isinstance(h, dict)}
    proposals = {p.get("id") for k in ("proposed_regression_tests", "proposed_controls")
                 for p in hyp.get(k) or [] if isinstance(p, dict)}
    decided: dict[str, str] = {}
    if not isinstance(data, dict):
        return decided, [f"{DECISIONS} is not a mapping."]
    extra = sorted(mask_text(str(k))[:40] for k in data if k not in TOP_LEVEL_KEYS)
    if extra:
        problems.append(f"{DECISIONS} has keys the template does not define ({', '.join(extra)}); "
                        "only per-item decisions are recognized.")
    if data.get("case") != case_id:
        problems.append(f"{DECISIONS} names a different case than this result.")
    for section, known in (("hypotheses", set(statuses)), ("proposals", proposals)):
        entries = data.get(section)
        if entries is None:
            continue
        if not isinstance(entries, dict):
            problems.append(f"{DECISIONS}: '{section}' must be a mapping of item IDs.")
            continue
        for item, entry in entries.items():
            label = mask_text(str(item))[:40]
            if item not in known:
                problems.append(f"{DECISIONS} records '{label}', which is not a {section[:-1] if section == 'proposals' else 'hypothesis'} of this result.")
                continue
            if not isinstance(entry, dict):
                problems.append(f"{DECISIONS}: '{label}' must be a mapping.")
                continue
            before = len(problems)
            fields = sorted(mask_text(str(k))[:40] for k in entry if k not in ITEM_KEYS[section])
            if fields:
                problems.append(f"{DECISIONS}: '{label}' has fields the template does not define ({', '.join(fields)}).")
            decision = entry.get("decision")
            if decision is not None and decision not in DECISION_VALUES:
                problems.append(f"{DECISIONS}: '{label}' has a decision that is not one of {', '.join(DECISION_VALUES)}.")
            for name in ("decided_by_role", "reason"):
                text = entry.get(name)
                if text is not None and (not isinstance(text, str) or len(text) > MAX_TEXT):
                    problems.append(f"{DECISIONS}: '{label}' {name} must be plain text of at most {MAX_TEXT} "
                                    "characters, or null.")
            if section == "hypotheses" and entry.get("checked_status") != statuses[item]:
                problems.append(f"{DECISIONS}: '{label}' records a checked status that is not this result's "
                                f"({statuses[item]}).")
            if decision is not None and len(problems) == before:
                decided[str(item)] = decision
    return decided, problems
