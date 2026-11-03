"""A person's decisions are never silently overwritten, and they stay bound to the result they reviewed."""

import json
import os
import subprocess
import sys

import pytest

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
    assert r.returncode == 1 and "do not apply to this report" in r.stdout


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


# ------------------------------------------------------------------ independent review findings


def test_archive_name_cannot_be_steered_by_the_file(tmp_path):
    out = tmp_path / "a"
    haq("demo", "--out", str(out))
    text = (out / "decisions.yaml").read_text()
    digest = json.loads((out / "run.json").read_text())["result_sha256"]
    (out / "decisions.yaml").write_text(text.replace(digest, "x/../../escaped"))
    (out / "decisions.superseded-x").mkdir()
    r = haq("demo", "--out", str(out), "--overwrite", "--archive-decisions")
    assert r.returncode == 0, r.stderr
    archived = out / "decisions.superseded-unbound.yaml"
    assert archived.is_file() and "x/../../escaped" in archived.read_text()
    assert not (tmp_path / "escaped").exists() and not list(tmp_path.glob("*.yaml"))


def test_check_decisions_does_not_echo_non_digest_values(tmp_path):
    out = tmp_path / "a"
    haq("demo", "--out", str(out))
    text = (out / "decisions.yaml").read_text()
    digest = json.loads((out / "run.json").read_text())["result_sha256"]
    (out / "decisions.yaml").write_text(text.replace(digest, "ghp_" + "Zx9" * 12))
    r = haq("check-decisions", str(out))
    assert r.returncode == 1 and "(not a digest)" in r.stdout and "ghp_Zx9" not in r.stdout


def test_failed_overwrite_keeps_the_previous_result(tmp_path):
    out, bad = tmp_path / "a", tmp_path / "bad.json"
    haq("demo", "--out", str(out))
    report = (out / "report.md").read_text()
    data = json.loads(DEMO_RESPONSES.read_text())
    data["responses"]["2-validation"] = "not an object"
    bad.write_text(json.dumps(data))
    r = haq("investigate", str(DEMO_CASE), "--out", str(out), "--scripted", str(bad), "--overwrite")
    assert r.returncode == 2
    assert (out / "previous-run" / "report.md").read_text() == report
    assert (out / "previous-run" / "decisions.yaml").is_file()
    r = haq("demo", "--out", str(out))          # the folder is unfinished now, so it can be reused
    assert r.returncode == 0, r.stderr
    assert not (out / "previous-run").exists() and (out / "report.md").read_text() == report


def test_successful_overwrite_removes_the_previous_result(tmp_path):
    out = tmp_path / "a"
    haq("demo", "--out", str(out))
    assert haq("demo", "--variant", "missing-evidence", "--out", str(out), "--overwrite").returncode == 0
    assert not (out / "previous-run").exists()
    assert sorted(p.name for p in (out / "raw").iterdir()) == [
        "1-trace.attempt-1.json", "2-validation.attempt-1.json", "3-hypotheses.attempt-1.json"]


# ------------------------------------------------------------------ check-decisions verifies the result


def finished(tmp_path, *extra):
    out = tmp_path / "a"
    assert haq("demo", "--out", str(out), *extra).returncode == 0
    decide(out)
    return out


def test_intact_result_passes_and_says_what_was_not_checked(tmp_path):
    out = finished(tmp_path)
    r = haq("check-decisions", str(out))
    assert r.returncode == 0 and "NOT CHECKED: evidence" in r.stdout and "nothing is signed" in r.stdout
    r = haq("check-decisions", str(out), "--case", str(DEMO_CASE))
    assert r.returncode == 0 and "OK: the case folder's evidence is unchanged." in r.stdout


@pytest.mark.parametrize("name", ["report.md", "checks.json"])
def test_edited_output_file_fails(tmp_path, name):
    out = finished(tmp_path)
    (out / name).write_text((out / name).read_text() + "\n", encoding="utf-8")
    r = haq("check-decisions", str(out))
    assert r.returncode == 1 and f"FAIL: {name} differs from the file this run wrote." in r.stdout


def test_edited_checked_result_fails_even_with_hashes_updated(tmp_path):
    """Someone flips a hypothesis to SUPPORTED and updates the recorded file hash; the digest no longer recomputes."""
    import hashlib

    out = finished(tmp_path)
    results = json.loads((out / "results.json").read_text())
    results["checked"]["3-hypotheses"]["hypotheses"][5]["check_status"] = "SUPPORTED"
    (out / "results.json").write_text(json.dumps(results, indent=1))
    run = json.loads((out / "run.json").read_text())
    run["artifacts_sha256"]["results.json"] = hashlib.sha256((out / "results.json").read_bytes()).hexdigest()
    (out / "run.json").write_text(json.dumps(run, indent=1))
    r = haq("check-decisions", str(out))
    assert r.returncode == 1 and "result digest recomputed from them does not match" in r.stdout


def test_forged_digest_in_run_and_decisions_fails(tmp_path):
    out = finished(tmp_path)
    run = json.loads((out / "run.json").read_text())
    forged = "f" * 64
    (out / "decisions.yaml").write_text((out / "decisions.yaml").read_text().replace(run["result_sha256"], forged))
    run["result_sha256"] = forged
    (out / "run.json").write_text(json.dumps(run, indent=1))
    r = haq("check-decisions", str(out))
    assert r.returncode == 1 and "does not match the recorded one" in r.stdout


def test_changed_evidence_is_detected_with_case(tmp_path):
    import shutil

    out = finished(tmp_path)
    case = tmp_path / "case"
    shutil.copytree(DEMO_CASE, case)
    (case / "tests.md").write_text((case / "tests.md").read_text() + "\n## TC-213 — added later\n")
    r = haq("check-decisions", str(out), "--case", str(case))
    assert r.returncode == 1 and "evidence differs" in r.stdout and "tests.md" in r.stdout
    r = haq("check-decisions", str(out), "--case", str(DEMO_CASE), "--variant",
            str(DEMO_CASE.parent / "variants" / "missing-evidence"))
    assert r.returncode == 1 and "evidence differs" in r.stdout


def test_older_run_record_cannot_be_verified(tmp_path):
    out = finished(tmp_path)
    run = json.loads((out / "run.json").read_text())
    del run["result_basis"], run["artifacts_sha256"]
    (out / "run.json").write_text(json.dumps(run, indent=1))
    r = haq("check-decisions", str(out))
    assert r.returncode == 1 and "cannot be recomputed" in r.stdout and "cannot be verified" in r.stdout


# ------------------------------------------------------------------ second independent review


@pytest.mark.parametrize("edit,message", [
    (lambda t: t.replace("  H4:\n    checked_status: CONTRADICTED\n    decision: null",
                         "  H4:\n    checked_status: SUPPORTED\n    decision: accept"), "checked status that is not"),
    (lambda t: t.replace("proposals:\n", "  H99:\n    decision: accept\nproposals:\n"), "'H99', which is not"),
    (lambda t: t.replace("decision: null", "decision: approve-release", 1), "not one of accept, reject, investigate"),
    (lambda t: t.split("hypotheses:")[0] + "hypotheses: [H1]\n", "must be a mapping"),
])
def test_decisions_that_go_beyond_the_result_fail(tmp_path, edit, message):
    out = tmp_path / "a"
    haq("demo", "--out", str(out))
    path = out / "decisions.yaml"
    edited = edit(path.read_text())
    assert edited != path.read_text()
    path.write_text(edited)
    r = haq("check-decisions", str(out))
    assert r.returncode == 1 and message in r.stdout and "Traceback" not in r.stdout + r.stderr


def test_check_lists_what_it_does_not_verify_and_requires_case_for_variant(tmp_path):
    out = tmp_path / "a"
    haq("demo", "--out", str(out))
    r = haq("check-decisions", str(out))
    assert "NOT CHECKED: the raw/ attempt records" in r.stdout
    r = haq("check-decisions", str(out), "--variant", str(DEMO_CASE.parent / "variants" / "missing-evidence"))
    assert r.returncode == 2 and "--variant needs --case" in r.stderr


@pytest.mark.parametrize("edit,message", [
    (lambda t: t.replace("case: checkout-promo", "case: other"), "names a different case"),
    (lambda t: t + "release_approval: approved\n", "keys the template does not define"),
    (lambda t: t.replace("  H1:\n    checked_status: SUPPORTED\n    decision: null",
                         "  H1:\n    checked_status: SUPPORTED\n    decision: accept\n    applies_to: all hypotheses"),
     "fields the template does not define"),
    (lambda t: t.replace("  T1:\n    decision: null", "  T1:\n    decision: accept\n    scope: everything"),
     "fields the template does not define"),
])
def test_content_outside_the_template_fails(tmp_path, edit, message):
    out = tmp_path / "a"
    haq("demo", "--out", str(out))
    path = out / "decisions.yaml"
    edited = edit(path.read_text())
    assert edited != path.read_text()
    path.write_text(edited)
    r = haq("check-decisions", str(out))
    assert r.returncode == 1 and message in r.stdout


def test_items_with_problems_are_not_listed_as_decided(tmp_path):
    out = tmp_path / "a"
    haq("demo", "--out", str(out))
    path = out / "decisions.yaml"
    text = path.read_text().replace("  H4:\n    checked_status: CONTRADICTED\n    decision: null",
                                    "  H4:\n    checked_status: SUPPORTED\n    decision: accept")
    path.write_text(text.replace("  H1:\n    checked_status: SUPPORTED\n    decision: null",
                                 "  H1:\n    checked_status: SUPPORTED\n    decision: accept"))
    r = haq("check-decisions", str(out))
    assert r.returncode == 1 and "0 decisions apply to this result (1 recorded but NOT applicable: H1=accept)" in r.stdout


# ------------------------------------------------------------------ third independent review


def demo_out(tmp_path):
    out = tmp_path / "a"
    assert haq("demo", "--out", str(out)).returncode == 0
    return out


@pytest.mark.parametrize("edit", [
    lambda t: t.replace("  H1:\n    checked_status: SUPPORTED\n    decision: null",
                        "  H1:\n    checked_status: SUPPORTED\n    decision: reject\n    decision: accept"),
    lambda t: t + "hypotheses:\n  H1:\n    checked_status: SUPPORTED\n    decision: accept\n",
])
def test_duplicate_keys_fail(tmp_path, edit):
    out = demo_out(tmp_path)
    (out / "decisions.yaml").write_text(edit((out / "decisions.yaml").read_text()))
    r = haq("check-decisions", str(out))
    assert r.returncode == 1 and "repeats the key" in r.stdout and "decided:" not in r.stdout


@pytest.mark.parametrize("field,value", [
    ("reason", "{scope: all future results, approve_all: true}"),
    ("decided_by_role", "[qa, release-manager, everyone]"),
    ("reason", "'" + "x" * 2001 + "'"),
])
def test_role_and_reason_must_be_plain_text(tmp_path, field, value):
    out = demo_out(tmp_path)
    text = (out / "decisions.yaml").read_text().replace(
        "  H1:\n    checked_status: SUPPORTED\n    decision: null\n    decided_by_role: null\n    reason: null",
        "  H1:\n    checked_status: SUPPORTED\n    decision: accept\n    decided_by_role: null\n    reason: null", 1)
    (out / "decisions.yaml").write_text(text.replace(f"    {field}: null", f"    {field}: {value}", 1))
    r = haq("check-decisions", str(out))
    assert r.returncode == 1 and f"{field} must be plain text" in r.stdout


def test_a_plain_role_and_reason_still_pass(tmp_path):
    out = demo_out(tmp_path)
    text = (out / "decisions.yaml").read_text().replace(
        "  H1:\n    checked_status: SUPPORTED\n    decision: null\n    decided_by_role: null\n    reason: null",
        "  H1:\n    checked_status: SUPPORTED\n    decision: accept\n    decided_by_role: QA lead\n"
        "    reason: Quote and diff agree.", 1)
    (out / "decisions.yaml").write_text(text)
    r = haq("check-decisions", str(out))
    assert r.returncode == 0 and "1 item(s) of this result decided: H1=accept" in r.stdout


def test_decisions_are_not_listed_as_applying_when_any_check_fails(tmp_path):
    out = demo_out(tmp_path)
    text = (out / "decisions.yaml").read_text().replace("decision: null", "decision: accept", 1)
    run = json.loads((out / "run.json").read_text())
    (out / "decisions.yaml").write_text(text.replace(run["result_sha256"], "e" * 64))
    r = haq("check-decisions", str(out))
    assert r.returncode == 1 and "0 decisions apply to this result (1 recorded but NOT applicable: H1=accept)" in r.stdout
    assert "of this result decided" not in r.stdout


@pytest.mark.parametrize("tamper", [
    lambda c: c.__setitem__("3-hypotheses", "x"),
    lambda c: c["3-hypotheses"].__setitem__("hypotheses", 5),
    lambda c: c["3-hypotheses"].__setitem__("proposed_controls", {"C1": 1}),
])
def test_tampered_results_fail_cleanly(tmp_path, tamper):
    out = demo_out(tmp_path)
    results = json.loads((out / "results.json").read_text())
    tamper(results["checked"])
    (out / "results.json").write_text(json.dumps(results))
    r = haq("check-decisions", str(out))
    assert r.returncode == 1 and "FAIL:" in r.stdout and "unexpected" not in r.stderr


def test_results_json_that_is_not_an_object_fails_cleanly(tmp_path):
    out = demo_out(tmp_path)
    (out / "results.json").write_text("[]")
    r = haq("check-decisions", str(out))
    assert r.returncode == 1 and "does not hold a JSON object" in r.stdout


@pytest.mark.parametrize("tamper", [
    lambda c: c["3-hypotheses"]["hypotheses"][0].__setitem__("id", ["x"]),
    lambda c: c["3-hypotheses"]["proposed_controls"][0].__setitem__("id", {"a": 1}),
    lambda c: c["3-hypotheses"]["proposed_regression_tests"].__setitem__(0, "T1"),
])
def test_non_text_item_ids_in_results_fail_cleanly(tmp_path, tamper):
    out = demo_out(tmp_path)
    results = json.loads((out / "results.json").read_text())
    tamper(results["checked"])
    (out / "results.json").write_text(json.dumps(results))
    r = haq("check-decisions", str(out))
    assert r.returncode == 1 and "FAIL:" in r.stdout and "unexpected" not in r.stderr
