"""Agent exchange: every saved answer is bound to its exact request and to earlier answers. No model is called."""

import json
import os
import subprocess
import sys

import pytest
from conftest import ROOT, bind_answer

from haq._engine.errors import PassOutputError
from haq.cli import DEMO_CASE, DEMO_RESPONSES, DEMO_VARIANTS
from haq.investigate import run_investigation
from haq.prompts import STEPS
from haq.providers import AwaitingAnswer, ExchangeProvider, StaleAnswer
from haq.report import render_report

ANSWERS = json.loads(DEMO_RESPONSES.read_text(encoding="utf-8"))["responses"]
KEYS = [s.key for s in STEPS]


def answer_all(folder, variant=None, answers=ANSWERS):
    """Answer step by step, the way an agent would: run, read the prompt, answer, run again."""
    for key in KEYS:
        with pytest.raises(AwaitingAnswer):
            run_investigation(DEMO_CASE, ExchangeProvider(folder), variant_dir=variant)
        bind_answer(folder, key, answers[key])
    return run_investigation(DEMO_CASE, ExchangeProvider(folder), variant_dir=variant)


def test_incremental_round_trip(tmp_path):
    inv = answer_all(tmp_path / "x")
    report = render_report(inv)
    assert "AGENT ANSWERS" in report and "[AGENT]" in report
    assert set(inv.bindings) == set(KEYS)
    prompt = (tmp_path / "x" / "1-trace.prompt.md").read_text(encoding="utf-8")
    assert inv.bindings["1-trace"] in prompt.splitlines()[0]


def test_unbound_answer_is_refused(tmp_path):
    folder = tmp_path / "x"
    folder.mkdir()
    (folder / "1-trace.answer.json").write_text(json.dumps(ANSWERS["1-trace"]), encoding="utf-8")
    with pytest.raises(StaleAnswer, match="has no binding"):
        run_investigation(DEMO_CASE, ExchangeProvider(folder))


def test_wrong_binding_is_refused(tmp_path):
    folder = tmp_path / "x"
    folder.mkdir()
    (folder / "1-trace.answer.json").write_text(json.dumps({"binding": "0" * 64, "answer": ANSWERS["1-trace"]}))
    with pytest.raises(StaleAnswer, match="different request"):
        run_investigation(DEMO_CASE, ExchangeProvider(folder))


def test_changed_evidence_makes_answers_stale(tmp_path):
    folder = tmp_path / "x"
    answer_all(folder)
    with pytest.raises(StaleAnswer, match="1-trace.answer.json was written for a different request"):
        run_investigation(DEMO_CASE, ExchangeProvider(folder), variant_dir=DEMO_VARIANTS / "missing-evidence")


def test_changed_earlier_answer_invalidates_later_answers(tmp_path):
    folder = tmp_path / "x"
    answer_all(folder)
    changed = json.loads(json.dumps(ANSWERS["1-trace"]))
    changed["ambiguities"].append("Whether the release note was read by support.")
    bind_answer(folder, "1-trace", changed)          # step 1's request did not change, so its binding is the same
    with pytest.raises(StaleAnswer, match="2-validation.answer.json was written for a different request"):
        run_investigation(DEMO_CASE, ExchangeProvider(folder))


def test_earlier_answer_change_is_detected_even_if_checked_result_is_identical(tmp_path):
    """Same content, different bytes: the checked result is equal, but the accepted answer changed."""
    folder = tmp_path / "x"
    answer_all(folder)
    reordered = dict(reversed(list(ANSWERS["1-trace"].items())))
    bind_answer(folder, "1-trace", reordered)
    with pytest.raises(StaleAnswer, match="2-validation"):
        run_investigation(DEMO_CASE, ExchangeProvider(folder))


def test_rebinding_after_a_change_completes_again(tmp_path):
    folder = tmp_path / "x"
    answer_all(folder)
    changed = json.loads(json.dumps(ANSWERS["1-trace"]))
    changed["ambiguities"].append("Another open question.")
    bind_answer(folder, "1-trace", changed)
    for key in KEYS[1:]:
        with pytest.raises(StaleAnswer):
            run_investigation(DEMO_CASE, ExchangeProvider(folder))
        (folder / f"{key}.answer.json").unlink()      # the agent discards the stale answer ...
        with pytest.raises(AwaitingAnswer):
            run_investigation(DEMO_CASE, ExchangeProvider(folder))
        bind_answer(folder, key, ANSWERS[key])        # ... and answers the new prompt
    inv = run_investigation(DEMO_CASE, ExchangeProvider(folder))
    assert "Another open question." in inv.trace.ambiguities


def test_invalid_saved_answer_is_reported_and_kept(tmp_path):
    folder, out = tmp_path / "x", tmp_path / "out"
    with pytest.raises(AwaitingAnswer):
        run_investigation(DEMO_CASE, ExchangeProvider(folder), out_dir=out)
    bind_answer(folder, "1-trace", {"production_problem": "only this"})
    with pytest.raises(PassOutputError, match="saved answer for step 1-trace"):
        run_investigation(DEMO_CASE, ExchangeProvider(folder), out_dir=out)
    kept = list((out / "raw").glob("1-trace.attempt-*.txt"))
    assert kept and "only this" in kept[0].read_text(encoding="utf-8")


def test_cli_exchange_workflow_reuses_its_unfinished_output_folder(tmp_path):
    """Reruns into the same --out work without --overwrite until the run finishes; nothing is forced."""
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    folder, out = tmp_path / "x", tmp_path / "out"
    cmd = [sys.executable, "-m", "haq", "investigate", str(DEMO_CASE), "--out", str(out), "--answers-dir", str(folder)]
    for key in KEYS:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
        assert r.returncode == 3, r.stderr
        bind_answer(folder, key, ANSWERS[key])
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stderr
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 2 and "finished investigation" in r.stderr
