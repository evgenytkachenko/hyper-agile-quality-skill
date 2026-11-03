"""Pre-publication check for this repository.

1. Every file tracked by Git (or, with --files-from-disk, every file on disk outside ignored
   folders) must be listed in PUBLICATION_ALLOWLIST.
2. Every listed file is scanned for credential-like strings (the engine's masking rules),
   e-mail addresses, absolute home-directory paths and private-network addresses.
3. Optionally, --denylist FILE adds terms (one per line, case-insensitive) that must not
   appear anywhere. Keep that file outside the repository: it names what must not be published.

Values that match are never printed; only the file, line number and rule are.
A clean result is not proof that the repository is safe to publish.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from haq._engine.masking import MASK, mask_text  # noqa: E402

RULES = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+"),
    "home-path": re.compile(r"(?:/Users/|/home/|C:\\Users\\)[A-Za-z0-9._-]+"),
    "private-ip": re.compile(r"\b(?:10\.\d+|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d+\.\d+\b"),
}
# Fictional or documentation values that are allowed on purpose.
ALLOWED = {"noreply@anthropic.com"}


def listed() -> list[str]:
    lines = (ROOT / "PUBLICATION_ALLOWLIST").read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


def tracked(from_disk: bool) -> list[str]:
    if from_disk:
        skip = {".git", ".venv", "__pycache__", ".pytest_cache", "dist", "build"}
        return sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
                      if p.is_file() and not skip & set(p.relative_to(ROOT).parts))
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return sorted(out.split())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--denylist", type=Path)
    parser.add_argument("--files-from-disk", action="store_true")
    args = parser.parse_args()
    allow = listed()
    problems = []
    for path in sorted(set(tracked(args.files_from_disk)) - set(allow)):
        problems.append(f"{path}: not in PUBLICATION_ALLOWLIST")
    for path in sorted(set(allow) - set(tracked(args.files_from_disk))):
        problems.append(f"{path}: listed but not present")
    deny = []
    if args.denylist:
        deny = [t.strip().lower() for t in args.denylist.read_text(encoding="utf-8").splitlines() if t.strip()]
    for rel in allow:
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), start=1):
            if mask_text(line).count(MASK) > line.count(MASK) and "fictional token-shaped" not in line:
                problems.append(f"{rel}:{n}: credential-like value")
            for name, rule in RULES.items():
                if any(m not in ALLOWED for m in rule.findall(line)):
                    problems.append(f"{rel}:{n}: {name}")
            low = line.lower()
            for i, term in enumerate(deny):
                if term in low:
                    problems.append(f"{rel}:{n}: denylist term #{i + 1}")
    for p in problems:
        print(p)
    print(f"{len(allow)} allowlisted file(s) checked; {len(problems)} problem(s).")
    print("A clean result is not proof that the repository is safe to publish.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
