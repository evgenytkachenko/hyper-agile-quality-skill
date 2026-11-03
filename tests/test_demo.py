"""The no-model demo: scripted answers, real checks. Pins the checked outcome of both runs."""

from pathlib import Path

from conftest import ROOT, by_id, rules

from haq.compare import compare
from haq.investigate import write_outputs
from haq.report import render_report


def test_baseline_trace_links(baseline):
    links = {f"{l.from_item} → {l.to_item}": l for l in baseline.trace.links}
    assert links["SHOP-482 → SHOP-455"].direct_or_inferred == "DIRECT"
    assert links["SHOP-482 → SHOP-455"].confidence == "CONFIRMED"
    # Claimed DIRECT through a shared commit SHA only: the engine relabels it.
    assert links["PR #318 → junit:ci-unit"].direct_or_inferred == "INFERRED"
    assert links["PR #318 → junit:ci-unit"].confidence == "STRONGLY SUPPORTED"
    assert "G-TRACE-SUPPORT" in rules(baseline, "PR #318 → junit:ci-unit")


def test_baseline_test_relevance_and_derived_gap(baseline):
    rows = {t.test: t for t in baseline.validation.test_relevance}
    assert rows["TC-211"].could_this_test_detect_the_failure == "UNCERTAIN"   # answered YES with material differences
    assert rows["TC-210"].classification == "RELATED BUT NOT DETECTING"
    assert baseline.validation.regression_selection_gap == "UNCERTAIN"
    assert "G-GAP-DERIVED" in rules(baseline)


def test_baseline_hypotheses(baseline):
    expected = {
        "H1": ("SUPPORTED", "STRONGLY SUPPORTED"),
        "H2": ("SUPPORTED", "CONFIRMED"),
        "H3": ("SUPPORTED", "STRONGLY SUPPORTED"),
        "H4": ("CONTRADICTED", "POSSIBLE CONTRIBUTING FACTOR"),
        "H5": ("CONTRADICTED", "UNKNOWN"),
        "H6": ("NOT ESTABLISHED", "UNKNOWN"),
        "H7": ("SUPPORTED", "POSSIBLE CONTRIBUTING FACTOR"),
    }
    assert {h.id: (h.check_status, h.confidence) for h in baseline.hypotheses.hypotheses} == expected
    assert "H-CONTRADICTED" in rules(baseline, "H4")
    assert "H-REGRESSION-GAP" in rules(baseline, "H5")
    assert {"G-CITATION-UNRESOLVED", "G-EVIDENCE-REF"} <= {c["guard_id"] for c in baseline.checks
                                                            if c["step"] == "3-hypotheses" and "'H6'" in c["reason"]}
    assert "H-POST-RELEASE-ONLY" in rules(baseline, "H7")
    assert by_id(baseline, "H6").quote_checks[0]["status"] == "UNKNOWN_SOURCE"


def test_baseline_proposal_flags(baseline):
    flags = {p.id: p.review_flags for p in (*baseline.hypotheses.proposed_regression_tests,
                                             *baseline.hypotheses.proposed_controls)}
    assert flags["T1"] == [] and flags["C1"] == [] and flags["C2"] == []
    assert any("SUPPORTED" in f for f in flags["T3"])        # addresses only H5
    assert any("SUPPORTED" in f for f in flags["C3"])        # addresses only H6
    assert any("vague" in f for f in flags["C4"])


def test_variant_changes_follow_the_evidence(variant):
    links = {f"{l.from_item} → {l.to_item}": l for l in variant.trace.links}
    assert links["SHOP-482 → SHOP-455"].direct_or_inferred == "INFERRED"   # link field removed
    signals = {s.id: s for s in variant.trace.critical_signals}
    assert signals["signal-002"].verified is False                       # release note changed
    assert signals["signal-002"].confidence == "UNKNOWN"
    assert by_id(variant, "H2").check_status == "NOT ESTABLISHED"        # test evidence removed
    assert by_id(variant, "H2").confidence == "UNKNOWN"
    assert by_id(variant, "H3").check_status == "NOT ESTABLISHED"        # quote no longer in the release record
    assert "H-QUOTE-PROVENANCE" in rules(variant, "H3")
    assert by_id(variant, "H1").check_status == "SUPPORTED"              # untouched evidence, unchanged result
    assert any("No test evidence artifact" in l for l in variant.case.bundle.limitations)


def test_same_answers_are_used_in_both_runs(baseline, variant):
    assert [h.model_dump() for h in baseline.raw["3-hypotheses"].hypotheses] == \
           [h.model_dump() for h in variant.raw["3-hypotheses"].hypotheses]


def test_report_labels_and_no_root_cause_claim(baseline):
    report = render_report(baseline)
    assert "SCRIPTED RESPONSES (not a model)" in report and "No model was run" in report
    assert "It does not establish a root cause" in report
    assert "[CHECK]" in report and "[DECISION]" in report and "[SCRIPTED]" in report
    assert "[MODEL]" not in report


def test_report_is_deterministic(baseline):
    assert render_report(baseline) == render_report(baseline)


def test_committed_sample_output_is_current(baseline, variant, tmp_path):
    """docs/sample-output must be what the code produces now."""
    sample = ROOT / "docs" / "sample-output"
    assert (sample / "baseline" / "report.md").read_text(encoding="utf-8") == render_report(baseline)
    assert (sample / "missing-evidence" / "report.md").read_text(encoding="utf-8") == render_report(variant)
    a, b = tmp_path / "a", tmp_path / "b"
    write_outputs(baseline, a)
    write_outputs(variant, b)
    assert (sample / "comparison.md").read_text(encoding="utf-8") == compare(a, b)


def test_readme_excerpts_come_from_the_sample_output():
    import re

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    sample = "".join((ROOT / "docs" / "sample-output" / p).read_text(encoding="utf-8")
                     for p in ("baseline/report.md", "comparison.md"))
    blocks = re.findall(r"```markdown\n(.*?)```", readme, re.S)
    assert len(blocks) == 2
    for line in "\n".join(blocks).splitlines():
        assert not line.strip() or line in sample, line


def test_documentation_warns_that_masking_cannot_catch_every_secret():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "**Masking cannot catch every secret.**" in readme
    assert "review every output before you\n> share" in readme
    for path in ("docs/connectors.md", "skill/hyper-agile-quality/SKILL.md"):
        assert "Masking cannot catch every secret" in (ROOT / path).read_text(encoding="utf-8") or \
               "masking cannot catch every secret" in (ROOT / path).read_text(encoding="utf-8"), path
