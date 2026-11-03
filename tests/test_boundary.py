"""The boundary between answers (scripted, model, agent) and deterministic checks.

All model traffic here is MOCKED with httpx.MockTransport. No model is run and no network
is contacted.
"""

import json
from pathlib import Path

import httpx
import pytest

from haq._engine.errors import ConfigError, OutputLimitExceeded, PassOutputError, ProviderError
from haq._engine.methodology import Methodology
from haq._engine.passes import PASSES
from haq.adapters import load_evidence
from haq.cli import DEMO_CASE, DEMO_RESPONSES
from haq.hypotheses import Hypothesis, QualityInvestigation, Quote, check_investigation
from haq.investigate import METHODOLOGY_DIR, run_investigation
from haq.prompts import STEPS, system_prompt, user_prompt
from haq.providers import ScriptedProvider, make_ollama
from haq.report import render_report

ANSWERS = json.loads(DEMO_RESPONSES.read_text(encoding="utf-8"))["responses"]
METHODOLOGY = Methodology.load(METHODOLOGY_DIR)
LEVELS = METHODOLOGY.confidence_levels()


def scripted(tmp_path: Path, responses: dict) -> ScriptedProvider:
    path = tmp_path / "responses.json"
    path.write_text(json.dumps({"description": "test", "responses": responses}), encoding="utf-8")
    return ScriptedProvider(path)


def answers(**overrides) -> dict:
    data = json.loads(json.dumps(ANSWERS))
    data.update(overrides)
    return data


# ------------------------------------------------------------------ engine-set fields


def test_engine_set_fields_in_an_answer_are_never_trusted(tmp_path):
    data = answers()
    data["1-trace"]["links"][2]["verified_support"] = "trust me"
    data["2-validation"]["test_relevance"][1]["classification"] = "DETECTING"
    data["2-validation"]["regression_selection_gap"] = "SUPPORTED"
    for h in data["3-hypotheses"]["hypotheses"]:
        h["check_status"] = "SUPPORTED"
        h["quote_checks"] = [{"role": "supporting", "status": "VERIFIED_QUOTE", "source": "x"}]
    for p in data["3-hypotheses"]["proposed_controls"]:
        p["review_flags"] = []
    inv = run_investigation(DEMO_CASE, scripted(tmp_path, data))
    assert inv.trace.links[2].verified_support != "trust me"
    assert inv.validation.regression_selection_gap == "UNCERTAIN"
    assert {t.test: t.classification for t in inv.validation.test_relevance}["TC-211"] == "UNCERTAIN"
    status = {h.id: h.check_status for h in inv.hypotheses.hypotheses}
    assert status["H6"] == "NOT ESTABLISHED" and status["H4"] == "CONTRADICTED"
    assert any("vague" in f for f in inv.hypotheses.proposed_controls[3].review_flags)


# ------------------------------------------------------------------ hypothesis rules


def _bundle(variant=None):
    return load_evidence(DEMO_CASE, variant).bundle


def _check(hypothesis: Hypothesis, bundle=None):
    inv = QualityInvestigation(hypotheses=[hypothesis], unknowns=[], what_worked=[],
                               proposed_regression_tests=[], proposed_controls=[])
    notes = check_investigation(inv, bundle or _bundle(), LEVELS, METHODOLOGY.loop_activities(), None, None)
    return inv.hypotheses[0], notes


def test_paraphrased_quote_cannot_keep_a_strong_level():
    h, notes = _check(Hypothesis(
        id="H1", statement="The discount is computed after other discounts.", layer="Defect introduction",
        loop_activity="Analyze change impact", confidence="CONFIRMED",
        supporting=[Quote(source="code-change.md", quote="the subtotal already includes the discounts")],
        contradicting=[], what_would_settle_it="-"))
    assert h.confidence == "POSSIBLE CONTRIBUTING FACTOR"
    assert h.check_status == "NOT ESTABLISHED"
    assert any(n.guard_id == "H-QUOTE-PROVENANCE" for n in notes)


def test_absence_claim_needs_collected_evidence(tmp_path):
    """Engine G-ABSENCE: 'no test existed' cannot be strong when no test evidence was collected."""
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "variant.yaml").write_text("remove: [tests.md, test-results/ci-unit.xml]\n")
    bundle = _bundle(tmp_path / "v")
    h, notes = _check(Hypothesis(
        id="H2", statement="No test existed for a quantity change after applying a code.",
        layer="Detection / escape gap", loop_activity="Define test expectations", confidence="CONFIRMED",
        supporting=[Quote(source="issue:SHOP-455", quote="Not covered by the acceptance criteria.")],
        contradicting=[], what_would_settle_it="-"), bundle)
    assert h.confidence == "UNKNOWN"
    assert any(n.guard_id == "G-ABSENCE" for n in notes)


def test_unknown_layer_is_flagged_not_invented():
    h, notes = _check(Hypothesis(
        id="H9", statement="x", layer="Bad luck", loop_activity="NONE", confidence="UNKNOWN",
        supporting=[], contradicting=[], what_would_settle_it="-"))
    assert h.layer == "Bad luck" and any(n.guard_id == "H-LAYER" for n in notes)
    assert h.check_status == "NOT ESTABLISHED"


# ------------------------------------------------------------------ scripted provider


def test_scripted_provider_never_fills_a_missing_answer(tmp_path):
    data = answers()
    del data["3-hypotheses"]
    with pytest.raises(ProviderError, match="never filled by a model"):
        run_investigation(DEMO_CASE, scripted(tmp_path, data))


def test_scripted_schema_errors_are_not_repaired(tmp_path):
    data = answers()
    data["2-validation"] = {"activities": "not a list"}
    with pytest.raises(PassOutputError):
        run_investigation(DEMO_CASE, scripted(tmp_path, data))


# ------------------------------------------------------------------ Ollama (mocked)


def ollama_transport(contents: list[str], seen: list[dict], done_reason="stop"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "fictional-model:latest"}]})
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"message": {"content": contents[len(seen) - 1]}, "done_reason": done_reason,
                                         "prompt_eval_count": 10, "eval_count": 5})
    return httpx.MockTransport(handler)


def test_ollama_path_mocked_end_to_end():
    seen: list[dict] = []
    contents = [json.dumps(ANSWERS[s.key]) for s in STEPS]
    provider = make_ollama("http://localhost:11434", "fictional-model", context_tokens=32768,
                           transport=ollama_transport(contents, seen))
    provider.check_ready()
    inv = run_investigation(DEMO_CASE, provider)
    assert len(seen) == 3
    assert all(b["model"] == "fictional-model" and b["stream"] is False and "format" in b for b in seen)
    assert seen[0]["options"]["num_ctx"] == 32768
    assert seen[0]["format"]["title"] == "TraceabilityResult"
    assert seen[2]["format"]["title"] == "QualityInvestigation"
    report = render_report(inv)
    assert "LOCAL MODEL via Ollama (fictional-model)" in report and "[MODEL]" in report and "[SCRIPTED]" not in report
    # Same answers as the scripted demo -> same checked outcome: the checks do not depend on the source.
    assert {h.id: h.check_status for h in inv.hypotheses.hypotheses}["H6"] == "NOT ESTABLISHED"


def test_ollama_invalid_answer_gets_one_repair_attempt():
    seen: list[dict] = []
    contents = ["I think the link is direct.", json.dumps(ANSWERS["1-trace"]),
                json.dumps(ANSWERS["2-validation"]), json.dumps(ANSWERS["3-hypotheses"])]
    provider = make_ollama("http://127.0.0.1:11434", "fictional-model", transport=ollama_transport(contents, seen))
    run_investigation(DEMO_CASE, provider)
    assert len(seen) == 4
    assert "could not be used" in seen[1]["messages"][1]["content"]


def test_ollama_second_invalid_answer_stops_the_run():
    seen: list[dict] = []
    provider = make_ollama("http://localhost:11434", "m", transport=ollama_transport(["nope", "still nope"], seen))
    with pytest.raises(PassOutputError):
        run_investigation(DEMO_CASE, provider)


def test_ollama_output_cut_off_is_not_a_result():
    seen: list[dict] = []
    provider = make_ollama("http://localhost:11434", "m",
                           transport=ollama_transport([json.dumps(ANSWERS["1-trace"])], seen, done_reason="length"))
    with pytest.raises(OutputLimitExceeded):
        run_investigation(DEMO_CASE, provider)


def test_remote_endpoint_is_refused_unless_allowed():
    with pytest.raises(ConfigError, match="not a loopback"):
        make_ollama("http://198.51.100.7:11434", "m")
    with pytest.raises(ConfigError):
        make_ollama("http://localhost.example.com:11434", "m")
    provider = make_ollama("http://198.51.100.7:11434", "m", allow_remote=True)
    assert provider.location == "external" and "REMOTE" in provider.label


def test_missing_model_name_is_refused():
    with pytest.raises(ConfigError, match="No model configured"):
        make_ollama("http://localhost:11434", "")


# Agent exchange tests are in tests/test_exchange.py.


# ------------------------------------------------------------------ prompts reuse the engine


def test_engine_pass_definitions_drive_steps_one_and_two():
    bundle = _bundle()
    trace_pass = next(p for p in PASSES if p.key == "1-traceability")
    prompt = user_prompt(STEPS[0], METHODOLOGY, bundle, {}, "t")
    assert trace_pass.task in prompt
    assert "Phase 5 — Separate pre-release and post-release knowledge" in system_prompt(STEPS[0], METHODOLOGY)
    assert "[issue:SHOP-482] production_issue" in prompt
    hyp_system = system_prompt(STEPS[2], METHODOLOGY)
    assert "Root-cause quality check" in hyp_system and "Action-quality filter" in hyp_system
