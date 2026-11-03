# Architecture and the deterministic / model boundary

```
case folder ──► adapters ──► EvidenceBundle (engine type, masked)
                                   │
         ┌─────────────────────────┼─────────────────────────────┐
         ▼                         ▼                             ▼
  step 1-trace              step 2-validation              step 3-hypotheses
  engine pass               engine pass                    this skill's schema
  "1-traceability"          "3-validation-release"
         │ answer                  │ answer                        │ answer
         ▼                         ▼                               ▼
  engine guards             engine guards                  engine guard functions
  (apply_after_pass)        (apply_after_pass)             + H-* checks
         └──────────── checked results feed later steps ──────────┘
                                   │
                                   ▼
              report.md · results.json · checks.json · run.json · decisions.yaml
```

Code fixes the order of the steps, what each step sees, the output schema and every
check. The answer source fills in the schema and nothing else. Fields marked "Set by the
engine" in a schema are removed from what the answer source is asked for, and any value an
answer supplies for them is overwritten (tested in `tests/test_boundary.py`).

## Who is responsible for what

| Statement | Source | Enforced? | Tested how |
| --- | --- | --- | --- |
| Evidence loading, masking, limitations | `haq.adapters` | Yes | Fictional fixtures |
| Citation / link / quote / relevance checks | Engine guards + `haq.hypotheses` | Yes | Scripted answers, fictional case and variant |
| Hypotheses, confidence, proposals | Answer source | No — checked for provenance only | Scripted and mocked answers |
| Methodology rules not listed below (for example "name what worked", "separate pre- and post-release knowledge") | Prompt text and `SKILL.md` | No — instructions | Not testable deterministically |
| Accept / reject / investigate | A person, in `decisions.yaml` | Only a person; the tool never overwrites it and binds it to `result_sha256` | Fictional runs |
| Exchange answer binding | `haq.providers.ExchangeProvider` | Yes | Fictional runs |
| Answer sanitizing before anything is kept or shown | `haq.sanitize` | Yes, for parseable answers; unparseable text is never kept | Synthetic secrets |
| Decision integrity (`check-decisions`) | `haq.investigate.check_decisions` | Detects changed or inconsistent files and, with `--case`, changed evidence; not signed | Fictional runs |

## Rules applied by code

From hyper-agile-engine (vendored, unchanged):

| Rule | What it does |
| --- | --- |
| G-CITATION-UNRESOLVED | Removes a citation that names no provided evidence; lowers a strong level that relied on it |
| G-EVIDENCE-REF | A finding at CONFIRMED or STRONGLY SUPPORTED needs a citation that resolves and holds the identifiers it names |
| G-TRACE-SUPPORT | A DIRECT link needs a recorded relationship, a cited artifact of one item naming the other, or a quote found in a cited artifact; a critical signal is verified only if its source holds what it says |
| (inferred link ceiling) | An INFERRED link cannot be CONFIRMED |
| G-MATERIAL-DIFFERENCE | A test marked able to detect the failure with recorded material differences becomes UNCERTAIN; "cannot detect" without a stated difference becomes UNCERTAIN |
| G-UNASSESSED-RELEVANCE | A row that says detectability was not assessed cannot carry a decided answer |
| G-GAP-DERIVED | The regression-selection gap is derived from the test rows (SUPPORTED needs a DETECTING test that was not run) |
| G-ABSENCE | A claim that something did not exist or happen cannot be strong if the evidence that would show it was not collected |
| G-ACTIVITY-ESTABLISHMENT | A Quality Loop activity interpretation is never held at a strong level on citation provenance alone |
| G-REMEDIATION-TEST | A test known only from the fix is not pre-release coverage |

Added by this skill (`src/haq/hypotheses.py`):

| Rule | What it does |
| --- | --- |
| H-QUOTE-PROVENANCE | A strong hypothesis needs at least one supporting quote found verbatim (whitespace-normalized) in the source it cites — the engine's `bind_claims` check |
| H-CONTRADICTED | A contradicting quote found in its source caps the hypothesis at POSSIBLE CONTRIBUTING FACTOR and groups it under "contradicted" for review |
| H-POST-RELEASE-ONLY | Support only from post-release evidence (fix changes, production evidence) cannot keep a pre-release hypothesis strong |
| H-REGRESSION-GAP | A hypothesis anchored to regression selection drops to UNKNOWN unless the engine-derived gap is SUPPORTED |
| H-LAYER | The causal layer must be one of the methodology's six |
| H-PROPOSAL-BASIS | A proposal that addresses no SUPPORTED hypothesis, or an unknown hypothesis ID, is flagged |
| H-VAGUE-ACTION | The methodology's action-quality filter applied as a phrase list |

Before any of these rules runs, every answer is validated (`answer_problems`): confidence
values and activity statuses must be in the methodology's vocabulary (case and spacing aside),
and hypothesis and proposal IDs must be present and unique. An invalid answer is rejected — a
model gets one repair request, a saved answer is not used — never classified.

The report groups hypotheses as SUPPORTED (a verified supporting quote and not at the
weakest level), CONTRADICTED (a verified contradicting quote) or NOT ESTABLISHED.

## What no rule can establish

Whether a quote means what the hypothesis says; whether a test's description matches its
code; whether the provided evidence is complete; whether a hypothesis is the cause. These
remain human judgments.

## Reuse from hyper-agile-engine

Reused unchanged: the evidence types (`EvidenceBundle`, `EvidenceArtifact`) and file-stem
convention, credential masking, methodology loading and section slicing, the pass
definitions and schemas for traceability and validation, all guards, the quote-provenance
binder, the loopback check and the Ollama provider. Not reused: the engine's eight-pass
orchestrator and its remaining five passes, working-set compaction, run reconciliation,
review stores, engagement packages, benchmark tooling and every connector. Those modules
depend on each other heavily (the orchestrator's import closure is about 28,000 lines);
this project keeps a small, readable flow instead.
