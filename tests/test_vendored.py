"""Vendored engine files match the hashes recorded in VENDORED.md, and nothing else is vendored."""

import hashlib
import re

from conftest import ROOT


def recorded() -> dict[str, str]:
    text = (ROOT / "VENDORED.md").read_text(encoding="utf-8")
    return dict(re.findall(r"^\| `(src/haq/[^`]+)` \| `[^`]+` \| [^|]+ \| `([0-9a-f]{64})` \|$", text, re.M))


def test_vendored_hashes_match():
    table = recorded()
    assert len(table) == 17
    for path, digest in table.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path


def test_nothing_unlisted_is_vendored():
    table = recorded()
    on_disk = {p.relative_to(ROOT).as_posix() for d in ("src/haq/_engine", "src/haq/_methodology")
               for p in (ROOT / d).rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    extra = on_disk - set(table) - {"src/haq/_engine/__init__.py", "src/haq/_engine/providers/__init__.py"}
    assert extra == set()
