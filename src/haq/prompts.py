"""Prompts for the three investigation steps.

Steps 1 and 2 are the engine's own pass definitions (``passes.PASSES``: traceability, and
validation/release evidence): their task text, methodology excerpts, evidence categories and
output schemas are used unchanged. The preamble below follows the engine's per-pass rules.
Step 3 (hypotheses) is defined in ``hypotheses.py``.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from ._engine.evidence import CATEGORIES, EvidenceBundle
from ._engine.methodology import Methodology
from ._engine.passes import PASSES, PassSpec, model_schema, pass_schema, pass_task
from .hypotheses import TASK as HYPOTHESIS_TASK
from .hypotheses import QualityInvestigation

SYSTEM_PREAMBLE = """\
You are a quality engineering analyst performing one focused step of a Hyper-Agile \
investigation of an escaped defect.

Rules for every step:
- Work only from the evidence artifacts and earlier checked results in this prompt. You have \
no tools and cannot look anything up.
- Never invent evidence, identifiers, dates, people, or events. When the evidence does not \
say, answer UNKNOWN and name what is missing.
- Cite evidence by its ID exactly as written in brackets in the evidence index (for example \
[issue:SHOP-482]), with the identifiers it contains, for every claim that matters. Never build a \
file name or an ID from another one: a citation that names no collected artifact is not evidence.
- Apply the methodology excerpts below as written. They were written for a wider workflow \
that gathers evidence with tools; here the evidence has already been collected, so treat a \
category with no artifact as an evidence limitation.
- Artifacts in the category remediation_changes describe work done after the defect was \
reported, to fix it. Treat them as post-release learning only.
- Your answer is a hypothesis for human review. Code will check every citation and quote.
- Do only the task for this step."""


class StepSpec:
    def __init__(self, key: str, title: str, output: type[BaseModel], engine_pass: PassSpec | None,
                 methodology: tuple, evidence: tuple[str, ...], prior: tuple[str, ...]):
        self.key, self.title, self.output, self.engine_pass = key, title, output, engine_pass
        self.methodology, self.evidence, self.prior = methodology, evidence, prior


def _engine_pass(key: str) -> PassSpec:
    return next(p for p in PASSES if p.key == key)


TRACE = _engine_pass("1-traceability")
VALIDATE = _engine_pass("3-validation-release")

STEPS: tuple[StepSpec, ...] = (
    StepSpec("1-trace", TRACE.title, TRACE.output, TRACE, TRACE.methodology, TRACE.evidence, ()),
    StepSpec("2-validation", VALIDATE.title, VALIDATE.output, VALIDATE, VALIDATE.methodology, VALIDATE.evidence,
             ("1-trace",)),
    StepSpec("3-hypotheses", "Hypotheses, unknowns and proposals", QualityInvestigation, None,
             (("causal-model", "Causal layers"), ("causal-model", "Root-cause quality check"),
              ("causal-model", "Earliest reasonable missed opportunity"), ("quality-loop", None),
              ("evidence-and-actions", "Evidence confidence levels"), ("evidence-and-actions", "Action generation"),
              ("evidence-and-actions", "Always identify what worked")),
             CATEGORIES, ("1-trace", "2-validation")),
)


def schema(step: StepSpec, methodology: Methodology) -> dict:
    return pass_schema(step.engine_pass, methodology) if step.engine_pass else model_schema(step.output)


def system_prompt(step: StepSpec, methodology: Methodology) -> str:
    excerpts = []
    for doc, section in step.methodology:
        path = methodology.docs[doc].relative_path
        excerpts.append(f"<!-- from {path}{' — ' + section if section else ''} -->\n{methodology.text(doc, section)}")
    return SYSTEM_PREAMBLE + "\n\n# Methodology excerpts\n\n" + "\n\n".join(excerpts)


def user_prompt(step: StepSpec, methodology: Methodology, bundle: EvidenceBundle, results: dict[str, BaseModel],
                case_title: str) -> str:
    task = pass_task(step.engine_pass, methodology) if step.engine_pass else HYPOTHESIS_TASK
    index = "\n".join(f"- [{a.ref}] {a.category}" for a in bundle.artifacts())
    limitations = "\n".join(f"- {l}" for l in bundle.limitations) or "- none recorded"
    prior = "\n\n".join(
        f"## Checked result of step {key}\n```json\n{results[key].model_dump_json(indent=1)}\n```"
        for key in step.prior if key in results) or "(none)"
    return (f"# Task — {step.title}\n\n{task}\n\n# Case\n\nCase id: {bundle.case_id}\n"
            + (f"Title: {case_title}\n" if case_title else "")
            + f"\nEvidence index (cite evidence by the ID in brackets):\n{index}\n\nEvidence limitations:\n{limitations}\n\n"
            f"# Earlier checked results\n\n{prior}\n\n# Evidence for this step\n\n{bundle.render(step.evidence)}\n\n"
            "# Output format\n\nRespond with one JSON object that matches this JSON Schema. No prose and no code fences.\n\n"
            + json.dumps(schema(step, methodology), indent=1))


def approx_tokens(text: str) -> int:
    return len(text) // 4 + 1
