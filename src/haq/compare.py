"""Compare two investigation outputs deterministically. No model is called."""

from __future__ import annotations

import json
from pathlib import Path


def _load(folder: Path) -> dict:
    data = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    return {"checked": data["checked"], "limitations": data.get("limitations", []), "run": run}


def _rows(a: dict, b: dict) -> list[tuple[str, str, str]]:
    rows = []
    ta, tb = a["checked"]["1-trace"], b["checked"]["1-trace"]
    links_a = {f"{l['from_item']} → {l['to_item']}": l for l in ta["links"]}
    links_b = {f"{l['from_item']} → {l['to_item']}": l for l in tb["links"]}
    for name in dict.fromkeys([*links_a, *links_b]):
        x, y = links_a.get(name), links_b.get(name)
        fx = f"{x['direct_or_inferred']}, {x['confidence']}" if x else "absent"
        fy = f"{y['direct_or_inferred']}, {y['confidence']}" if y else "absent"
        if fx != fy:
            rows.append((f"Link {name}", fx, fy))
    sig_a = {s["id"]: s for s in ta["critical_signals"]}
    sig_b = {s["id"]: s for s in tb["critical_signals"]}
    for sid in dict.fromkeys([*sig_a, *sig_b]):
        x, y = sig_a.get(sid), sig_b.get(sid)
        fx = f"{'verified' if x.get('verified') else 'not verified'}, {x['confidence']}" if x else "absent"
        fy = f"{'verified' if y.get('verified') else 'not verified'}, {y['confidence']}" if y else "absent"
        if fx != fy:
            rows.append((f"Critical signal {sid}", fx, fy))
    va, vb = a["checked"]["2-validation"], b["checked"]["2-validation"]
    tests_a = {t["test"]: t for t in va["test_relevance"]}
    tests_b = {t["test"]: t for t in vb["test_relevance"]}
    for name in dict.fromkeys([*tests_a, *tests_b]):
        x, y = tests_a.get(name), tests_b.get(name)
        fx = f"{x['classification']}, {x['confidence']}" if x else "absent"
        fy = f"{y['classification']}, {y['confidence']}" if y else "absent"
        if fx != fy:
            rows.append((f"Test {name}", fx, fy))
    if va["regression_selection_gap"] != vb["regression_selection_gap"]:
        rows.append(("Regression-selection gap", va["regression_selection_gap"], vb["regression_selection_gap"]))
    ha = {h["id"]: h for h in a["checked"]["3-hypotheses"]["hypotheses"]}
    hb = {h["id"]: h for h in b["checked"]["3-hypotheses"]["hypotheses"]}
    for hid in dict.fromkeys([*ha, *hb]):
        x, y = ha.get(hid), hb.get(hid)
        fx = f"{x['check_status']}, {x['confidence']}" if x else "absent"
        fy = f"{y['check_status']}, {y['confidence']}" if y else "absent"
        if fx != fy:
            rows.append((f"Hypothesis {hid}", fx, fy))
    pa = {p["id"]: p for k in ("proposed_regression_tests", "proposed_controls") for p in a["checked"]["3-hypotheses"][k]}
    pb = {p["id"]: p for k in ("proposed_regression_tests", "proposed_controls") for p in b["checked"]["3-hypotheses"][k]}
    for pid in dict.fromkeys([*pa, *pb]):
        fx = f"{len(pa[pid]['review_flags'])} review flag(s)" if pid in pa else "absent"
        fy = f"{len(pb[pid]['review_flags'])} review flag(s)" if pid in pb else "absent"
        if fx != fy:
            rows.append((f"Proposal {pid}", fx, fy))
    return rows


def compare(a_dir: Path, b_dir: Path) -> str:
    a, b = _load(a_dir), _load(b_dir)
    out = [f"# Comparison: `{a['run']['case_id']}` vs `{b['run']['case_id']}`", "",
           f"- A answers: {a['run']['answers']['label']}",
           f"- B answers: {b['run']['answers']['label']}", ""]
    same_answers = a["run"]["answers"] == b["run"]["answers"]
    if same_answers:
        out += ["Both runs used the same answer source, so every difference below comes from the evidence and the "
                "deterministic checks, not from different answers.", ""]
    changed = sorted(set(a["run"]["evidence_files_sha256"].items()) ^ set(b["run"]["evidence_files_sha256"].items()))
    files = sorted({name for name, _ in changed})
    out += ["## Evidence files that differ", ""]
    for name in files:
        in_a, in_b = name in a["run"]["evidence_files_sha256"], name in b["run"]["evidence_files_sha256"]
        out.append(f"- `{name}`: " + ("changed" if in_a and in_b else "only in A" if in_a else "only in B"))
    if not files:
        out.append("- None.")
    out += ["", "## Checked results that differ", "", "| Item | A | B |", "| --- | --- | --- |"]
    rows = _rows(a, b)
    out += [f"| {x} | {y} | {z} |" for x, y, z in rows] or ["| (none) | | |"]
    lim_a, lim_b = set(a["limitations"]), set(b["limitations"])
    out += ["", "## Evidence limitations only in B", ""]
    out += [f"- {l}" for l in sorted(lim_b - lim_a)] or ["- None."]
    out += ["", "## Evidence limitations only in A", ""]
    out += [f"- {l}" for l in sorted(lim_a - lim_b)] or ["- None."]
    return "\n".join(out) + "\n"
