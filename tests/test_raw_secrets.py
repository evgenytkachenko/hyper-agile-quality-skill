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
    assert clean == {"a": 1} and "outside the JSON object" in record["outside_object"] and not leaks(json.dumps(record))


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
    assert "password" not in record["answer"] and "config" not in record["answer"]       # outside the schema
    assert record["keys_not_kept"] == "4 key(s) outside the answer schema are not kept."
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
    assert not leaks(str(err.value)) and "activities: expected a list, got text" in str(err.value)
    # Text where a list is expected is the wrong shape: its whole content is omitted, including the digit-free
    # password that no pattern recognizes.
    kept = tree(tmp_path / "o")
    assert not leaks(kept) and "[OMITTED: expected a list, got text]" in kept


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


# ------------------------------------------------------------------ alternate key casing and nested structures

CASINGS = ["PASSWORD", "Password", "DB_PASSWORD", "dbPassword", "db.password", "db-password", "ApiKey", "API-KEY",
           "apiKey", "api.key", "api key", "OAuth", "OAUTH_TOKEN", "oauthToken", "AuthHeader", "AUTH_HEADER",
           "auth-header", "authHeader", "auth.header", "X-Auth", "x.auth", "Auth", "SessionId", "session.id",
           "ConnectionString", "connection.string", "DSN", "db.dsn", "clientSecret", "PrivateKey", "private.key",
           "http.authorization", "Set-Cookie", "PassPhrase"]


@pytest.mark.parametrize("key", CASINGS)
def test_alternate_casing_and_separators_are_sanitized(key):
    assert sanitize({key: "plain-value"}) == {key: "[REDACTED]"}


@pytest.mark.parametrize("key", ["author", "authority", "passage", "passed", "pass_rate", "bypass", "compass",
                                 "description", "session_summary", "Authored", "keyword"])
def test_ordinary_names_are_kept(key):
    assert sanitize({key: "plain-value"}) == {key: "plain-value"}


def test_nested_structures_at_every_depth():
    value = {"outer": [{"layer": {"items": [{"AuthHeader": "v1"}, ["x", {"db.password": {"deep": "v2"}}]],
                                  "ok": f"see {TOKEN}"}}],
             "list_of_lists": [[["Bearer " + TOKEN]]], "SESSION_ID": ["a", "b"], "keep": {"source": "s", "quote": "q"}}
    clean = sanitize(value)
    assert clean["outer"][0]["layer"]["items"][0] == {"AuthHeader": "[REDACTED]"}
    assert clean["outer"][0]["layer"]["items"][1][1] == {"db.password": "[REDACTED]"}
    assert TOKEN not in json.dumps(clean) and clean["SESSION_ID"] == "[REDACTED]"
    assert clean["keep"] == {"source": "s", "quote": "q"}



def test_nested_casing_variants_never_reach_any_output(tmp_path):
    secret = "plain-words-only-synthetic-value"
    extras = {"Config": {"AUTH_HEADER": secret, "nested": [{"oauthToken": secret}, {"Db.Password": [secret]}]},
              "auth.header": secret}
    responses = {k: json.dumps({**v, **extras}) for k, v in ANSWERS.items()}
    out = tmp_path / "out"
    inv = run_investigation(DEMO_CASE, scripted(tmp_path, responses), out_dir=out)
    write_outputs(inv, out)
    assert secret not in tree(out)
    record = json.loads((out / "raw" / "3-hypotheses.attempt-1.json").read_text())
    assert "Config" not in record["answer"] and "keys_not_kept" in record


def test_answer_schema_fields_survive_sanitizing(baseline):
    """Sanitizing must not destroy legitimate answer content: the demo's checked results equal the unsanitized answers'."""
    for key, answer in ANSWERS.items():
        assert sanitize(answer) == answer, key


# ------------------------------------------------------------------ keys outside the schema are not kept


def test_keys_outside_the_schema_are_dropped_at_every_depth(tmp_path):
    planted = "Hunter-2xyzzy-synthetic"
    answer = json.loads(json.dumps(ANSWERS["1-trace"]))
    answer["dbPass"] = planted
    answer["links"][0]["userPass"] = planted
    answer["links"][0]["jwt"] = planted
    answer["critical_signals"][1]["extra"] = {"connString": planted}
    responses = dict(ANSWERS, **{"1-trace": json.dumps(answer)})
    out = tmp_path / "out"
    inv = run_investigation(DEMO_CASE, scripted(tmp_path, responses), out_dir=out)
    write_outputs(inv, out)
    assert planted not in tree(out)
    record = json.loads((out / "raw" / "1-trace.attempt-1.json").read_text())
    assert record["keys_not_kept"] == "4 key(s) outside the answer schema are not kept."
    kept = record["answer"]
    assert kept["links"][0]["from_item"] == "SHOP-482" and "userPass" not in kept["links"][0]
    assert kept["production_problem"] == ANSWERS["1-trace"]["production_problem"]


def test_pruning_keeps_every_schema_field_of_the_demo_answers():
    from haq.prompts import STEPS
    from haq.sanitize import prune

    for step in STEPS:
        kept, dropped = prune(sanitize(ANSWERS[step.key]), step.output)
        assert dropped == 0 and kept == ANSWERS[step.key], step.key


# ------------------------------------------------------------------ fourth independent review


def test_engine_set_fields_are_never_kept_from_an_answer(tmp_path):
    """Free-form engine-set dicts could not be filtered by key, so engine-set fields are dropped from answers."""
    planted = "Hunter-" + "two-xyzzy-synthetic"
    r = json.loads(json.dumps(ANSWERS))
    r["2-validation"]["presented_test_inventory"] = {"dbPass": planted}                      # top-level dict field
    r["2-validation"]["regression_selection_gap"] = "SUPPORTED"                             # top-level str field
    r["2-validation"]["test_relevance"][0]["classification"] = "DETECTING " + planted       # nested model field
    r["1-trace"]["links"][0]["verified_support"] = planted                                   # nested model field
    r["3-hypotheses"]["hypotheses"][0]["quote_checks"] = [{"dbPass": planted}]               # list[dict] field
    r["3-hypotheses"]["what_worked"][0]["quote_checks"] = [{"dbPass": planted}]
    out = tmp_path / "out"
    inv = run_investigation(DEMO_CASE, scripted(tmp_path, r), out_dir=out)
    write_outputs(inv, out)
    assert planted not in tree(out)
    assert inv.validation.presented_test_inventory == {"status": "unknown", "reason": "No saved actual admission inventory."}
    assert inv.validation.regression_selection_gap == "UNCERTAIN"                            # derived, as before
    record = json.loads((out / "raw" / "2-validation.attempt-1.json").read_text())
    assert "presented_test_inventory" not in record["answer"] and record["keys_not_kept"].startswith("3 key(s)")


def test_valid_answers_give_the_same_checked_result_after_pruning(baseline):
    """The demo answers carry no engine-set fields; pruning must not change their checked outcome."""
    from haq.sanitize import prune
    from haq.prompts import STEPS

    for step in STEPS:
        assert prune(ANSWERS[step.key], step.output)[1] == 0
    assert {h.id: h.check_status for h in baseline.hypotheses.hypotheses}["H1"] == "SUPPORTED"
