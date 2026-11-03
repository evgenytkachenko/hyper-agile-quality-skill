"""Answers are validated before classification; evidence identities must be unambiguous; failed answers are kept.

The bypass these tests close: before this fix, a hypothesis with confidence "HIGH" (not a methodology level) and a
verified quote was classified SUPPORTED, duplicate IDs silently collapsed, and repeated basenames or issue keys
let one citation stand for two files.
"""

import json
import shutil

import httpx
import pytest
from conftest import secret_token

from haq._engine.errors import EvidenceError, PassOutputError
from haq._engine.methodology import Methodology
from haq.adapters import load_evidence
from haq.cli import DEMO_CASE, DEMO_RESPONSES
from haq.hypotheses import Hypothesis, QualityInvestigation, Quote, check_investigation
from haq.investigate import METHODOLOGY_DIR, run_investigation
from haq.prompts import STEPS
from haq.providers import ScriptedProvider, make_ollama

ANSWERS = json.loads(DEMO_RESPONSES.read_text(encoding="utf-8"))["responses"]
METHODOLOGY = Methodology.load(METHODOLOGY_DIR)
LEVELS = METHODOLOGY.confidence_levels()


def scripted(tmp_path, mutate):
    data = json.loads(json.dumps(ANSWERS))
    mutate(data)
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"responses": data}), encoding="utf-8")
    return ScriptedProvider(path)


def hypothesis(confidence, hid="H1"):
    return Hypothesis(id=hid, statement="The discount is computed after other discounts.", layer="Defect introduction",
                      loop_activity="Analyze change impact", confidence=confidence,
                      supporting=[Quote(source="code-change.md", quote="total after discounts already applied")],
                      contradicting=[], what_would_settle_it="-")


def check(*hs):
    inv = QualityInvestigation(hypotheses=list(hs), unknowns=[], what_worked=[], proposed_regression_tests=[],
                               proposed_controls=[])
    check_investigation(inv, load_evidence(DEMO_CASE).bundle, LEVELS, METHODOLOGY.loop_activities(), None, None)
    return inv


# ------------------------------------------------------------------ confidence vocabulary


@pytest.mark.parametrize("bad", ["HIGH", "confirmed-ish", "", "PROBABLE"])
def test_unknown_confidence_is_rejected_not_classified(bad):
    with pytest.raises(PassOutputError, match="is not one of"):
        check(hypothesis(bad))


def test_valid_levels_still_classify_and_are_canonicalized():
    inv = check(hypothesis("strongly  supported"))
    assert inv.hypotheses[0].confidence == "STRONGLY SUPPORTED" and inv.hypotheses[0].check_status == "SUPPORTED"
    assert check(hypothesis("UNKNOWN")).hypotheses[0].check_status == "NOT ESTABLISHED"


def test_unknown_confidence_in_a_full_run_is_rejected(tmp_path):
    def mutate(d):
        d["3-hypotheses"]["hypotheses"][0]["confidence"] = "HIGH"
    with pytest.raises(PassOutputError, match="'HIGH' is not one of"):
        run_investigation(DEMO_CASE, scripted(tmp_path, mutate))


@pytest.mark.parametrize("step,path,bad", [
    ("1-trace", ("links", 0, "confidence"), "VERY HIGH"),
    ("1-trace", ("critical_signals", 1, "confidence"), "LIKELY"),
    ("2-validation", ("test_relevance", 0, "confidence"), "HIGH"),
    ("2-validation", ("activities", 0, "status"), "DONE"),
])
def test_engine_step_vocabulary_is_rejected(tmp_path, step, path, bad):
    def mutate(d):
        node = d[step]
        for part in path[:-1]:
            node = node[part]
        node[path[-1]] = bad
    with pytest.raises(PassOutputError, match="is not one of"):
        run_investigation(DEMO_CASE, scripted(tmp_path, mutate))


def test_activity_may_be_not_applicable(tmp_path):
    def mutate(d):
        d["2-validation"]["activities"][4]["status"] = "NOT APPLICABLE"
    run_investigation(DEMO_CASE, scripted(tmp_path, mutate))


def test_model_with_invalid_confidence_gets_a_repair_attempt(tmp_path):
    bad = json.loads(json.dumps(ANSWERS["3-hypotheses"]))
    bad["hypotheses"][0]["confidence"] = "HIGH"
    contents = [json.dumps(ANSWERS["1-trace"]), json.dumps(ANSWERS["2-validation"]), json.dumps(bad),
                json.dumps(ANSWERS["3-hypotheses"])]
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": contents[len(seen) - 1]}, "done_reason": "stop"})
    out = tmp_path / "out"
    provider = make_ollama("http://localhost:11434", "fictional-model", transport=httpx.MockTransport(handler))
    inv = run_investigation(DEMO_CASE, provider, out_dir=out)
    assert len(seen) == 4 and "'HIGH' is not one of" in seen[3]["messages"][1]["content"]
    assert inv.hypotheses.hypotheses[0].confidence == "STRONGLY SUPPORTED"
    assert sorted(p.name for p in (out / "raw").iterdir()) == [
        "1-trace.attempt-1.txt", "2-validation.attempt-1.txt", "3-hypotheses.attempt-1.txt", "3-hypotheses.attempt-2.txt"]


# ------------------------------------------------------------------ duplicate IDs


def test_duplicate_hypothesis_ids_are_rejected():
    with pytest.raises(PassOutputError, match="hypothesis ID 'H1' is used 2 times"):
        check(hypothesis("UNKNOWN"), hypothesis("STRONGLY SUPPORTED"))


@pytest.mark.parametrize("mutate,message", [
    (lambda d: d["3-hypotheses"]["proposed_controls"][0].update(id="T1"), "proposal ID 'T1' is used 2 times"),
    (lambda d: d["3-hypotheses"]["proposed_regression_tests"][1].update(id="T1"), "proposal ID 'T1' is used 2 times"),
    (lambda d: d["3-hypotheses"]["proposed_controls"][0].update(id="H1"), "both a hypothesis and a proposal"),
    (lambda d: d["3-hypotheses"]["hypotheses"][1].update(id=" "), "must be a letter followed by"),
    (lambda d: d["3-hypotheses"]["hypotheses"][1].update(id='"H1"'), "must be a letter followed by"),
    (lambda d: d["3-hypotheses"]["hypotheses"][1].update(id="H1 #dup"), "must be a letter followed by"),
    (lambda d: d["3-hypotheses"]["hypotheses"][1].update(id="h1"), "hypothesis ID 'H1' is used 2 times"),
])
def test_duplicate_or_empty_ids_are_rejected(tmp_path, mutate, message):
    with pytest.raises(PassOutputError, match=message):
        run_investigation(DEMO_CASE, scripted(tmp_path, mutate))


# ------------------------------------------------------------------ ambiguous evidence identities


def copy(tmp_path):
    case = tmp_path / "case"
    shutil.copytree(DEMO_CASE, case)
    return case


def test_repeated_basename_is_rejected(tmp_path):
    case = copy(tmp_path)
    (case / "notes").mkdir()
    (case / "notes" / "tests.md").write_text("# Other tests\n- TC-999")
    with pytest.raises(EvidenceError, match="'tests.md' names notes/tests.md, tests.md"):
        load_evidence(case)


def test_repeated_issue_key_is_rejected(tmp_path):
    case = copy(tmp_path)
    (case / "issues" / "OTHER.yaml").write_text("key: SHOP-455\ntitle: A second record of the same key\n")
    with pytest.raises(EvidenceError, match="'issue:shop-455' names"):
        load_evidence(case)


def test_issue_keys_differing_only_in_case_are_rejected(tmp_path):
    case = copy(tmp_path)
    (case / "issues" / "lower.yaml").write_text("key: shop-455\ntitle: lower case\n")
    with pytest.raises(EvidenceError, match="Ambiguous evidence identities"):
        load_evidence(case)


def test_same_basename_in_two_structured_folders_is_rejected(tmp_path):
    case = copy(tmp_path)
    (case / "releases" / "SHOP-455.yaml").write_text("version: 9.9.9\n")
    with pytest.raises(EvidenceError, match="'shop-455.yaml' names"):
        load_evidence(case)


def test_adapter_artifact_and_a_same_named_user_file_stay_distinct(tmp_path):
    from haq._engine.guards import cited_artifacts

    case = copy(tmp_path)
    (case / "recorded-relationships.md").write_text("# Not the adapter's file\n")
    bundle = load_evidence(case).bundle
    user = cited_artifacts("recorded-relationships.md", bundle)
    derived = cited_artifacts("adapter:relationships", bundle)
    assert [a.source_path for a in user] == ["recorded-relationships.md"]
    assert [a.source_path for a in derived] == ["derived:recorded-relationships.md"]


def test_unique_identities_still_load():
    refs = [a.ref for a in load_evidence(DEMO_CASE).bundle.artifacts()]
    assert len(refs) == len({r.lower() for r in refs}) == 10


# ------------------------------------------------------------------ failed answers are kept


def test_failed_saved_answer_is_kept_and_named(tmp_path):
    def mutate(d):
        d["2-validation"] = "not an object"
    out = tmp_path / "out"
    with pytest.raises(PassOutputError, match="Every attempt is kept under"):
        run_investigation(DEMO_CASE, scripted(tmp_path, mutate), out_dir=out)
    assert (out / "raw" / "2-validation.attempt-1.txt").read_text() == "not an object"


def test_model_failing_twice_keeps_both_attempts(tmp_path):
    contents = ["no json here", "still none"]
    seen = []

    def handler(request):
        seen.append(1)
        return httpx.Response(200, json={"message": {"content": contents[len(seen) - 1]}, "done_reason": "stop"})
    out = tmp_path / "out"
    provider = make_ollama("http://localhost:11434", "m", transport=httpx.MockTransport(handler))
    with pytest.raises(PassOutputError):
        run_investigation(DEMO_CASE, provider, out_dir=out)
    assert [(out / "raw" / f"1-trace.attempt-{n}.txt").read_text() for n in (1, 2)] == contents


def test_attempts_are_numbered_across_reruns(tmp_path):
    def mutate(d):
        d["1-trace"] = "bad"
    out = tmp_path / "out"
    for _ in range(2):
        with pytest.raises(PassOutputError):
            run_investigation(DEMO_CASE, scripted(tmp_path, mutate), out_dir=out)
    assert sorted(p.name for p in (out / "raw").iterdir()) == ["1-trace.attempt-1.txt", "1-trace.attempt-2.txt"]


def test_masking_does_not_break_a_valid_answer(tmp_path):
    token = secret_token()

    def mutate(d):
        d["1-trace"]["production_problem"] += f" key={token}"
    inv = run_investigation(DEMO_CASE, scripted(tmp_path, mutate))
    assert token not in inv.trace.production_problem and "[REDACTED]" in inv.trace.production_problem


# ------------------------------------------------------------------ independent review findings


def test_non_ascii_lookalike_identity_is_refused(tmp_path):
    """'ſ' (U+017F) matches 's' case-insensitively, so it could make one citation name two issues."""
    case = copy(tmp_path)
    (case / "issues" / "OTHER.yaml").write_text("key: ſHOP-482\ntitle: lookalike\n", encoding="utf-8")
    with pytest.raises(EvidenceError, match="non-ASCII"):
        load_evidence(case)


def test_decisions_file_stays_valid_yaml_for_any_accepted_case_id(tmp_path):
    import yaml

    from haq.investigate import write_outputs

    case = copy(tmp_path)
    (case / "case.yaml").write_text("id: 'odd: name #1'\ntitle: t\nincident: SHOP-482\n", encoding="utf-8")
    inv = run_investigation(case, ScriptedProvider(DEMO_RESPONSES))
    write_outputs(inv, tmp_path / "out")
    data = yaml.safe_load((tmp_path / "out" / "decisions.yaml").read_text())
    assert data["case"] == "odd: name #1" and len(data["hypotheses"]) == 7 and len(data["proposals"]) == 7
