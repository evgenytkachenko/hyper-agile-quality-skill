from pathlib import Path

import pytest

from haq.cli import DEMO_CASE, DEMO_RESPONSES, DEMO_VARIANTS
from haq.investigate import run_investigation
from haq.providers import ScriptedProvider

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def baseline():
    return run_investigation(DEMO_CASE, ScriptedProvider(DEMO_RESPONSES))


@pytest.fixture(scope="session")
def variant():
    return run_investigation(DEMO_CASE, ScriptedProvider(DEMO_RESPONSES),
                             variant_dir=DEMO_VARIANTS / "missing-evidence")


def by_id(inv, hid):
    return next(h for h in inv.hypotheses.hypotheses if h.id == hid)


def rules(inv, subject=None):
    return {c["guard_id"] for c in inv.checks if subject is None or c.get("subject") == subject}
