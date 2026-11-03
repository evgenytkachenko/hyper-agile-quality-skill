"""Command line: haq demo | investigate | check-case | compare | init | doctor."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import ENGINE_SOURCE_COMMIT, __version__
from ._engine.errors import HyperAgileError
from ._engine.masking import mask_text

EXAMPLES = Path(__file__).parent / "examples"
DEMO_CASE = EXAMPLES / "checkout-promo"
DEMO_RESPONSES = EXAMPLES / "checkout-promo.responses.json"
DEMO_VARIANTS = EXAMPLES / "variants"
DEFAULT_OLLAMA_URL = "http://localhost:11434"

CASE_TEMPLATE = {
    "case.yaml": "# Case metadata. Use only evidence you are allowed to analyze.\nid: my-case\ntitle: One-line description of the escaped defect\nincident: KEY-1   # the production issue key; its record goes in issues/KEY-1.yaml\n",
    "issues/KEY-1.yaml": "key: KEY-1\ntype: Bug\ntitle: What failed in production\nstatus: Done\ncreated: 2026-01-01T00:00:00Z\naffected_versions: [1.0.0]\nlinks:\n  - relation: is caused by\n    target: KEY-0\n    title: The originating story, if a link is recorded\ndescription: |\n  Expected vs actual behavior, impact, how it was detected.\ncomments: []\n",
    "requirements.md": "# Requirements\n\nPaste the requirement or acceptance criteria as they were before release.\n",
    "code-change.md": "# Implementing change\n\nPull request / commit identifiers, title, changed files, review notes.\n",
    "tests.md": "# Test cases\n\nEach relevant test case with its identifier, precondition, steps and expected result.\n",
    "production-learning.md": "# Production evidence\n\nDetection, impact, timeline after release.\n",
    "releases/1.0.0.yaml": "version: 1.0.0\nreleased: 2026-01-01\nissues: [KEY-0]\nvalidation_runs: []\napproval:\n  decision: approved\n  by_role: release manager\n  note: \"\"\n",
}


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _provider(args):
    from .providers import ExchangeProvider, ScriptedProvider, make_ollama

    chosen = [x for x in (args.scripted, args.answers_dir) if x]
    if len(chosen) > 1:
        raise HyperAgileError("Choose one answer source: --scripted, --answers-dir, or a local model (default).")
    if args.scripted:
        return ScriptedProvider(Path(args.scripted))
    if args.answers_dir:
        return ExchangeProvider(Path(args.answers_dir))
    think = _env("HAQ_THINK")
    return make_ollama(args.base_url or _env("HAQ_OLLAMA_URL", DEFAULT_OLLAMA_URL), args.model or _env("HAQ_MODEL", ""),
                       allow_remote=args.allow_remote,
                       timeout_seconds=float(_env("HAQ_TIMEOUT_SECONDS", "600")),
                       context_tokens=int(args.context_tokens or _env("HAQ_CONTEXT_TOKENS", "16384")),
                       temperature=float(_env("HAQ_TEMPERATURE", "0.1")),
                       think=None if think is None else think.lower() in {"1", "true", "yes"})


def _say(text: str) -> None:
    print(mask_text(text))


def _run(case: Path, provider, out: Path, variant: Path | None, overwrite: bool, context_tokens: int | None,
         archive_decisions: bool = False) -> int:
    from .investigate import prepare_out_dir, run_investigation, write_outputs
    from .providers import AwaitingAnswer

    for note in prepare_out_dir(out, overwrite, archive_decisions):
        _say(note)
    try:
        inv = run_investigation(case, provider, variant_dir=variant, out_dir=out, context_tokens=context_tokens)
    except AwaitingAnswer as exc:
        _say(str(exc))
        return 3
    paths = write_outputs(inv, out)
    hyp = inv.hypotheses
    counts = {s: sum(h.check_status == s for h in hyp.hypotheses) for s in ("SUPPORTED", "CONTRADICTED", "NOT ESTABLISHED")}
    _say(f"Answers: {inv.provider_label}")
    _say(f"Hypotheses after checks: {counts['SUPPORTED']} supported, {counts['CONTRADICTED']} contradicted, "
         f"{counts['NOT ESTABLISHED']} not established; {len(inv.checks)} check note(s).")
    _say(f"Regression-selection gap (derived): {inv.validation.regression_selection_gap}")
    for name, path in paths.items():
        _say(f"  {name:9} {path}")
    return 0


def cmd_demo(args) -> int:
    from .providers import ScriptedProvider

    variant = None
    if args.variant:
        variant = DEMO_VARIANTS / args.variant
        if not variant.is_dir():
            names = ", ".join(sorted(p.name for p in DEMO_VARIANTS.iterdir() if p.is_dir()))
            raise HyperAgileError(f"Unknown variant '{args.variant}'. Available: {names}")
    out = Path(args.out or ("haq-demo" + (f"-{args.variant}" if args.variant else "")))
    print("Running the fictional demo with SCRIPTED responses (no model is called).")
    return _run(DEMO_CASE, ScriptedProvider(DEMO_RESPONSES), out, variant, args.overwrite, None,
                args.archive_decisions)


def cmd_investigate(args) -> int:
    provider = _provider(args)
    if provider.name == "ollama":
        provider.check_ready()
    ctx = int(args.context_tokens or _env("HAQ_CONTEXT_TOKENS", "16384")) if provider.name == "ollama" else None
    return _run(Path(args.case), provider, Path(args.out), Path(args.variant) if args.variant else None,
                args.overwrite, ctx, args.archive_decisions)


def cmd_check_case(args) -> int:
    from .adapters import load_evidence

    case = load_evidence(Path(args.case), Path(args.variant) if args.variant else None)
    _say(f"Case {case.bundle.case_id}: {len(case.bundle.artifacts())} evidence artifact(s); no model was called.")
    for a in case.bundle.artifacts():
        _say(f"  [{a.ref}] {a.category} ({len(a.content)} chars)")
    if case.relationships:
        print("Recorded relationships:")
        for r in case.relationships:
            _say(f"  {r['source']} -> {r['target']} ({r['relationship_type']})")
    print("Limitations:" if case.bundle.limitations else "Limitations: none")
    for l in case.bundle.limitations:
        _say(f"  - {l}")
    return 0


def cmd_check_decisions(args) -> int:
    from .investigate import check_decisions

    if args.variant and not args.case:
        raise HyperAgileError("--variant needs --case: the evidence is verified only against a case folder.")
    ok, lines = check_decisions(Path(args.out), Path(args.case) if args.case else None,
                                Path(args.variant) if args.variant else None)
    for line in lines:
        _say(line)
    return 0 if ok else 1


def cmd_compare(args) -> int:
    from .compare import compare

    text = compare(Path(args.a), Path(args.b))
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)
    return 0


def cmd_init(args) -> int:
    root = Path(args.folder)
    if root.exists() and any(root.iterdir()):
        raise HyperAgileError(f"{root} is not empty.")
    for rel, text in CASE_TEMPLATE.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(f"Created a case template in {root}. Replace the placeholders with your evidence, then run:")
    print(f"  haq check-case {root}")
    return 0


def cmd_doctor(args) -> int:
    from ._engine.methodology import Methodology
    from ._engine.passes import validate_pass_definitions
    from .investigate import METHODOLOGY_DIR

    ok = True
    print(f"hyper-agile-quality-skill {__version__} (engine source {ENGINE_SOURCE_COMMIT})")
    print(f"Python {sys.version.split()[0]}: " + ("ok" if sys.version_info >= (3, 12) else "needs 3.12+"))
    ok &= sys.version_info >= (3, 12)
    methodology = Methodology.load(METHODOLOGY_DIR)
    validate_pass_definitions(methodology)
    print(f"Methodology: ok ({len(methodology.loop_activities())} Quality Loop activities) at {METHODOLOGY_DIR}")
    print(f"Demo case: {'ok' if DEMO_CASE.is_dir() and DEMO_RESPONSES.is_file() else 'missing'}")
    if args.ollama:
        from .providers import make_ollama

        provider = make_ollama(args.base_url or _env("HAQ_OLLAMA_URL", DEFAULT_OLLAMA_URL),
                               args.model or _env("HAQ_MODEL", "") or "(unset)", allow_remote=args.allow_remote)
        try:
            models = provider.list_models()
            print(f"Ollama at {provider.base_url}: reachable; {len(models)} model(s) installed")
            if provider.model in models or f"{provider.model}:latest" in models:
                print(f"Model {provider.model}: installed")
            else:
                print(f"Model {provider.model}: NOT installed (this tool never downloads models)")
                ok = False
        except HyperAgileError as exc:
            print(f"Ollama: {exc}")
            ok = False
    else:
        print("Ollama: not checked (pass --ollama to list installed models; no model is run)")
    return 0 if ok else 1


OVERWRITE_HELP = ("Replace a finished run's report, results, checks, run record and raw attempts. "
                  "Never overwrites decisions.yaml.")
ARCHIVE_HELP = ("If decisions.yaml may hold a person's decisions, rename it to decisions.superseded-<result>.yaml "
                "and start a fresh one. Without this flag such a run is refused.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="haq", description="Hyper-Agile Quality Skill: evidence-checked escaped-defect investigation.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("demo", help="Run the fictional case with scripted responses (no model).")
    d.add_argument("--variant", help="Apply a bundled evidence variant, e.g. missing-evidence.")
    d.add_argument("--out", help="Output folder (default haq-demo[-variant]).")
    d.add_argument("--overwrite", action="store_true", help=OVERWRITE_HELP)
    d.add_argument("--archive-decisions", action="store_true", help=ARCHIVE_HELP)
    d.set_defaults(func=cmd_demo)

    i = sub.add_parser("investigate", help="Investigate a case folder.")
    i.add_argument("case")
    i.add_argument("--out", required=True)
    i.add_argument("--variant", help="A variant folder to lay over the case.")
    i.add_argument("--scripted", help="Use scripted answers from this JSON file (no model).")
    i.add_argument("--answers-dir", help="Exchange prompts/answers with an agent through this folder.")
    i.add_argument("--model", help="Ollama model name (default $HAQ_MODEL).")
    i.add_argument("--base-url", help=f"Ollama URL (default $HAQ_OLLAMA_URL or {DEFAULT_OLLAMA_URL}).")
    i.add_argument("--context-tokens", type=int, help="Context window requested from Ollama (default 16384).")
    i.add_argument("--allow-remote", action="store_true", help="Allow a non-loopback model endpoint.")
    i.add_argument("--overwrite", action="store_true", help=OVERWRITE_HELP)
    i.add_argument("--archive-decisions", action="store_true", help=ARCHIVE_HELP)
    i.set_defaults(func=cmd_investigate)

    c = sub.add_parser("check-case", help="Load and list a case's evidence without any model.")
    c.add_argument("case")
    c.add_argument("--variant")
    c.set_defaults(func=cmd_check_case)

    k = sub.add_parser("check-decisions", help="Check that decisions.yaml reviews the result in an output folder.")
    k.add_argument("out")
    k.add_argument("--case", help="Also verify that this case folder's evidence is unchanged.")
    k.add_argument("--variant", help="The variant folder used for the run, with --case.")
    k.set_defaults(func=cmd_check_decisions)

    m = sub.add_parser("compare", help="Compare two investigation outputs.")
    m.add_argument("a")
    m.add_argument("b")
    m.add_argument("--output")
    m.set_defaults(func=cmd_compare)

    n = sub.add_parser("init", help="Create an empty case folder from a template.")
    n.add_argument("folder")
    n.set_defaults(func=cmd_init)

    o = sub.add_parser("doctor", help="Check the installation.")
    o.add_argument("--ollama", action="store_true", help="Also list models at the Ollama endpoint (no generation).")
    o.add_argument("--model")
    o.add_argument("--base-url")
    o.add_argument("--allow-remote", action="store_true")
    o.set_defaults(func=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except HyperAgileError as exc:
        print(f"Error: {mask_text(str(exc))}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - an unexpected error must not print evidence text or a traceback
        if os.environ.get("HAQ_DEBUG") == "1":
            raise
        print(f"Error: unexpected {type(exc).__name__}. Its message is not shown because it may quote evidence; "
              "set HAQ_DEBUG=1 to see the full traceback (it may contain evidence text).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
