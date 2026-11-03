"""Deterministic Markdown report. No model writes any part of it.

Every statement carries its origin:

    [CHECK]     computed by code from the evidence (engine guards and this skill's checks)
    [SCRIPTED] / [MODEL] / [AGENT]
                proposed by the answer source named at the top of the report
    [DECISION]  for a person to decide; nothing in this tool makes that decision
"""

from __future__ import annotations

from ._engine.guards import norm
from .hypotheses import ROOT_CAUSE

TAGS = {"scripted": "SCRIPTED", "ollama": "MODEL", "exchange": "AGENT"}


def _cell(text: object) -> str:
    return " ".join(str(text).split()).replace("|", "\\|") or "—"


def _changed(before: str, after: str) -> str:
    return f"{after} (answered {before})" if norm(before) != norm(after) else after


def render_report(inv) -> str:
    tag = f"[{TAGS.get(inv.provider_name, 'MODEL')}]"
    case, bundle = inv.case, inv.case.bundle
    trace, validation, hyp = inv.trace, inv.validation, inv.hypotheses
    raw_trace, raw_val, raw_hyp = (inv.raw.get(k) for k in ("1-trace", "2-validation", "3-hypotheses"))
    out: list[str] = []
    w = out.append

    w(f"# Escaped-defect investigation: {case.title or bundle.case_id}")
    w("")
    w(f"- Case: `{bundle.case_id}`" + (f" (variant `{case.variant}`)" if case.variant else ""))
    w(f"- Answers: **{inv.provider_label}** — marked {tag} below")
    w(f"- Checks: hyper-agile-engine guards (vendored) and this skill's hypothesis checks — marked [CHECK]")
    w("- Decisions: none taken by this tool — marked [DECISION]")
    w("")
    if inv.provider_name == "scripted":
        w("> **Scripted demo.** The answers in this report were written in advance for a fictional case. No model "
          "was run. The checks and the report are real code running on those answers.")
        w("")
    w("> This report contains checked hypotheses for human review. It does not establish a root cause. [CHECK] "
      "means an identifier, citation or quote was found where the answer said it was, or a rule was applied; "
      "it does not mean the evidence says what the hypothesis claims.")
    w("")

    # ---------------------------------------------------------------- 1
    w("## 1. Production problem")
    w("")
    w(f"{tag} {trace.production_problem}")
    w("")

    # ---------------------------------------------------------------- 2
    w("## 2. Evidence chain: production back to origin")
    w("")
    w("| Link | Recorded? [CHECK] | Confidence [CHECK] | Verified support [CHECK] | Basis " + tag + " |")
    w("| --- | --- | --- | --- | --- |")
    for link, before in zip(trace.links, raw_trace.links):
        w(f"| {_cell(link.from_item)} → {_cell(link.to_item)} ({_cell(link.relationship_type)}) "
          f"| {_changed(before.direct_or_inferred, link.direct_or_inferred)} "
          f"| {_changed(before.confidence, link.confidence)} | {_cell(link.verified_support or 'none (unresolved)')} "
          f"| {_cell(link.basis)} |")
    w("")
    if trace.critical_signals:
        w("Critical signals " + tag + " with provenance [CHECK]:")
        w("")
        for s, before in zip(trace.critical_signals, raw_trace.critical_signals):
            provenance = "source holds what it says" if s.verified else "NOT VERIFIED: supports nothing downstream"
            w(f"- `{s.id}` ({s.timing}, relevance {s.relevance}, {_changed(before.confidence, s.confidence)}; "
              f"provenance: {provenance}) from `{s.source_artifact or 'unresolved'}` — {s.description}")
        w("")
    w(f"Known before release {tag}:")
    w("")
    out += [f"- {x}" for x in trace.known_before_release] or ["- (none stated)"]
    w("")
    w(f"Learned after release {tag}:")
    w("")
    out += [f"- {x}" for x in trace.learned_after_release] or ["- (none stated)"]
    w("")
    if trace.timeline:
        w(f"Timeline {tag}:")
        w("")
        out += [f"- {e.when} — {e.event} (`{e.source or 'unresolved'}`)" for e in trace.timeline]
        w("")

    # ---------------------------------------------------------------- 3
    w("## 3. Testing and release evidence")
    w("")
    if validation.test_relevance:
        w(f"| Test | Could detect the failure? [CHECK] | Classification [CHECK] | Confidence [CHECK] | Run for this release? {tag} | Material differences {tag} |")
        w("| --- | --- | --- | --- | --- | --- |")
        for t, before in zip(validation.test_relevance, raw_val.test_relevance):
            w(f"| {_cell(t.test)} | {_changed(before.could_this_test_detect_the_failure, t.could_this_test_detect_the_failure)} "
              f"| {_cell(t.classification)} | {_changed(before.confidence, t.confidence)} | {_cell(t.was_selected_or_executed)} "
              f"| {_cell(t.material_differences)} |")
        w("")
    w(f"- Regression-selection gap [CHECK, derived from the rows above]: **{validation.regression_selection_gap or 'not derived'}**")
    w(f"- Test-coverage failure mode {tag}: {validation.test_coverage_failure_mode}")
    w(f"- What CI actually demonstrated {tag}: {validation.ci_evidence_provided}")
    if validation.release_signals:
        w(f"- Signals available at release time {tag}: " + "; ".join(validation.release_signals))
    w("")
    w(f"Quality Loop activities in this step {tag}, held by [CHECK]:")
    w("")
    for a, before in zip(validation.activities, raw_val.activities):
        w(f"- **{a.activity}**: {_changed(before.status, a.status)} — {a.finding} "
          f"({a.evidence_status.replace('_', ' ').lower()})")
    w("")

    # ---------------------------------------------------------------- 4
    w("## 4. What the evidence supports, contradicts and leaves unknown")
    w("")
    groups = (("Supported after checks", "SUPPORTED"), ("Contradicted or in conflict", "CONTRADICTED"),
              ("Not established", "NOT ESTABLISHED"))
    before_by_id = {h.id: h for h in raw_hyp.hypotheses}
    for title, status in groups:
        members = [h for h in hyp.hypotheses if h.check_status == status]
        w(f"### {title} [CHECK]")
        w("")
        if not members:
            w("- None.")
            w("")
            continue
        for h in members:
            before = before_by_id.get(h.id)
            w(f"**{h.id}** {tag} {h.statement}")
            w("")
            w(f"- Layer: {h.layer}; Quality Loop activity: {h.loop_activity}")
            w(f"- Confidence [CHECK]: {_changed(before.confidence if before else h.confidence, h.confidence)} — citations and quotes checked; meaning not verified")
            for q, c in zip([*h.supporting, *h.contradicting], h.quote_checks):
                w(f"- {c['role'].capitalize()} quote from `{q.source}` — {c['status']}: “{_cell(q.quote)}”")
            if not h.supporting:
                w("- No supporting quote given.")
            w(f"- What would settle it {tag}: {h.what_would_settle_it}")
            if ROOT_CAUSE.search(h.statement):
                w("- [CHECK] The answer uses the words “root cause”. This tool does not establish root causes; "
                  "read it as a hypothesis.")
            w("")
    w(f"### Unknowns {tag}")
    w("")
    out += [f"- {u}" for u in hyp.unknowns] or ["- None stated."]
    w("")
    w("### Evidence limitations [CHECK]")
    w("")
    out += [f"- {l}" for l in bundle.limitations] or ["- None recorded by the adapter."]
    w("")

    # ---------------------------------------------------------------- 5
    w("## 5. What worked")
    w("")
    for item in hyp.what_worked:
        checks = ", ".join(f"`{q.source}` {c['status']}" for q, c in zip(item.supporting, item.quote_checks)) or "no quote"
        w(f"- {tag} {item.statement} — quotes [CHECK]: {checks}")
    if not hyp.what_worked:
        w("- None stated.")
    w("")

    # ---------------------------------------------------------------- 6/7
    w("## 6. Proposed regression tests (for human review)")
    w("")
    for t in hyp.proposed_regression_tests:
        w(f"**{t.id}. {t.title}** {tag}")
        w("")
        w(f"- Condition: {t.condition}")
        w(f"- Level: {t.level}; destination: {t.destination}; addresses: {', '.join(t.addresses) or '—'}")
        for flag in t.review_flags:
            w(f"- Review flag [CHECK]: {flag}")
        w("- Status [DECISION]: proposed — not accepted")
        w("")
    w("## 7. Proposed quality-loop improvements (for human review)")
    w("")
    for c in hyp.proposed_controls:
        w(f"**{c.id}. {c.loop_activity}** {tag} {c.control}")
        w("")
        w(f"- Where: {c.destination}; owner type: {c.owner_type}; addresses: {', '.join(c.addresses) or '—'}")
        w(f"- Recurrence protection: {c.recurrence_protection}")
        for flag in c.review_flags:
            w(f"- Review flag [CHECK]: {flag}")
        w("- Status [DECISION]: proposed — not accepted")
        w("")

    # ---------------------------------------------------------------- 8
    w("## 8. Decisions needed [DECISION]")
    w("")
    w("Record decisions in `decisions.yaml` next to this report. This tool never marks a hypothesis as the cause, "
      "and never creates tickets, tests or monitoring.")
    w("")
    w(f"- {len(hyp.hypotheses)} hypotheses to accept, reject or investigate further")
    w(f"- {len(hyp.proposed_regression_tests)} proposed regression tests and {len(hyp.proposed_controls)} proposed controls to accept or reject")
    w("")

    # ---------------------------------------------------------------- 9
    w("## 9. Check log [CHECK]")
    w("")
    if inv.checks:
        w("| Step | Rule | Subject | Answered → after check | Reason |")
        w("| --- | --- | --- | --- | --- |")
        for c in inv.checks:
            change = f"{c.get('original', '')} → {c.get('corrected', '')}" if c.get("original") or c.get("corrected") else "—"
            w(f"| {c['step']} | {c.get('guard_id', '')} | {_cell(c.get('subject') or c.get('qualifier') or '')} "
              f"| {_cell(change)} | {_cell(c.get('reason', ''))} |")
    else:
        w("- No check changed any answer.")
    w("")
    for warning in inv.warnings:
        w(f"- Warning: {warning}")

    # ---------------------------------------------------------------- 10
    w("## 10. Evidence reviewed")
    w("")
    w("| Evidence ID | Category | File | SHA-256 (first 12) |")
    w("| --- | --- | --- | --- |")
    for a in bundle.artifacts():
        digest = case.files.get(a.source_path, "")[:12] or "derived"
        w(f"| `{a.ref}` | {a.category} | {a.source_path} | {digest} |")
    w("")
    return "\n".join(out).rstrip() + "\n"


def decisions_template(inv, result_sha256: str) -> str:
    hyp = inv.hypotheses
    lines = ["# Human decisions for this investigation. Nothing here is filled in by the tool.",
             "# For each item set decision to one of: accept, reject, investigate. Add who decided (a role) and why.",
             "# These decisions apply only to the result named by result_sha256. If the evidence or the answers change,",
             "# the result changes and `haq check-decisions` reports these decisions as not applying to it.",
             f"case: {inv.case.bundle.case_id}", f"result_sha256: {result_sha256}", "hypotheses:"]
    for h in hyp.hypotheses:
        lines += [f"  {h.id}:", f"    checked_status: {h.check_status}", "    decision: null", "    decided_by_role: null",
                  "    reason: null"]
    lines.append("proposals:")
    for p in (*hyp.proposed_regression_tests, *hyp.proposed_controls):
        lines += [f"  {p.id}:", "    decision: null", "    decided_by_role: null", "    reason: null"]
    return "\n".join(lines) + "\n"
