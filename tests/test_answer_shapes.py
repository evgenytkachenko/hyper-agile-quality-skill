"""Answers are conformed to their schema's shape before anything is kept, echoed or used in a repair prompt.

Wrong-shaped values (an object or list where text is expected, a list of lists, text where an object is expected,
...) at any depth have their content omitted and make the answer fail; nothing from them reaches attempt records,
repair prompts, errors, logs or outputs, whatever their key names. All secrets are synthetic and built at runtime;
model traffic is MOCKED.
"""

import json
import os
import subprocess
import sys

import httpx
import pytest
from conftest import ROOT, secret_token

from haq._engine.errors import PassOutputError
from haq.cli import DEMO_CASE, DEMO_RESPONSES
from haq.investigate import run_investigation, write_outputs
from haq.prompts import STEPS
from haq.providers import ScriptedProvider, make_ollama
from haq.sanitize import conform, intake

PLANTED = "Hunter-" + "two-xyzzy-synthetic"          # matches no credential pattern: only shape handling stops it
TOKEN = secret_token()
SECRETS = (PLANTED, TOKEN, TOKEN[4:])
ANSWERS = json.loads(DEMO_RESPONSES.read_text(encoding="utf-8"))["responses"]
MODELS = {s.key: s.output for s in STEPS}

# (step, path, wrong value, expected problem). Key names are deliberately ordinary or abbreviated (dbPass, note).
CASES = [
    ("1-trace", ("production_problem",), {"dbPass": PLANTED}, "production_problem: expected text, got an object"),
    ("1-trace", ("production_problem",), [PLANTED], "production_problem: expected text, got a list"),
    ("1-trace", ("production_problem",), [[{"note": PLANTED}]], "production_problem: expected text, got a list"),
    ("1-trace", ("ambiguities",), {"dbPass": PLANTED}, "ambiguities: expected a list, got an object"),
    ("1-trace", ("ambiguities",), [[PLANTED]], "ambiguities[0]: expected text, got a list"),
    ("1-trace", ("ambiguities",), ["fine", {"note": PLANTED}], "ambiguities[1]: expected text, got an object"),
    ("1-trace", ("links",), {"dbPass": PLANTED}, "links: expected a list, got an object"),
    ("1-trace", ("links",), [PLANTED], "links[0]: expected an object, got text"),
    ("1-trace", ("links",), [[{"from_item": PLANTED}]], "links[0]: expected an object, got a list"),
    ("1-trace", ("links", 0, "basis"), {"dbPass": PLANTED}, "links[0].basis: expected text, got an object"),
    ("1-trace", ("links", 0, "basis"), [[[PLANTED]]], "links[0].basis: expected text, got a list"),
    ("2-validation", ("test_relevance", 1, "evidence"), [{"x": PLANTED}], "test_relevance[1].evidence[0]: expected text, got an object"),
    ("2-validation", ("activities", 0), PLANTED, "activities[0]: expected an object, got text"),
    ("3-hypotheses", ("hypotheses", 0, "supporting", 0, "quote"), [[{"dbPass": PLANTED}]],
     "hypotheses[0].supporting[0].quote: expected text, got a list"),
    ("3-hypotheses", ("hypotheses", 0, "supporting"), {"dbPass": PLANTED}, "hypotheses[0].supporting: expected a list, got an object"),
    ("3-hypotheses", ("proposed_controls", 0, "addresses"), [["H1", PLANTED]], "proposed_controls[0].addresses[0]: expected text, got a list"),
    ("3-hypotheses", ("unknowns",), "just text " + PLANTED, "unknowns: expected a list, got text"),
    ("3-hypotheses", ("hypotheses", 0, "confidence"), 0.9, "hypotheses[0].confidence: expected text, got a number"),
]


def planted(step, path, value):
    data = json.loads(json.dumps(ANSWERS))
    node = data[step]
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value
    return data


def leaks(text):
    return [s for s in SECRETS if s in text]


def tree(folder):
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in folder.rglob("*") if p.is_file())


def scripted(tmp_path, responses):
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"responses": responses}), encoding="utf-8")
    return ScriptedProvider(path)


def schema_names():
    names, seen = set(), set()

    def walk(model):
        if model in seen:
            return
        seen.add(model)
        for name, field in model.model_fields.items():
            names.add(name)
            for arg in (getattr(field.annotation, "__args__", None) or (field.annotation,)):
                if isinstance(arg, type) and hasattr(arg, "model_fields"):
                    walk(arg)
    for model in MODELS.values():
        walk(model)
    return names


def keys_in(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from keys_in(v)
    elif isinstance(value, list):
        for v in value:
            yield from keys_in(v)


# ------------------------------------------------------------------ the conformance itself


@pytest.mark.parametrize("step,path,value,problem", CASES)
def test_wrong_shape_content_is_omitted_and_reported(step, path, value, problem):
    raw = json.dumps(planted(step, path, value)[step])
    clean, record = intake(raw, MODELS[step])
    assert record["status"] == "wrong_shape" and problem in record["shape_problems"]
    assert not leaks(json.dumps(record))
    assert set(keys_in(record["answer"])) <= schema_names()        # no unknown key survives in any container


@pytest.mark.parametrize("step", MODELS)
def test_valid_answers_are_unchanged(step):
    kept, dropped, problems = conform(ANSWERS[step], MODELS[step])
    assert (kept, dropped, problems) == (ANSWERS[step], 0, [])


def test_problem_list_is_bounded_and_content_free():
    answer = dict(ANSWERS["1-trace"], ambiguities=[{"k": PLANTED}] * 500)
    _, record = intake(json.dumps(answer), MODELS["1-trace"])
    assert len(record["shape_problems"]) == 51 and not leaks(json.dumps(record))
    assert record["shape_problems"][-1] == "... and 450 more location(s) of the wrong shape"


def test_unknown_keys_inside_valid_containers_are_dropped_at_depth():
    answer = json.loads(json.dumps(ANSWERS["3-hypotheses"]))
    answer["hypotheses"][0]["supporting"][0]["dbPass"] = PLANTED
    answer["proposed_controls"][0]["extra"] = {"note": PLANTED}
    clean, record = intake(json.dumps(answer), MODELS["3-hypotheses"])
    assert record["status"] == "parsed" and clean is not None and not leaks(json.dumps(record))
    assert record["keys_not_kept"] == "2 key(s) outside the answer schema are not kept."


# ------------------------------------------------------------------ every channel of a run


@pytest.mark.parametrize("step,path,value,problem", CASES)
def test_saved_wrong_shape_answer_fails_without_trace_in_any_channel(tmp_path, step, path, value, problem):
    out = tmp_path / "o"
    with pytest.raises(PassOutputError, match="wrong shape") as err:
        run_investigation(DEMO_CASE, scripted(tmp_path, planted(step, path, value)), out_dir=out)
    assert problem in str(err.value) and not leaks(str(err.value))
    assert not leaks(tree(out))
    record = json.loads((out / "raw" / f"{step}.attempt-1.json").read_text())
    assert record["status"] == "wrong_shape" and set(keys_in(record["answer"])) <= schema_names()


def test_cli_stdout_stderr_and_outputs_hold_nothing(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"responses": planted("1-trace", ("production_problem",), {"dbPass": PLANTED})}))
    r = subprocess.run([sys.executable, "-m", "haq", "investigate", str(DEMO_CASE), "--out", str(tmp_path / "o"),
                        "--scripted", str(path)], capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 2 and "wrong shape" in r.stderr
    assert not leaks(r.stdout + r.stderr + tree(tmp_path / "o"))


def test_model_repair_prompt_names_locations_only_and_the_repaired_run_is_clean(tmp_path):
    bad = planted("2-validation", ("test_relevance", 0, "reasoning"), {"dbPass": PLANTED})["2-validation"]
    bad["missing_evidence"] = [[{"note": PLANTED}]]
    contents = [json.dumps(ANSWERS["1-trace"]), json.dumps(bad), json.dumps(ANSWERS["2-validation"]),
                json.dumps(ANSWERS["3-hypotheses"])]
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": contents[len(seen) - 1]}, "done_reason": "stop"})
    out = tmp_path / "out"
    provider = make_ollama("http://localhost:11434", "fictional-model", transport=httpx.MockTransport(handler))
    inv = run_investigation(DEMO_CASE, provider, out_dir=out)
    write_outputs(inv, out)
    repair = seen[2]["messages"][1]["content"]
    assert "test_relevance[0].reasoning: expected text, got an object" in repair
    assert "missing_evidence[0]: expected text, got a list" in repair
    assert not leaks(repair) and not leaks(tree(out))
    assert [json.loads((out / "raw" / f"2-validation.attempt-{n}.json").read_text())["status"] for n in (1, 2)] == \
           ["wrong_shape", "parsed"]


def test_valid_control_run_still_works(tmp_path):
    out = tmp_path / "o"
    inv = run_investigation(DEMO_CASE, ScriptedProvider(DEMO_RESPONSES), out_dir=out)
    write_outputs(inv, out)
    assert {h.id: h.check_status for h in inv.hypotheses.hypotheses}["H1"] == "SUPPORTED"
    for step in MODELS:
        assert json.loads((out / "raw" / f"{step}.attempt-1.json").read_text())["status"] == "parsed"
