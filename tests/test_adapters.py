"""Local evidence adapters: fictional fixtures only, no network."""

from pathlib import Path

import pytest

from haq._engine.errors import EvidenceError
from haq.adapters import load_evidence
from haq.cli import DEMO_CASE, DEMO_VARIANTS


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_demo_case_categories_and_ids():
    case = load_evidence(DEMO_CASE)
    refs = {a.ref: a.category for a in case.bundle.artifacts()}
    assert refs["issue:SHOP-482"] == "production_issue"
    assert refs["issue:SHOP-455"] == "originating_work"
    assert refs["junit:ci-unit"] == "ci_evidence"
    assert refs["release:4.2.0"] == "release_evidence"
    assert refs["fix-change.md"] == "remediation_changes"
    assert refs["adapter:relationships"] == "additional_evidence"
    assert case.incident == "SHOP-482"


def test_issue_links_become_recorded_relationships():
    case = load_evidence(DEMO_CASE)
    assert case.relationships == [{"source": "SHOP-482", "target": "SHOP-455",
                                   "relationship_type": "issue link: is caused by", "direct_or_inferred": "DIRECT"}]
    ties = case.bundle.recorded_ties()
    assert ties and ties[0][0] == "SHOP-482" and ties[0][1] == "SHOP-455"


def test_yaml_dates_and_hash_characters_are_rendered_as_written():
    issue = next(a for a in load_evidence(DEMO_CASE).bundle.artifacts() if a.ref == "issue:SHOP-455")
    assert "2026-02-26T14:20:00Z" in issue.content
    assert "Merged in PR #318." in issue.content


def test_junit_statuses(tmp_path):
    write(tmp_path, "test-results/run.xml", """<testsuite name="s" tests="3">
      <testcase classname="a" name="ok"/>
      <testcase classname="a" name="bad"><failure message="expected 6.00 got 11.40"/></testcase>
      <testcase classname="a" name="skip"><skipped/></testcase></testsuite>""")
    content = load_evidence(tmp_path).bundle.ci_evidence[0].content
    assert "a::ok: passed" in content
    assert "a::bad: FAILED (expected 6.00 got 11.40)" in content
    assert "a::skip: SKIPPED" in content


def test_release_record_rendering(tmp_path):
    write(tmp_path, "releases/r.yaml", "version: 1.2.3\nvalidation_runs:\n  - id: R-1\n    results: {TC-1: FAILED}\n"
                                       "    not_run: [TC-2]\napproval: {decision: approved, by_role: Release manager, note: risk accepted}\n")
    art = load_evidence(tmp_path).bundle.release_evidence[0]
    assert art.ref == "release:1.2.3"
    assert "TC-1: FAILED" in art.content and "Not run: TC-2" in art.content and "Note: risk accepted" in art.content


def test_credentials_are_masked_and_counted(tmp_path):
    token = "ghp_" + "A1b2C3d4" * 5  # built at runtime; fictional token-shaped value
    write(tmp_path, "ci.md", f"# CI log\nexport GITHUB_TOKEN={token}\n")
    case = load_evidence(tmp_path)
    assert token not in case.bundle.ci_evidence[0].content
    assert case.masked >= 1
    assert any("masked" in limitation for limitation in case.bundle.limitations)


def test_unsupported_and_missing_files_are_limitations(tmp_path):
    write(tmp_path, "production-issue.md", "# Bug\nIt failed.")
    write(tmp_path, "screenshot.png", "not really an image")
    limitations = load_evidence(tmp_path).bundle.limitations
    assert "Skipped unsupported file: screenshot.png" in limitations
    assert any("No test evidence artifact" in l for l in limitations)


def test_incident_named_but_not_provided(tmp_path):
    write(tmp_path, "case.yaml", "id: x\nincident: KEY-9\n")
    write(tmp_path, "tests.md", "# Tests")
    assert any("issues/KEY-9.yaml was not provided" in l for l in load_evidence(tmp_path).bundle.limitations)


def test_empty_case_is_an_error(tmp_path):
    with pytest.raises(EvidenceError):
        load_evidence(tmp_path)


def test_variant_removes_and_replaces():
    case = load_evidence(DEMO_CASE, DEMO_VARIANTS / "missing-evidence")
    refs = {a.ref for a in case.bundle.artifacts()}
    assert "tests.md" not in refs and "junit:ci-unit" not in refs
    assert case.relationships == []
    assert "SHOP-470" not in next(a for a in case.bundle.artifacts() if a.ref == "release:4.2.0").content
    assert case.bundle.case_id == "checkout-promo+missing-evidence"


def test_variant_cannot_remove_unknown_file(tmp_path):
    write(tmp_path, "v/variant.yaml", "remove: [nope.md]\n")
    with pytest.raises(EvidenceError):
        load_evidence(DEMO_CASE, tmp_path / "v")
