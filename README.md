# hyper-agile-quality-skill

An agent skill and a small command-line tool (`haq`) for investigating escaped defects,
release issues and quality gaps from the evidence a team already has. It traces production
feedback back through release and testing evidence, shows what that evidence supports,
contradicts and leaves unknown, and proposes regression tests and preventive controls for a
person to review.

It applies the Hyper-Agile Quality Loop methodology (see [Relationship to the book](#relationship-to-the-book)).
Its deterministic evidence checks are reused from the author's hyper-agile-engine
(see [VENDORED.md](VENDORED.md)).

> **Status: beta (v0.1.0-beta), a first public pre-release.** Commands, file formats and
> output may change before a stable release. Licensed under the [MIT License](LICENSE); see
> [License](#license). Release notes: [docs/release-notes/v0.1.0-beta.md](docs/release-notes/v0.1.0-beta.md).

## What is supported in this version

| Capability | Status |
| --- | --- |
| Evidence from **local files** in a case folder (Markdown/text, issue YAML, JUnit XML, release YAML) | Supported |
| **Scripted replay** of the fictional demo case (`haq demo`), no model | Supported |
| **Agent answer exchange** (`--answers-dir`): the agent you work with answers each step, and `haq` checks every answer | Supported |
| Local model through **Ollama** (`--model`) | **Experimental.** Tested with a mocked HTTP transport and only partially exercised with a local model; no live-model investigation has been completed and no accuracy claim is made ([details](#local-model-configuration-experimental)) |
| Live connectors (Jira, GitHub, test management, documentation tools) | **Not included.** Export evidence to local files first |

## What it does — and what it does not

- It **checks**: every citation must name evidence that was provided; a traceability link is
  "DIRECT" only if an artifact records it; a quote must occur in the source it cites; a test
  counts as able to detect the failure only if its recorded condition matches; a
  regression-selection gap is derived from those test rows, never asserted; an absence
  ("no test existed") cannot be strong when that evidence was never collected; evidence
  produced after release cannot confirm a pre-release cause.
- It **proposes**: hypotheses, confidence levels, regression tests and controls come from an
  answer source — the agent you are working with (answer exchange), scripted answers for the
  demo, or, experimentally, a local model through Ollama. They are labelled as such everywhere.
- It **does not decide**: it never names a root cause, never claims model accuracy, never
  creates tickets, tests or monitors, and never sends evidence anywhere except the model
  endpoint you choose (loopback only, unless you explicitly allow another).

The checks confirm that an identifier, link or quote is where an answer says it is. They
cannot confirm that the evidence *means* what the answer says. Every report says so.

> **Masking cannot catch every secret.** `haq` masks credential-like values it recognizes, but a
> secret in a format no pattern knows — a word-only password, a customer name, an internal host name,
> personal data — passes through unchanged into prompts, reports, JSON files and `raw/` records.
> Review your evidence before giving it to any answer source, and review every output before you
> share, commit or publish it. Masking reduces risk; it does not make content safe to share.
> `haq init`, `haq check-case` and `haq investigate` print a short reminder of this on stderr
> (stdout and exit codes are unaffected); the agent skill raises it before anything else.

## Install

Requirements: Python 3.12+ and pip (or [uv](https://docs.astral.sh/uv/): `uv venv` and
`uv pip install` work the same way). Installing downloads the dependencies (pydantic, httpx,
PyYAML) from the Python package index.

```sh
git clone https://github.com/evgenytkachenko/hyper-agile-quality-skill.git
cd hyper-agile-quality-skill
python3.12 -m venv .venv && . .venv/bin/activate
pip install .                 # or: pip install -e ".[dev]" to run the tests
haq --version
```

## Quick start: replay the fictional demo (no model needed)

```sh
haq demo                                   # fictional case, scripted answers -> ./haq-demo
haq demo --variant missing-evidence        # same answers, less/changed evidence
haq compare haq-demo haq-demo-missing-evidence
```

The demo runs a fictional escaped defect ("Example Shop": a promo discount applied twice after
a cart quantity change) with **scripted answers written by hand — no model is called**. The
scripted answers deliberately include typical model mistakes so you can see the checks work.

Sample output (excerpt of [docs/sample-output/baseline/report.md](docs/sample-output/baseline/report.md)):

```markdown
| PR #318 → junit:ci-unit (validated by) | INFERRED (answered DIRECT) | STRONGLY SUPPORTED (answered CONFIRMED) | code-change.md | The CI results and the pull request show the same commit 4f2c1a9e. |

- Regression-selection gap [CHECK, derived from the rows above]: **UNCERTAIN**

### Contradicted or in conflict [CHECK]

**H5** [SCRIPTED] TC-211 was left out of the regression run; had it been selected, it would have caught the defect before release.

- Layer: Detection / escape gap; Quality Loop activity: Select regression intelligently
- Confidence [CHECK]: UNKNOWN (answered STRONGLY SUPPORTED) — citations and quotes checked; meaning not verified
- Supporting quote from `release:4.2.0` — VERIFIED_QUOTE: “Not run: TC-211”
- Contradicting quote from `tests.md` — VERIFIED_QUOTE: “Expected: The code SPRING10 is still shown as applied.”
```

And the effect of removing the test evidence, unlinking the incident and changing the
release note, with identical answers (excerpt of [docs/sample-output/comparison.md](docs/sample-output/comparison.md)):

```markdown
| Link SHOP-482 → SHOP-455 | DIRECT, CONFIRMED | INFERRED, STRONGLY SUPPORTED |
| Critical signal signal-002 | verified, CONFIRMED | not verified, UNKNOWN |
| Hypothesis H2 | SUPPORTED, CONFIRMED | NOT ESTABLISHED, UNKNOWN |
| Hypothesis H3 | SUPPORTED, STRONGLY SUPPORTED | NOT ESTABLISHED, POSSIBLE CONTRIBUTING FACTOR |
```

Each run writes `report.md`, `results.json` (answers as given and after checks),
`checks.json` (every rule that changed something), `run.json` (provenance and file hashes)
and `decisions.yaml` (empty, for a person to fill in, bound to this exact result), plus `raw/`
with a sanitized record of every answer attempt, including attempts that failed validation
(see "Answer records" below).
Attempts from earlier invocations of an unfinished run are kept too; `run.json` lists the
attempts of the invocation that finished. An exchange answer refused for its binding is not
copied to `raw/`; it stays, unchanged, in the answers folder.

## Output folders and human decisions

- A new or empty `--out` folder is used and marked as a haq output folder. Other non-empty folders are refused.
- An unfinished run (for example a step-by-step agent exchange) can be continued in the same folder.
- A finished run is replaced only with `--overwrite`, which replaces the report, results, checks, run record
  and raw attempts. It never overwrites `decisions.yaml`. The previous result is moved to `previous-run/`
  and removed only once the new run has written its result, so a failed run loses nothing.
- If `decisions.yaml` differs from the template the tool wrote, the run is refused and nothing is changed.
  `--archive-decisions` renames it to `decisions.superseded-<result>.yaml` and starts a fresh one.
- `decisions.yaml` names the `result_sha256` it reviews. `haq check-decisions <out> [--case <case>
  [--variant <variant>]]` fails when the decisions name a different result, when the result no longer
  recomputes from `results.json` and `run.json`, when `report.md`, `results.json` or `checks.json` differ
  from what the run wrote, or (with `--case`) when the case folder's evidence has changed. It also fails
  when `decisions.yaml` holds anything outside its template: another case, extra keys or fields, a
  repeated key (a merge key `<<` overridden in the same mapping counts as repeated), an item the
  result does not have, a decision other than accept, reject or investigate,
  a role or reason that is not plain text, or a checked status that differs from the result's. When any
  check fails, it reports that no decision applies and lists recorded decisions as not applicable. Without `--case` it says that the
  evidence was not checked, and it always lists what it does not verify (the `raw/` records, other
  `run.json` fields, the installed tool and methodology versions). Nothing is signed: these checks
  detect changed or inconsistent files, not a deliberate, consistent rewrite of all of them.

## Answer records (`raw/`)

Each attempt is kept as `raw/<step>.attempt-<n>.json`, written before the answer is validated:

- A parseable answer is decoded first, so JSON escapes cannot hide a token, then sanitized
  recursively: string values and keys are masked with the engine's patterns, and the whole value
  under a credential-like key (password, `db_password`, `password_hash`, secret, token, API key,
  auth, credential, cookie, session ID, connection string, DSN, ...) is replaced. Key names are matched in
  any casing and with `_`, `-`, `.` or space separators. Keys the step's answer schema does not
  define, and fields the engine sets itself, are then dropped at every depth (their number is
  recorded), because an abbreviated name such as `dbPass` cannot be told apart from an ordinary word. Only this sanitized form is kept, validated or shown; a repair
  prompt carries only the locations and messages of the problems, never answer content. Text outside the JSON object (reasoning, prose, code fences) is not kept; its length is.
- The answer is then conformed to the step's schema shape at every depth. A value of the wrong
  shape — an object or list where text is expected, a list of lists, text where an object or list is
  expected — has its content replaced by an `[OMITTED: expected ..., got ...]` marker, whatever its
  key names, and the answer is rejected (a model gets one repair request naming only the locations
  and shapes). This does not depend on recognizing credential names.
- An answer that cannot be parsed (malformed, truncated, not an object, nested too deeply, or
  containing unpaired surrogate escapes) cannot be sanitized
  safely, so its text is not kept or shown anywhere. The record holds only its length and the
  parser's reason, which names a position, never content. To diagnose such an answer, reproduce
  it with a model you control.
- Validation errors are reported by field and message, never with the offending value.
- With answer exchange, every invocation re-reads the saved answers of the steps already
  answered and records them again, so a finished three-step exchange typically shows
  `1-trace.attempt-1..3`, `2-validation.attempt-1..2` and `3-hypotheses.attempt-1`. These are
  repeated records of the same answers, not failed attempts; each record's `status` says whether
  it was accepted (`parsed`) or not.

## Investigate your own case (agent answer exchange)

1. Create a case folder and put your local evidence in it (see
   [Supported evidence](#supported-evidence-connectors)):

   ```sh
   haq init my-case          # creates a template with placeholders; replace them
   haq check-case my-case    # loads and lists the evidence and what is missing; no model
   ```

2. Run the investigation with an answers folder. `haq` writes the first step's prompt and stops
   (exit code 3):

   ```sh
   haq investigate my-case --out my-result --answers-dir my-result-exchange
   ```

3. The answerer (normally the coding agent using the skill below) reads
   `my-result-exchange/1-trace.prompt.md`, whose first line holds the step's **binding**, and
   saves `my-result-exchange/1-trace.answer.json` as
   `{"binding": "<binding>", "answer": <one JSON object matching the schema in the prompt>}`.
4. Run the same command again. Repeat for steps `2-validation` and `3-hypotheses`; after the
   third answer, `haq` checks everything and writes the report to `my-result/`.

The binding ties each answer to the exact prompt, evidence, methodology and earlier answers, so
an answer written for different evidence is refused, not reused. Use only evidence you are
allowed to process with the chosen answer source: with answer exchange, the evidence is read by
whatever model runs the agent. Keep real case folders out of version control (the default
`.gitignore` excludes `cases/`).

Experimental alternative: `haq investigate my-case --out my-result --model <model>` asks a
local Ollama model instead (see [Local model configuration](#local-model-configuration-experimental)).

## Use it as an agent skill

`skill/hyper-agile-quality/SKILL.md` is a skill file for coding agents that support the
`SKILL.md` format. The skill is in the repository, not in the installed Python package, so
install it from your clone. For example, for Claude Code:

```sh
mkdir -p ~/.claude/skills
cp -R skill/hyper-agile-quality ~/.claude/skills/      # or a project's .claude/skills/
```

If you run Claude Code with `CLAUDE_CONFIG_DIR` set, its user skills live in that folder
instead of `~/.claude`: copy the skill to `"$CLAUDE_CONFIG_DIR/skills/"`.

Make sure `haq` is on the agent's PATH (activate the virtual environment, or give the agent
the full path to `.venv/bin/haq`). Invoke it with a request such as "investigate why
SHOP-482 escaped" or `/hyper-agile-quality my-case`.

What to expect when you invoke it:

- The agent first explains that masking cannot catch every secret and that you must review
  inputs and outputs, then asks **which answer source to use** (itself through answer exchange,
  or the experimental local model) and **for your agreement** that the chosen source may read the
  evidence. You can answer both up front, for example "use answer exchange with you as the
  model; I agree you may read this evidence".
- The agent answers from the prompts `haq` writes and the case evidence. It must not use the demo's
  scripted answers that ship with the package; it may read the package source to troubleshoot,
  and should say so.
- Claude Code asks before running shell commands. Approving each `haq` command when asked is the
  safest choice. If you add allow rules to reduce prompts, keep them narrow and temporary (a
  project or session setting rather than your user settings), for example
  `Bash(haq check-case:*)`, `Bash(haq investigate:*)` and `Bash(haq check-decisions:*)`.
  Understand what they permit: `haq investigate` writes output folders, can replace a finished
  run with `--overwrite`, and with `--model --base-url ... --allow-remote` would send the evidence
  to a non-local endpoint. A broad rule such as `Bash(haq:*)` covers all of that, and rules for
  general shell commands cover far more; avoid them.

The skill tells the agent how to build the case folder, which answer source to use, how to
explain the report, and that it must stay read-only and leave decisions to people. Those
are **instructions**: unlike the checks in `haq`, nothing enforces them. With
`--answers-dir`, the agent itself answers the three steps and its answers go through the
same checks (the evidence then reaches whatever model runs the agent — ask first). Each answer
file must be `{"binding": "<digest from the prompt>", "answer": {...}}`; the binding covers the
exact request, the evidence files, the methodology and every earlier answer, so an answer
written for different evidence or after an earlier answer changed is refused, not reused.

## Supported evidence (connectors)

| Input | Status | Tested with |
| --- | --- | --- |
| Markdown / text files by name (`production-issue.md`, `requirements.md`, `code-change.md`, `fix-change.md`, `tests.md`, `ci.md`, `release.md`, `production-learning.md`, ...) — the engine's case-folder convention | Implemented | Fictional fixtures |
| `issues/*.yaml` issue records; `links` become recorded relationships | Implemented | Fictional fixtures |
| `test-results/*.xml` JUnit XML | Implemented | Fictional fixtures |
| `releases/*.yaml` release records (work items, validation runs, approval note) | Implemented | Fictional fixtures |
| Variant overlay (remove / replace files) | Implemented | Fictional fixtures |
| Jira, GitHub, Testiny, Notion, MCP, REST | **Not included.** They exist in hyper-agile-engine but pull in its collector and transports; not vendored, not tested here | — |
| Export through an agent's own tools | Instructions only (SKILL.md) | Not tested |

`haq` has no connector to any live system and contacts none; only the answer source you choose
receives evidence (an agent through answer exchange, or a local Ollama endpoint). Credential-like strings
in free text (titles, descriptions, comments, notes, test messages and all answers) are masked
with the engine's rules before they reach a model, an output file or a message. Identifiers
(file paths, case and variant IDs, issue keys, link fields, release versions) that look like
credentials, or contain non-ASCII or control characters, are refused instead, because a masked
or look-alike identifier could collide with another. Every evidence ID and file name must be
unique, case aside. Hypothesis and proposal IDs must be short ASCII names (`H1`, `T2`) and
unique, case aside. An unexpected internal error prints only its type, never its message or a
traceback, because either may quote evidence (`HAQ_DEBUG=1` shows the traceback). See
[docs/connectors.md](docs/connectors.md).

## Local model configuration (experimental)

| Setting | Flag | Environment | Default |
| --- | --- | --- | --- |
| Ollama URL | `--base-url` | `HAQ_OLLAMA_URL` | `http://localhost:11434` |
| Model | `--model` | `HAQ_MODEL` | none (required) |
| Context window | `--context-tokens` | `HAQ_CONTEXT_TOKENS` | 16384 |
| Timeout (s) | — | `HAQ_TIMEOUT_SECONDS` | 600 |
| Temperature | — | `HAQ_TEMPERATURE` | 0.1 |
| Thinking toggle (models that support it) | — | `HAQ_THINK` | unset |
| Non-loopback endpoint | `--allow-remote` | — | refused |

`haq` never installs Ollama or downloads models. `haq doctor --ollama` lists installed
models (it does not run one). See [docs/local-model.md](docs/local-model.md).

**Model testing status:** the Ollama integration is tested with a mocked HTTP transport and has
been only partially exercised with a local model. Two trials on the fictional demo case, with one
locally installed 8-billion-parameter model and a separate bounded test harness, were both
stopped by safety checks: the first by the harness's own model-identity check (an error in the
harness, since corrected) before any answer, the second by a memory-pressure limit after two of
the three steps had been answered. **Neither trial completed the investigation; no live-model
validation has been completed, and no claim is made about any model's accuracy, usefulness,
speed or memory use on this task.** See [docs/local-model.md](docs/local-model.md#testing-status).

## How it works

Three steps, each answered by the chosen source and then checked by code:

1. **Trace** — the engine's traceability pass: links from the production problem back to the
   originating work, timeline, pre- vs post-release knowledge, critical signals.
2. **Testing and release evidence** — the engine's validation pass: test relevance against the
   failing condition, what CI demonstrated, signals available at release.
3. **Hypotheses** — competing explanations with supporting and contradicting quotes,
   unknowns, what worked, proposed regression tests and controls.

See [docs/architecture.md](docs/architecture.md) for every rule and where it comes from.

## Tests

```sh
pip install -e ".[dev]"
pytest
```

271 tests: adapters, the demo and its variant (pinned outcomes and committed sample output),
the boundary between answers and checks (engine-set fields ignored, mocked Ollama including
repair, cut-off and locality cases), exchange bindings (changed evidence, changed earlier
answers), decision protection, secret handling at every input and output, answer vocabulary,
duplicate IDs, ambiguous evidence identities, sanitized answer records (sensitive keys,
escaped tokens, nested values, malformed and truncated answers, repair prompts), decision
integrity checks, CLI behavior and
vendored-file hashes.
The test suite verifies behavior with fictional fixtures, scripted answers and mocked model
traffic only. For the two partial local-model trials, see the model testing status under
[Local model configuration](#local-model-configuration-experimental).

## Limitations

- No live connectors; evidence must be exported to local files first.
- The checks are lexical and structural. They cannot tell whether a verified quote supports
  the claim made with it, whether a test's description matches what its code does, or whether
  the evidence provided is complete.
- Only English wording is anticipated by some engine rules (for example absence detection).
- Long artifacts are truncated (20,000 characters each) and the cut is reported.
- A single fictional case and one variant are included; they show behavior, not usefulness on
  real incidents.
- Small local models may fail the JSON schemas or the confidence vocabulary; one repair attempt
  is made, then the run stops. Every attempt is kept, sanitized, under `raw/`; an unparseable
  answer's text is not kept.
- Masking cannot catch every secret. It uses the engine's patterns and credential-like key names;
  a secret in a format they do not recognize, written as ordinary text under an ordinary field (for
  example a word-only password inside a finding), and any personal or confidential information that
  is not credential-shaped, is not masked. Review inputs before running and outputs before sharing.

## Relationship to the book

This project applies the methodology of *Hyper-Agile Testing* as captured in the author's
hyper-agile-engine methodology files (`src/haq/_methodology/`): the ten Quality Loop
activities, the causal layers, the evidence confidence levels, the hindsight-bias safeguards
and the action-quality rules. It does not reproduce text from the book, quote it, or refer to
specific chapters. It is not a substitute for the book. See [docs/book.md](docs/book.md).

## Related project

hyper-agile-engine — the larger assessment engine this project reuses checks from.

## Feedback

Report problems and suggestions as [GitHub issues](https://github.com/evgenytkachenko/hyper-agile-quality-skill/issues). Describe the problem with
the fictional demo case or with made-up evidence: **do not post real evidence, reports, `raw/`
records or anything confidential**, because issues are public.

## License

MIT License, copyright (c) 2026 Evgeny Tkachenko. See [LICENSE](LICENSE).

The MIT License covers everything in this repository: the code, the documentation, the agent
skill (`skill/`), the fictional example case and sample output, and the methodology files in
`src/haq/_methodology/`. It also covers the files in `src/haq/_engine/` and
`src/haq/_methodology/` that were copied from the author's hyper-agile-engine
([VENDORED.md](VENDORED.md)); applying MIT here does not change the terms of the engine
repository itself.

The license covers the methodology files as written. It does not cover the book
*Hyper-Agile Testing*, which is not included (see [docs/book.md](docs/book.md)).

Dependencies (pydantic, httpx, PyYAML and the packages they require) are not included in this
repository or in its packages. They are installed separately and keep their own licenses.
