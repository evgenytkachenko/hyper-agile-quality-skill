"""A person's decisions are never silently overwritten, and they stay bound to the result they reviewed."""

import json
import os
import subprocess
import sys

from conftest import ROOT, bind_answer

from haq.cli import DEMO_CASE, DEMO_RESPONSES
from haq.investigate import check_decisions, result_digest

ANSWERS = json.loads(DEMO_RESPONSES.read_text(encoding="utf-8"))["responses"]


def haq(*args):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.run([sys.executable, "-m", "haq", *args], capture_output=True, text=True, env=env, timeout=120)


def decide(out):
    path = out / "decisions.yaml"
    text = path.read_text(encoding="utf-8").replace("decision: null", "decision: accept", 1)
    path.write_text(text, encoding="utf-8")
    return text


def test_decisions_are_bound_to_the_result(tmp_path, baseline, variant):
    out = tmp_path / "a"
    assert haq("demo", "--out", str(out)).returncode == 0
    run = json.loads((out / "run.json").read_text())
    assert f"result_sha256: {run['result_sha256']}" in (out / "decisions.yaml").read_text()
    assert run["result_sha256"] == result_digest(baseline) != result_digest(variant)
    assert check_decisions(out)[0] is True


def test_edited_decisions_block_overwrite(tmp_path):
    out = tmp_path / "a"
    haq("demo", "--out", str(out))
    edited = decide(out)
    r = haq("demo", "--out", str(out), "--overwrite")
    assert r.returncode == 2 and "may contain a person's decisions" in r.stderr and "Nothing was changed" in r.stderr
    assert (out / "decisions.yaml").read_text() == edited


def test_archive_keeps_old_decisions_and_starts_unreviewed(tmp_path):
    out = tmp_path / "a"
    haq("demo", "--out", str(out))
    edited = decide(out)
    bound = json.loads((out / "run.json").read_text())["result_sha256"][:12]
    r = haq("demo", "--variant", "missing-evidence", "--out", str(out), "--overwrite", "--archive-decisions")
    assert r.returncode == 0, r.stderr
    archived = out / f"decisions.superseded-{bound}.yaml"
    assert archived.read_text() == edited
    fresh = (out / "decisions.yaml").read_text()
    assert "decision: accept" not in fresh
    assert check_decisions(out)[0] is True


def test_archive_flag_alone_does_not_replace_a_finished_run(tmp_path):
    out = tmp_path / "a"
    haq("demo", "--out", str(out))
    edited = decide(out)
    r = haq("demo", "--out", str(out), "--archive-decisions")
    assert r.returncode == 2 and "finished investigation" in r.stderr
    assert (out / "decisions.yaml").read_text() == edited and not list(out.glob("decisions.superseded-*"))


def test_untouched_template_is_replaced_by_overwrite(tmp_path):
    out = tmp_path / "a"
    haq("demo", "--out", str(out))
    r = haq("demo", "--variant", "missing-evidence", "--out", str(out), "--overwrite")
    assert r.returncode == 0, r.stderr
    assert not list(out.glob("decisions.superseded-*"))
    assert check_decisions(out)[0] is True


def test_decisions_copied_to_a_changed_result_do_not_apply(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    haq("demo", "--out", str(a))
    haq("demo", "--variant", "missing-evidence", "--out", str(b))
    (b / "decisions.yaml").write_text(decide(a))
    r = haq("check-decisions", str(b))
    assert r.returncode == 1 and "not bound to this result" in r.stdout


def test_exchange_rerun_cannot_replace_decisions(tmp_path):
    """Previously an exchange run forced overwrite and replaced decisions.yaml with an empty template."""
    folder, out = tmp_path / "x", tmp_path / "out"
    args = ["investigate", str(DEMO_CASE), "--out", str(out), "--answers-dir", str(folder)]
    for key in ANSWERS:
        haq(*args)
        bind_answer(folder, key, ANSWERS[key])
    assert haq(*args).returncode == 0
    edited = decide(out)
    for extra in ([], ["--overwrite"]):
        r = haq(*args, *extra)
        assert r.returncode == 2
        assert (out / "decisions.yaml").read_text() == edited


def test_unknown_folder_is_not_written_into(tmp_path):
    (tmp_path / "notes.txt").write_text("mine")
    r = haq("demo", "--out", str(tmp_path), "--overwrite")
    assert r.returncode == 2 and "not a haq output folder" in r.stderr
    assert (tmp_path / "notes.txt").read_text() == "mine"


def test_decisions_without_a_run_record_are_treated_as_edited(tmp_path):
    out = tmp_path / "a"
    haq("demo", "--out", str(out))
    (out / "run.json").unlink()
    r = haq("demo", "--out", str(out), "--overwrite")
    assert r.returncode == 2 and "may contain a person's decisions" in r.stderr
