"""Secret handling at every input and output boundary, with synthetic credential-shaped values only.

Policy under test: identifiers (paths, case/variant IDs, issue keys, link fields, release versions) that look like
credentials are refused, because masking them would leave ambiguous citations; free text (titles, descriptions,
comments, notes, test messages, answers) is masked. No output file, prompt, message or log may hold the value.
"""

import json
import os
import shutil
import subprocess
import sys

import pytest
from conftest import ROOT, bind_answer, secret_token

from haq._engine.errors import EvidenceError, PassOutputError
from haq.adapters import load_evidence
from haq.cli import DEMO_CASE, DEMO_RESPONSES
from haq.investigate import run_investigation, write_outputs
from haq.providers import AwaitingAnswer, ExchangeProvider, ScriptedProvider

TOKEN = secret_token()
ANSWERS = json.loads(DEMO_RESPONSES.read_text(encoding="utf-8"))["responses"]


def case_copy(tmp_path):
    case = tmp_path / "case"
    shutil.copytree(DEMO_CASE, case)
    return case


def edit(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def all_text(folder):
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in folder.rglob("*") if p.is_file())


# ------------------------------------------------------------------ identifiers are refused


IDENTIFIER_CASES = {
    "case id": lambda c: edit(c / "case.yaml", "id: checkout-promo", f"id: case-{TOKEN}"),
    "incident key": lambda c: edit(c / "case.yaml", "incident: SHOP-482", f"incident: {TOKEN}"),
    "issue key": lambda c: edit(c / "issues/SHOP-455.yaml", "key: SHOP-455", f"key: {TOKEN}"),
    "issue link target": lambda c: edit(c / "issues/SHOP-482.yaml", "target: SHOP-455", f"target: {TOKEN}"),
    "issue link relation": lambda c: edit(c / "issues/SHOP-482.yaml", "relation: is caused by", f"relation: {TOKEN}"),
    "release version": lambda c: edit(c / "releases/4.2.0.yaml", "version: 4.2.0", f"version: {TOKEN}"),
    "file path": lambda c: (c / "tests.md").rename(c / f"tests-{TOKEN}.md"),
    "file path (issue file)": lambda c: (c / "issues/SHOP-455.yaml").rename(c / f"issues/{TOKEN}.yaml"),
    "file path (JUnit file)": lambda c: (c / "test-results/ci-unit.xml").rename(c / f"test-results/{TOKEN}.xml"),
}


@pytest.mark.parametrize("kind", IDENTIFIER_CASES)
def test_credential_bearing_identifiers_are_refused_without_echoing_them(tmp_path, kind):
    case = case_copy(tmp_path)
    IDENTIFIER_CASES[kind](case)
    with pytest.raises(EvidenceError) as err:
        load_evidence(case)
    assert TOKEN not in str(err.value) and "[REDACTED]" in str(err.value)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    for cmd in (["check-case", str(case)], ["investigate", str(case), "--out", str(tmp_path / "o"), "--scripted",
                                              str(DEMO_RESPONSES)]):
        r = subprocess.run([sys.executable, "-m", "haq", *cmd], capture_output=True, text=True, env=env, timeout=120)
        assert r.returncode == 2 and TOKEN not in r.stdout + r.stderr


def test_variant_name_with_credential_is_refused(tmp_path):
    variant = tmp_path / f"v-{TOKEN}"
    variant.mkdir()
    (variant / "variant.yaml").write_text("remove: []\n")
    with pytest.raises(EvidenceError) as err:
        load_evidence(DEMO_CASE, variant)
    assert TOKEN not in str(err.value)


def test_missing_folder_message_is_masked(tmp_path):
    with pytest.raises(EvidenceError) as err:
        load_evidence(tmp_path / f"token={TOKEN}")
    assert TOKEN not in str(err.value)


# ------------------------------------------------------------------ free text is masked everywhere


def secret_case(tmp_path):
    case = case_copy(tmp_path)
    edit(case / "case.yaml", "title: Promo discount", f"title: Promo {TOKEN} discount")
    edit(case / "issues/SHOP-482.yaml", "title: Promo discount applied twice", f"title: Promo {TOKEN} applied twice")
    edit(case / "issues/SHOP-482.yaml", "title: Apply promo codes on the cart page", f"title: Apply {TOKEN}")
    edit(case / "issues/SHOP-482.yaml", "body: Reconciliation lists", f"body: token {TOKEN} Reconciliation lists")
    edit(case / "releases/4.2.0.yaml", "    Promo codes on the cart page verified", f"    {TOKEN} Promo codes on the cart page verified")
    edit(case / "test-results/ci-unit.xml", 'name="test_promo_rejects_expired" time="0.009"/>',
         f'name="test_promo_rejects_expired" time="0.009"><failure message="auth {TOKEN}"/></testcase>')
    (case / "ci.md").write_text(f"# CI log\nexport GITHUB_TOKEN={TOKEN}\n", encoding="utf-8")
    return case


def secret_answers(tmp_path):
    data = json.loads(json.dumps(ANSWERS))
    data["1-trace"]["production_problem"] += f" Leaked {TOKEN}."
    data["3-hypotheses"]["hypotheses"][0]["statement"] += f" ({TOKEN})"
    data["3-hypotheses"]["unknowns"].append(f"Whether {TOKEN} was rotated.")
    path = tmp_path / "answers.json"
    path.write_text(json.dumps({"description": "test", "responses": data}), encoding="utf-8")
    return path


def test_free_text_and_answers_are_masked_in_every_output(tmp_path):
    case, out = secret_case(tmp_path), tmp_path / "out"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    r = subprocess.run([sys.executable, "-m", "haq", "investigate", str(case), "--out", str(out),
                        "--scripted", str(secret_answers(tmp_path))], capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stderr
    assert TOKEN not in r.stdout + r.stderr
    written = all_text(out)
    assert {"report.md", "results.json", "checks.json", "run.json", "decisions.yaml"} <= {p.name for p in out.iterdir()}
    assert list((out / "raw").glob("*.attempt-*.json"))
    assert TOKEN not in written and "[REDACTED]" in written
    r = subprocess.run([sys.executable, "-m", "haq", "check-case", str(case)], capture_output=True, text=True,
                       env=env, timeout=120)
    assert r.returncode == 0 and TOKEN not in r.stdout + r.stderr and "masked" in r.stdout


def test_prompts_never_hold_the_value(tmp_path):
    folder = tmp_path / "x"
    with pytest.raises(AwaitingAnswer) as err:
        run_investigation(secret_case(tmp_path), ExchangeProvider(folder))
    assert TOKEN not in str(err.value)
    assert TOKEN not in all_text(folder)


def test_exchange_answer_text_is_masked(tmp_path):
    folder, out = tmp_path / "x", tmp_path / "out"
    answers = json.loads(secret_answers(tmp_path).read_text())["responses"]
    for key in answers:
        with pytest.raises(AwaitingAnswer):
            run_investigation(DEMO_CASE, ExchangeProvider(folder), out_dir=out)
        bind_answer(folder, key, answers[key])
    inv = run_investigation(DEMO_CASE, ExchangeProvider(folder), out_dir=out)
    write_outputs(inv, out)
    assert TOKEN not in all_text(out)


def test_rejected_answer_messages_and_attempts_are_masked(tmp_path):
    data = json.loads(json.dumps(ANSWERS))
    data["2-validation"] = {"activities": f"not a list {TOKEN}"}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"responses": data}), encoding="utf-8")
    out = tmp_path / "out"
    with pytest.raises(PassOutputError) as err:
        run_investigation(DEMO_CASE, ScriptedProvider(path), out_dir=out)
    assert TOKEN not in str(err.value)
    assert (out / "raw" / "2-validation.attempt-1.json").is_file() and TOKEN not in all_text(out)


# ------------------------------------------------------------------ independent review findings


def test_malformed_variant_manifest_leaks_nothing(tmp_path):
    variant = tmp_path / "v"
    variant.mkdir()
    (variant / "variant.yaml").write_text(f'remove: ["{TOKEN}\n', encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    r = subprocess.run([sys.executable, "-m", "haq", "check-case", str(DEMO_CASE), "--variant", str(variant)],
                       capture_output=True, text=True, env=env, timeout=120)
    out = r.stdout + r.stderr
    assert r.returncode == 2 and "not readable YAML" in out and "Traceback" not in out
    assert TOKEN[:12] not in out


def test_unexpected_errors_print_no_message_or_traceback(monkeypatch, capsys):
    from haq import cli

    def boom(args):
        raise RuntimeError(f"evidence line with {TOKEN}")
    monkeypatch.delenv("HAQ_DEBUG", raising=False)
    monkeypatch.setattr(cli, "cmd_doctor", boom)
    assert cli.main(["doctor"]) == 1
    err = capsys.readouterr().err
    assert "unexpected RuntimeError" in err and TOKEN[:8] not in err


def test_stale_binding_message_never_echoes_a_non_digest(tmp_path):
    from haq.providers import StaleAnswer

    folder = tmp_path / "x"
    folder.mkdir()
    (folder / "1-trace.answer.json").write_text(json.dumps({"binding": TOKEN, "answer": {}}), encoding="utf-8")
    with pytest.raises(StaleAnswer) as err:
        run_investigation(DEMO_CASE, ExchangeProvider(folder))
    assert TOKEN[:12] not in str(err.value) and "(not a digest)" in str(err.value)
