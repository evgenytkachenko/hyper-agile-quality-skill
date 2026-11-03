"""Answers are decoded and sanitized before any attempt record, repair prompt, error or output can show them.

All secrets are synthetic and built at runtime. Model traffic is MOCKED; no model is run.
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
from haq.providers import ScriptedProvider, make_ollama
from haq.sanitize import intake, sanitize

TOKEN = secret_token()
PASSWORD = "correct-horse-battery-staple-synthetic"      # no digits: text patterns alone miss it
DB_PASSWORD = "another-synthetic-db-value"
ESCAPED = "".join(f"\\u{ord(c):04x}" for c in TOKEN[:4]) + TOKEN[4:]   # JSON escapes hide the token's prefix
SECRETS = (TOKEN, TOKEN[4:], PASSWORD, DB_PASSWORD)
ANSWERS = json.loads(DEMO_RESPONSES.read_text(encoding="utf-8"))["responses"]


def leaks(text: str) -> list[str]:
    return [s for s in SECRETS if s in text]


def tree(folder) -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in folder.rglob("*") if p.is_file())


def with_extras(answer: dict) -> str:
    """The answer as raw JSON text, with secrets in extra keys, nested structures and escaped strings."""
    text = json.dumps(answer)[:-1]
    return (text + f', "password": "{PASSWORD}", "config": {{"db_password": "{DB_PASSWORD}", '
            f'"items": [{{"api_key": ["{PASSWORD}"]}}, "{ESCAPED}"]}}, "{ESCAPED}": 1, "session_token": 42}}')


def scripted(tmp_path, responses):
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"responses": responses}), encoding="utf-8")
    return ScriptedProvider(path)


# ------------------------------------------------------------------ the sanitizer itself


def test_escaped_token_is_decoded_then_masked():
    clean, record = intake('{"note": "' + ESCAPED + '"}')
    assert clean == {"note": "[REDACTED]"} and not leaks(json.dumps(record))


def test_sensitive_keys_compound_names_nested_and_non_string_values():
    clean = sanitize({"password": PASSWORD, "outer": {"db_password": DB_PASSWORD, "x_api_key": [PASSWORD],
                                                      "session_token": 42, "list": [{"secret": {"a": 1}}]},
                      "source": "kept", "quote": "kept too"})
    assert clean == {"password": "[REDACTED]", "outer": {"db_password": "[REDACTED]", "x_api_key": "[REDACTED]",
                                                         "session_token": "[REDACTED]", "list": [{"secret": "[REDACTED]"}]},
                     "source": "kept", "quote": "kept too"}


def test_credential_shaped_key_is_masked():
    clean, _ = intake('{"' + ESCAPED + '": 1}')
    assert list(clean) == ["[REDACTED]"]


def test_text_outside_the_object_is_dropped_and_counted():
    raw = f"<think>the password is {PASSWORD}</think> Sure! token {TOKEN}\n```json\n{{\"a\": 1}}\n```"
    clean, record = intake(raw)
    assert clean == {"a": 1} and "outside the JSON object" in record["omitted"] and not leaks(json.dumps(record))


@pytest.mark.parametrize("raw", [
    '{"production_problem": "' + TOKEN,                       # truncated mid-string
    '{"password": "' + PASSWORD + '", "x": }',                  # malformed
    'I could not answer. password=' + PASSWORD,                 # no JSON at all
    '{"a": "' + ESCAPED + '"',                                  # truncated, escaped token
    '["' + TOKEN + '"]',                                        # valid JSON but not an object
])
def test_unparseable_answers_keep_no_content(raw):
    clean, record = intake(raw)
    assert clean is None and record["status"] == "unparseable" and record["characters_received"] == len(raw)
    assert not leaks(json.dumps(record)) and "answer" not in record


# ------------------------------------------------------------------ every output of a run


def test_secret_extras_never_reach_attempts_results_report_or_messages(tmp_path):
    responses = {k: with_extras(v) for k, v in ANSWERS.items()}
    out = tmp_path / "out"
    inv = run_investigation(DEMO_CASE, scripted(tmp_path, responses), out_dir=out)
    write_outputs(inv, out)
    written = tree(out)
    assert not leaks(written) and ESCAPED not in written
    record = json.loads((out / "raw" / "1-trace.attempt-1.json").read_text())
    assert record["answer"]["password"] == "[REDACTED]" and record["answer"]["config"]["db_password"] == "[REDACTED]"
    assert record["answer"]["production_problem"] == ANSWERS["1-trace"]["production_problem"]  # diagnostics kept


def test_cli_output_and_errors_hold_no_secret(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    good = {k: with_extras(v) for k, v in ANSWERS.items()}
    bad = dict(good, **{"2-validation": '{"activities": "' + ESCAPED + '", "password": "' + PASSWORD + '"}'})
    for responses, code in ((good, 0), (bad, 2)):
        path = tmp_path / f"r{code}.json"
        path.write_text(json.dumps({"responses": responses}), encoding="utf-8")
        out = tmp_path / f"out{code}"
        r = subprocess.run([sys.executable, "-m", "haq", "investigate", str(DEMO_CASE), "--out", str(out),
                            "--scripted", str(path)], capture_output=True, text=True, env=env, timeout=120)
        assert r.returncode == code, r.stderr
        assert not leaks(r.stdout + r.stderr + tree(out))


def test_validation_error_message_has_no_input(tmp_path):
    responses = dict(ANSWERS, **{"2-validation": json.dumps({"activities": PASSWORD + " " + TOKEN})})
    with pytest.raises(PassOutputError) as err:
        run_investigation(DEMO_CASE, scripted(tmp_path, responses), out_dir=tmp_path / "o")
    assert not leaks(str(err.value)) and "activities" in str(err.value)
    # The attempt keeps the sanitized answer: the token is masked; a digit-free password written as ordinary text
    # under an ordinary field is not recognizable and stays (documented limitation), but is never echoed in errors.
    kept = tree(tmp_path / "o")
    assert TOKEN not in kept and "[REDACTED]" in kept


def test_truncated_saved_answer_is_reported_without_content(tmp_path):
    responses = dict(ANSWERS, **{"1-trace": '{"production_problem": "' + TOKEN + ' and the pass'})
    with pytest.raises(PassOutputError, match="could not be parsed") as err:
        run_investigation(DEMO_CASE, scripted(tmp_path, responses), out_dir=tmp_path / "o")
    assert not leaks(str(err.value)) and not leaks(tree(tmp_path / "o"))


def test_repair_prompts_and_attempts_from_a_model_hold_no_secret(tmp_path):
    """Mocked Ollama: an unparseable answer, then one failing validation with secrets, then valid answers."""
    contents = ['{"production_problem": "' + ESCAPED + ' cut off', json.dumps(ANSWERS["1-trace"]),
                with_extras(ANSWERS["2-validation"]).replace('"confidence": "STRONGLY SUPPORTED"',
                                                              f'"confidence": "{TOKEN}"', 1),
                with_extras(ANSWERS["2-validation"]), json.dumps(ANSWERS["3-hypotheses"])]
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": contents[len(seen) - 1]}, "done_reason": "stop"})
    out = tmp_path / "out"
    provider = make_ollama("http://localhost:11434", "fictional-model", transport=httpx.MockTransport(handler))
    inv = run_investigation(DEMO_CASE, provider, out_dir=out)
    write_outputs(inv, out)
    assert len(seen) == 5
    repairs = [m["messages"][1]["content"] for m in (seen[1], seen[3])]
    assert all("could not be used" in r for r in repairs)
    assert not leaks("\n".join(repairs)) and ESCAPED not in "\n".join(repairs)
    assert not leaks(tree(out))
    assert json.loads((out / "raw" / "1-trace.attempt-1.json").read_text())["status"] == "unparseable"


# ------------------------------------------------------------------ second independent review


@pytest.mark.parametrize("key", ["password_hash", "passwordConfirm", "pass", "auth", "x-auth", "auth_header",
                                 "connection_string", "dsn", "sessid", "db_password", "Authorization",
                                 "authHeader", "oauth"])
def test_more_credential_key_names_are_sanitized(key):
    assert sanitize({key: "some-plain-value"}) == {key: "[REDACTED]"}


def test_no_answer_schema_field_is_treated_as_sensitive():
    from haq.prompts import STEPS
    from haq.sanitize import SENSITIVE_KEY

    def fields(model, seen=set()):
        for name, f in model.model_fields.items():
            yield name
            for arg in (getattr(f.annotation, "__args__", None) or (f.annotation,)):
                if isinstance(arg, type) and hasattr(arg, "model_fields") and arg not in seen:
                    seen.add(arg)
                    yield from fields(arg, seen)
    names = {n for step in STEPS for n in fields(step.output)}
    assert len(names) > 40 and [n for n in names if SENSITIVE_KEY.search(n)] == []
    assert [k for k in ("bypass", "compass", "max_items") if SENSITIVE_KEY.search(k)] == []


@pytest.mark.parametrize("raw,reason", [
    ('{"a": ' + "[" * 5000 + "]" * 5000 + "}", "nested too deeply"),
    ('{"a": "\\ud800 ' + TOKEN + '"}', "unpaired surrogate"),
])
def test_pathological_answers_are_recorded_not_crashing(tmp_path, raw, reason):
    clean, record = intake(raw)
    assert clean is None and reason in record["reason"] and not leaks(json.dumps(record))
    responses = dict(ANSWERS, **{"1-trace": raw})
    with pytest.raises(PassOutputError, match=reason):
        run_investigation(DEMO_CASE, scripted(tmp_path, responses), out_dir=tmp_path / "o")
    kept = json.loads((tmp_path / "o" / "raw" / "1-trace.attempt-1.json").read_text())
    assert kept["status"] == "unparseable" and not leaks(tree(tmp_path / "o"))
