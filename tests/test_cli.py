"""The command line, run as a user would run it. No model and no network."""

import os
import subprocess
import sys

from conftest import ROOT


def haq(*args, cwd=None, env_extra=None):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), **(env_extra or {})}
    for name in ("HAQ_MODEL", "HAQ_OLLAMA_URL"):
        env.pop(name, None)
    return subprocess.run([sys.executable, "-m", "haq", *args], cwd=cwd or ROOT, env=env,
                          capture_output=True, text=True, timeout=120)


def test_demo_and_variant_and_compare(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    r = haq("demo", "--out", str(a))
    assert r.returncode == 0, r.stderr
    assert "SCRIPTED" in r.stdout and "4 supported, 2 contradicted, 1 not established" in r.stdout
    r = haq("demo", "--variant", "missing-evidence", "--out", str(b))
    assert r.returncode == 0, r.stderr
    assert "2 supported, 1 contradicted, 4 not established" in r.stdout
    for name in ("report.md", "results.json", "checks.json", "run.json", "decisions.yaml"):
        assert (a / name).is_file()
    r = haq("compare", str(a), str(b))
    assert r.returncode == 0 and "| Link SHOP-482 → SHOP-455 | DIRECT, CONFIRMED | INFERRED, STRONGLY SUPPORTED |" in r.stdout


def test_existing_output_is_not_overwritten(tmp_path):
    (tmp_path / "keep.txt").write_text("x")
    r = haq("demo", "--out", str(tmp_path))
    assert r.returncode == 2 and "not empty" in r.stderr


def test_remote_model_endpoint_is_refused(tmp_path):
    r = haq("investigate", "src/haq/examples/checkout-promo", "--out", str(tmp_path / "o"),
            "--model", "m", "--base-url", "http://192.0.2.10:11434")
    assert r.returncode == 2 and "not a loopback" in r.stderr


def test_init_then_check_case(tmp_path):
    case = tmp_path / "case"
    assert haq("init", str(case)).returncode == 0
    r = haq("check-case", str(case))
    assert r.returncode == 0 and "[issue:KEY-1] production_issue" in r.stdout


def test_doctor_without_model(tmp_path):
    r = haq("doctor")
    assert r.returncode == 0 and "Ollama: not checked" in r.stdout and "Methodology: ok" in r.stdout
