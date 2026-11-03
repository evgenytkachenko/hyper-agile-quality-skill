"""Loads the methodology from disk. The files under methodology/ are the source of truth:
nothing here restates their content, it only reads, slices, and hashes them."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import MethodologyError

REQUIRED_FILES = {
    "skill": "SKILL.md",
    "quality-loop": "references/quality-loop.md",
    "causal-model": "references/causal-model.md",
    "evidence-and-actions": "references/evidence-and-actions.md",
    "tool-mapping": "references/tool-mapping.md",
    "report-template": "references/report-template.md",
    "evaluation-harness": "references/evaluation-harness.md",
}

_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
_NUMBERED_BOLD = re.compile(r"^\d+\.\s+\*\*(.+?)\*\*", re.M)


def _split_sections(text: str) -> dict[str, str]:
    """Split on level-2 headings, ignoring headings inside code fences."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    in_fence = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            current = sections.setdefault(line[3:].strip(), [line])
            continue
        if current is not None:
            current.append(line)
    return {heading: "\n".join(lines).strip() for heading, lines in sections.items()}


@dataclass(frozen=True)
class MethodologyDoc:
    key: str
    relative_path: str
    text: str
    sha256: str

    def section(self, heading_prefix: str) -> str:
        sections = _split_sections(self.text)
        for heading, body in sections.items():
            if heading.lower().startswith(heading_prefix.lower()):
                return body
        raise MethodologyError(
            f"Methodology section '{heading_prefix}' not found in {self.relative_path}. "
            "The heading may have been renamed; update the pass definitions to match."
        )


class Methodology:
    def __init__(self, root: Path, docs: dict[str, MethodologyDoc]):
        self.root = root
        self.docs = docs

    @classmethod
    def load(cls, root: Path) -> Methodology:
        if not root.is_dir():
            raise MethodologyError(f"Methodology folder does not exist: {root}")
        docs = {}
        for key, relative in REQUIRED_FILES.items():
            path = root / relative
            if not path.is_file():
                raise MethodologyError(f"Required methodology file is missing: {path}")
            raw = path.read_bytes()
            text = _FRONTMATTER.sub("", raw.decode("utf-8"), count=1).strip()
            docs[key] = MethodologyDoc(key, relative, text, hashlib.sha256(raw).hexdigest())
        return cls(root, docs)

    def text(self, key: str, section: str | None = None) -> str:
        doc = self.docs[key]
        return doc.section(section) if section else doc.text

    def hashes(self) -> dict[str, str]:
        return {doc.relative_path: doc.sha256 for doc in self.docs.values()}

    def loop_activities(self) -> list[str]:
        names = _NUMBERED_BOLD.findall(self.docs["quality-loop"].text)
        if not names:
            raise MethodologyError(
                "Could not read the Quality Loop activities from references/quality-loop.md."
            )
        return names

    def confidence_levels(self) -> list[str]:
        """Evidence confidence levels, strongest first, as listed in the methodology."""
        section = self.text("evidence-and-actions", "Evidence confidence levels")
        levels = re.findall(r"^- `([^`]+)`", section, re.M)
        if len(levels) < 3:
            raise MethodologyError(
                "Could not read the evidence confidence levels from "
                "references/evidence-and-actions.md."
            )
        return levels

    def report_headers(self) -> list[str]:
        fenced = re.search(r"```[a-z]*\n(.*?)```", self.docs["report-template"].text, re.S)
        headers = [l.strip() for l in fenced.group(1).splitlines() if l.startswith("#")] if fenced else []
        if not headers:
            raise MethodologyError(
                "Could not read the report section headers from references/report-template.md."
            )
        return headers
