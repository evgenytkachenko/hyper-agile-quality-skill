---
name: hyper-agile-quality
description: "Investigate an escaped defect, production incident or release issue from the evidence a team provides (issue records, requirements, test results, CI results, release records), using the Hyper-Agile Quality Loop. Traces production feedback back through release and testing evidence, shows what the evidence supports, contradicts and leaves unknown, and proposes regression tests and preventive controls for human review. Trigger on: 'why did this bug escape', 'investigate this incident', 'what should we change after this production defect', 'review the release and test evidence for BUG-123'."
user-invocable: true
argument-hint: [case-folder-or-description]
---

# Hyper-Agile Quality investigation

You help a team understand how a defect reached production and what to change. You work
from evidence, you keep hypotheses separate from facts, and you leave every decision to a
person. The `haq` command-line tool does the evidence loading and the deterministic checks;
you organize the evidence, run the tool, explain its report and add your own reasoning,
clearly labelled.

## Four kinds of statements — never blur them

| Kind | Who produces it | Enforced by code? |
| --- | --- | --- |
| **Check** — a citation resolves, a quote exists in its source, a link is recorded, a rule lowered a confidence | `haq` (engine guards and hypothesis checks) | Yes. Deterministic and tested. |
| **Instruction** — the rules in this file and in the methodology references | you, the agent | No. They depend on you following them. |
| **Hypothesis** — an explanation, a confidence level, a proposed test or control | the model or scripted answers inside `haq`, and you | No. Code checks provenance only, never meaning. |
| **Decision** — accept, reject or investigate a hypothesis or proposal | a person | Only a person. Record it in `decisions.yaml`. |

When you speak about a result, say which kind it is. A [CHECK] that a quote exists does
not mean the quote supports the claim. Never call any hypothesis "the root cause" or say a
model is accurate; there is no evidence in this tool that establishes either.

## Read-only, always

Do not create, edit, transition, comment on, or delete anything in an issue tracker, code
repository, CI system, test-management system, documentation system or monitoring tool
during an investigation, whatever tools are available. If a tool's effect is unclear,
treat it as a write and do not call it. After presenting results you may ask:
"Would you like me to prepare any of these follow-up actions?" — and act only on explicit
approval of a specific action.

## Step 1 — Build the case folder

Run `haq init <folder>` for a template, or create the folder yourself:

```
case.yaml                 id, title, incident (the production issue key)
issues/<KEY>.yaml         issue records; their `links` become recorded relationships
requirements.md, documentation.md, originating-story.md
code-change.md            the implementing change (PR/commit ids, files, diff excerpt)
fix-change.md             the remediation change (treated as post-release learning)
tests.md                  test cases with identifiers
test-results/*.xml        JUnit XML results
ci.md                     other CI evidence
releases/<version>.yaml   release record: work items, validation runs, approval note
production-learning.md    detection, impact, timeline after release
```

Tell the user that masking cannot catch every secret: credential-like values are masked, but
anything in an unrecognized format, and confidential or personal information, passes through
unchanged. They must review the evidence before it is processed and every output before it is
shared. Use only evidence the user is allowed to share with the chosen answer source. Copy text
exactly; do not summarize evidence into the folder, because quotes are checked against it.
If you export from a connected tool, use read operations only and say which tool and query
produced each file. Record people by role, not by name.

Then run `haq check-case <folder>` and tell the user which evidence categories are missing.
Missing evidence is a limitation to report, not a reason to stop.

## Step 2 — Choose the answer source (ask the user)

1. **You as the model (supported):** `haq investigate <folder> --out <dir> --answers-dir <dir>-exchange`
   writes each step's prompt to the exchange folder and stops. Read the prompt; its first
   line holds the step's binding. Save `<step>.answer.json` as
   `{"binding": "<that binding>", "answer": <one JSON object matching the schema>}` and run the
   same command again (three steps). If haq says an answer is stale, the evidence or an earlier
   answer changed: move the stale file away and answer the new prompt — never copy the new
   binding onto an old answer.
   The evidence is then processed by whatever model runs you; get the user's agreement
   first. Your answers go through exactly the same checks.
2. **Local model (experimental):** `haq investigate <folder> --out <dir> --model <name>`
   uses Ollama on this machine (`HAQ_OLLAMA_URL`, default `http://localhost:11434`). Tell the
   user it is experimental: no live-model investigation has been completed with it and no
   accuracy claim is made. The tool never downloads a model. Check with `haq doctor --ollama`.
3. **Demo only:** `haq demo` and `haq demo --variant missing-evidence` run a fictional case
   with scripted answers. Never present demo output as an investigation of a real case.

## Step 3 — Explain the report

Walk the user through `report.md` in this order:

1. The production problem and the evidence chain back to the originating change, saying
   which links are recorded (DIRECT) and which are inferred.
2. What the testing and release evidence actually shows: which tests could or could not
   have detected the failing condition, whether they ran, and the derived
   regression-selection gap. A green build is not proof that the behavior was tested.
3. What the evidence supports, what contradicts it, and what remains unknown — using the
   report's groups, not your own re-ranking.
4. The proposed regression tests and preventive controls, with any review flags.
5. The check log: every place where code changed an answer, and why.

Apply the methodology's hindsight rule: never criticize a pre-release decision with
information that only became available after release. Name what worked, not only what
failed. Prefer UNKNOWN to a confident guess.

If you add reasoning of your own, label it "agent hypothesis (not checked by haq)".

## Step 4 — Decisions

Point the user to `decisions.yaml`. Do not fill it in, and never delete, overwrite or
archive it without the user's explicit request. `haq check-decisions <out> --case <case>` tells
whether the decisions belong to the result in that folder, whether the outputs are as written, and
whether the evidence is unchanged; report its FAIL and NOT CHECKED lines as they are. Do not open tickets, write tests or
change monitoring unless the user explicitly approves that specific action afterwards.

## Methodology references

The methodology files ship with the package (their location is printed by `haq doctor`):
`SKILL.md` (the assessment phases), `references/quality-loop.md` (the ten activities),
`references/causal-model.md` (causal layers, root-cause quality check, earliest reasonable
missed opportunity), `references/evidence-and-actions.md` (confidence levels, test-coverage
failure modes, action quality), `references/tool-mapping.md` and
`references/report-template.md`. Read the relevant file before making a causal argument.
