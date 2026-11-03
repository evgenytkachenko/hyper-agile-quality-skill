"""Local evidence adapters: a case folder on disk -> the engine's EvidenceBundle.

Everything here reads local files only. Nothing contacts a network service.

Supported inputs inside a case folder (all optional, at least one required):

    case.yaml                     case metadata: id, title, incident (the production issue key)
    <stem>.md / .markdown / .txt  hand-written evidence, filed by the engine's file-stem
                                  convention (production-issue, originating-story,
                                  requirements, documentation, code-change, fix-change,
                                  tests, ci, release, production-learning; anything
                                  else is "additional evidence")
    issues/<KEY>.yaml             issue-tracker records exported to YAML; their `links`
                                  become recorded (DIRECT) relationships
    test-results/<name>.xml       JUnit XML test results (CI evidence)
    releases/<name>.yaml          release records (version, date, included issues,
                                  validation runs, approval note)

A *variant* folder can be laid over a case to show how missing or changed evidence
changes the result: its `variant.yaml` lists files to `remove`, and every other file in
the variant folder adds or replaces the file at the same relative path.

Credential-like strings are masked with the engine's masking rules before anything is
shown to a model or written to the output.
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from ._engine.errors import EvidenceError
from ._engine.evidence import (
    CATEGORY_BY_STEM,
    FALLBACK_CATEGORY,
    IGNORED_STEMS,
    OPTIONAL_CATEGORIES,
    SUPPORTED_SUFFIXES,
    EvidenceArtifact,
    EvidenceBundle,
)
from ._engine.masking import MASK, mask_text

MAX_FILE_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_CHARS = 20000
STRUCTURED_DIRS = {"issues", "test-results", "releases"}
VARIANT_MANIFEST = "variant.yaml"


@dataclass
class LoadedCase:
    bundle: EvidenceBundle
    title: str
    incident: str
    # relative path -> sha256 of the bytes as read (before masking)
    files: dict[str, str] = field(default_factory=dict)
    relationships: list[dict] = field(default_factory=list)
    masked: int = 0
    variant: str = ""


# ------------------------------------------------------------------ file map


def _read_tree(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        raise EvidenceError(f"Case folder does not exist: {root}")
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts) or path.is_symlink():
            continue
        if path.is_file():
            if path.stat().st_size > MAX_FILE_BYTES:
                raise EvidenceError(f"{rel} is larger than {MAX_FILE_BYTES} bytes; split or trim it.")
            files[rel.as_posix()] = path.read_bytes()
    return files


def apply_variant(files: dict[str, bytes], variant_dir: Path) -> dict[str, bytes]:
    """Return a new file map with the variant's removals and replacements applied."""
    overlay = _read_tree(variant_dir)
    manifest = yaml.safe_load(overlay.pop(VARIANT_MANIFEST, b"") or b"") or {}
    out = dict(files)
    for rel in manifest.get("remove", []) or []:
        if rel not in out:
            raise EvidenceError(f"Variant removes {rel}, which is not in the case.")
        del out[rel]
    out.update(overlay)
    return out


# ------------------------------------------------------------------ renderers


def _lines(items: list[Any]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- (none recorded)"


def render_issue(raw: dict) -> str:
    key, title = str(raw.get("key", "")), str(raw.get("title", ""))
    out = [f"# {key} — {title}", ""]
    for label, name in (("Type", "type"), ("Status", "status"), ("Priority", "priority"), ("Created", "created"),
                        ("Resolved", "resolved"), ("Affected versions", "affected_versions"),
                        ("Fix versions", "fix_versions"), ("Components", "components")):
        value = raw.get(name)
        if value not in (None, "", []):
            out.append(f"- {label}: {', '.join(map(str, value)) if isinstance(value, list) else value}")
    links = raw.get("links") or []
    if links:
        out += ["", "## Issue links"]
        out += [f"- {l.get('relation', 'relates to')}: {l.get('target', '')}" + (f" — {l['title']}" if l.get("title") else "")
                for l in links]
    if raw.get("description"):
        out += ["", "## Description", str(raw["description"]).strip()]
    if raw.get("acceptance_criteria"):
        out += ["", "## Acceptance criteria", _lines(raw["acceptance_criteria"])]
    comments = raw.get("comments") or []
    if comments:
        out += ["", "## Comments"]
        for c in comments:
            who = c.get("author_role") or "Unattributed"
            out.append(f"- {c.get('at', 'unknown time')} ({who}): {str(c.get('body', '')).strip()}")
    return "\n".join(out)


def render_junit(name: str, data: bytes) -> str:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise EvidenceError(f"test-results/{name} is not well-formed XML: {exc}") from exc
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    out = [f"# Test results: {name}", "",
           "JUnit XML results as recorded. A passing test shows that the test passed, not what it exercised."]
    for suite in suites:
        out += ["", f"## Suite {suite.get('name', '(unnamed)')}"]
        for attr in ("timestamp", "hostname", "tests", "failures", "errors", "skipped"):
            if suite.get(attr) is not None:
                out.append(f"- {attr}: {suite.get(attr)}")
        props = {p.get("name"): p.get("value") for p in suite.iter("property")}
        for k, v in props.items():
            out.append(f"- property {k}: {v}")
        out.append("")
        for case in suite.iter("testcase"):
            status = "passed"
            for tag in ("failure", "error", "skipped"):
                node = case.find(tag)
                if node is not None:
                    status = {"failure": "FAILED", "error": "ERROR", "skipped": "SKIPPED"}[tag]
                    detail = (node.get("message") or (node.text or "")).strip()
                    if detail:
                        status += f" ({' '.join(detail.split())[:300]})"
                    break
            cls = case.get("classname")
            label = f"{cls}::{case.get('name')}" if cls else str(case.get("name"))
            out.append(f"- {label}: {status}")
    return "\n".join(out)


def render_release(raw: dict) -> str:
    version = str(raw.get("version", ""))
    out = [f"# Release {version}", ""]
    for label, name in (("Released", "released"), ("Environment", "environment"), ("Commit", "commit"),
                        ("Status", "status")):
        if raw.get(name) not in (None, ""):
            out.append(f"- {label}: {raw[name]}")
    if raw.get("issues"):
        out.append(f"- Work items: {', '.join(map(str, raw['issues']))}")
    for run in raw.get("validation_runs") or []:
        out += ["", f"## Validation run {run.get('id', '')} — {run.get('name', '')}"]
        for label, name in (("Status", "status"), ("Started", "started"), ("Finished", "finished")):
            if run.get(name):
                out.append(f"- {label}: {run[name]}")
        results = run.get("results") or {}
        if results:
            out.append("- Results: " + ", ".join(f"{k}: {v}" for k, v in results.items()))
        if run.get("not_run"):
            out.append("- Not run: " + ", ".join(map(str, run["not_run"])))
    approval = raw.get("approval")
    if approval:
        out += ["", "## Release decision",
                f"- Decision: {approval.get('decision', 'unknown')}",
                f"- Recorded by: {approval.get('by_role', 'unattributed role')}",
                f"- At: {approval.get('at', 'unknown')}"]
        if approval.get("note"):
            out.append(f"- Note: {' '.join(str(approval['note']).split())}")
    if raw.get("notes"):
        out += ["", "## Notes", str(raw["notes"]).strip()]
    return "\n".join(out)


def render_relationships(rows: list[dict]) -> str:
    out = ["# Recorded relationships", "",
           "Derived by the local adapter from issue-record link fields. DIRECT means an issue record lists the link. "
           "A relationship says that a reference exists; it does not say that the target is the origin or the cause "
           "of anything.", ""]
    for n, row in enumerate(rows, start=1):
        out.append(f"- relationship:rel-{n:03d} | {row['source']} → {row['target']} | {row['relationship_type']} | "
                   f"{row['direct_or_inferred']} | recorded in issues/{row['source']}.yaml")
    return "\n".join(out)


# ------------------------------------------------------------------ loading


def _plain(value: Any) -> Any:
    """YAML turns unquoted timestamps into date objects; render them back as written in ISO form."""
    if isinstance(value, datetime):
        text = value.isoformat()
        return text[:-6] + "Z" if text.endswith("+00:00") else text
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _yaml(rel: str, data: bytes) -> dict:
    try:
        raw = yaml.safe_load(data.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise EvidenceError(f"{rel} is not readable YAML: {type(exc).__name__}") from exc
    if not isinstance(raw, dict):
        raise EvidenceError(f"{rel} must contain a YAML mapping.")
    return _plain(raw)


def load_evidence(case_dir: Path, variant_dir: Path | None = None,
                  max_chars_per_artifact: int = DEFAULT_MAX_CHARS) -> LoadedCase:
    files = _read_tree(case_dir)
    variant = ""
    if variant_dir is not None:
        files = apply_variant(files, variant_dir)
        variant = variant_dir.name
    meta = _yaml("case.yaml", files["case.yaml"]) if "case.yaml" in files else {}
    case_id = str(meta.get("id") or case_dir.resolve().name) + (f"+{variant}" if variant else "")
    incident = str(meta.get("incident") or "")
    bundle = EvidenceBundle(case_id=case_id)
    loaded = LoadedCase(bundle=bundle, title=str(meta.get("title") or ""), incident=incident, variant=variant)
    relationships: list[dict] = []

    def add(rel: str, category: str, content: str, evidence_id: str = "") -> None:
        masked = mask_text(content)
        loaded.masked += masked.count(MASK) - content.count(MASK)
        content = masked.strip()
        if not content:
            bundle.limitations.append(f"Skipped empty file: {rel}")
            return
        truncated = len(content) > max_chars_per_artifact
        if truncated:
            bundle.limitations.append(
                f"{rel} was truncated to the first {max_chars_per_artifact} characters (of {len(content)}).")
            content = content[:max_chars_per_artifact]
        getattr(bundle, category).append(EvidenceArtifact(
            name=PurePosixPath(rel).name, category=category, content=content, source_path=rel,
            truncated=truncated, evidence_id=evidence_id))

    for rel, data in sorted(files.items()):
        loaded.files[rel] = hashlib.sha256(data).hexdigest()
        path = PurePosixPath(rel)
        top = path.parts[0] if len(path.parts) > 1 else ""
        if rel == "case.yaml" or (path.stem.lower() in IGNORED_STEMS and not top):
            continue
        if top == "issues" and path.suffix.lower() in {".yaml", ".yml"}:
            raw = _yaml(rel, data)
            key = str(raw.get("key") or path.stem)
            raw["key"] = key
            category = "production_issue" if key == incident else "originating_work"
            add(rel, category, render_issue(raw), evidence_id=f"issue:{key}")
            for link in raw.get("links") or []:
                relationships.append({"source": key, "target": str(link.get("target", "")),
                                      "relationship_type": f"issue link: {link.get('relation', 'relates to')}",
                                      "direct_or_inferred": "DIRECT"})
        elif top == "test-results" and path.suffix.lower() == ".xml":
            add(rel, "ci_evidence", render_junit(path.name, data), evidence_id=f"junit:{path.stem}")
        elif top == "releases" and path.suffix.lower() in {".yaml", ".yml"}:
            raw = _yaml(rel, data)
            add(rel, "release_evidence", render_release(raw), evidence_id=f"release:{raw.get('version') or path.stem}")
        elif not top and path.suffix.lower() in SUPPORTED_SUFFIXES:
            text = data.decode("utf-8", errors="replace")
            add(rel, CATEGORY_BY_STEM.get(path.stem.lower(), FALLBACK_CATEGORY), text)
        elif top and top not in STRUCTURED_DIRS and path.suffix.lower() in SUPPORTED_SUFFIXES:
            text = data.decode("utf-8", errors="replace")
            add(rel, FALLBACK_CATEGORY, text)
        else:
            bundle.limitations.append(f"Skipped unsupported file: {rel}")

    if relationships:
        add("recorded-relationships.md", FALLBACK_CATEGORY, render_relationships(relationships),
            evidence_id="adapter:relationships")
        bundle.set_relationships(relationships)
    loaded.relationships = relationships

    if not bundle.artifacts():
        raise EvidenceError(f"No supported evidence found in {case_dir}.")
    if incident and not any(a.evidence_id == f"issue:{incident}" for a in bundle.production_issue):
        bundle.limitations.append(f"case.yaml names incident {incident}, but issues/{incident}.yaml was not provided.")
    for category in CATEGORY_BY_STEM.values():
        if category not in OPTIONAL_CATEGORIES and not getattr(bundle, category):
            bundle.limitations.append(f"No {category.replace('_', ' ')} artifact was provided in the case folder.")
    if loaded.masked:
        bundle.limitations.append(f"{loaded.masked} credential-like value(s) were masked before analysis.")
    return loaded
