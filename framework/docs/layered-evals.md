# Hands-on layered evaluation lab

This is application-authorization evaluation, not a model-accuracy benchmark. All records,
sessions and requests are fictional; listeners bind only loopback on random ports.
There is no URL option and no production scan. Existing mandatory tests and CI gates remain unchanged.

## Three layers and what you learn

1. **Deterministic prevention/regression:** server authorization prevents the leak; `npm run test:api`
   checks real HTTP responses. `npm run demo` demonstrates why two happy-path tests alone miss a critical gap.
2. **Offline dataset evaluation:** six fixed reference cases compare vulnerable and fixed versions.
   Offline means controlled examples with expected answers, not necessarily disconnected from the internet.
   Here the default command is also cloud-free. Expected results: vulnerable 4/6 correct, fixed 6/6.
   These small illustrative fractions are not statistical estimates of model quality.
3. **Online evaluation mechanism:** observe fresh individual requests after completion, using an invariant
   rather than dataset reference labels. Seeded cross-patient responses score zero. This catches disclosure
   after it occurred; it is NOT a security boundary. Promote a flagged case to a reviewed regression dataset.
   Local synthetic traffic demonstrates the mechanism, not a production deployment.

## Start locally (Node 22+, from framework/)

```sh
npm ci
npm run test:api
npm run evals:offline
npm run evals:online
```

Each `evals:offline` or `evals:online` command saves a uniquely named `evidence/layered-*/result.json`. No LangSmith client is constructed
unless `--upload-synthetic` is present, even if your global tracing environment is enabled.
`evals:online` without that flag runs the same scoring function locally. It does not configure a hosted evaluator.
Six sequential requests per version are made, then the local fixture shuts down.
The app's normal entry point remains secure; vulnerable code exists only in the isolated benchmark.

## Send synthetic evidence to LangSmith (optional)

This creates private workspace datasets/experiments or request traces. Review account billing/retention
before enabling online evaluators; automated evaluation can increase trace retention/cost.
Only case IDs, expected statuses/booleans and observed safe metadata are sent. No raw clinical records,
response bodies, source, cookies, session headers, API keys or model prompts are traced.
No model API or LLM judge is involved. Default SDK US endpoint applies; use your account's endpoint if different.

In macOS zsh, run the read line separately, paste the key at its prompt, then continue:

```sh
unset LANGSMITH_PROJECT LANGCHAIN_PROJECT LANGCHAIN_SESSION
export LANGSMITH_AGENT_ID="qe-demo" # use your exact Agent ID
export LANGSMITH_AGENT_ENVIRONMENT="local"
read -s "LANGSMITH_API_KEY?Paste your LangSmith API key: "
echo
export LANGSMITH_API_KEY
```

### Offline experiment comparison in the dashboard

```sh
npm run evals:offline -- --upload-synthetic
```

This creates a new uniquely named `synthetic-lab-authorization-...` dataset and two experiments
with prefixes `qe-vulnerable` and `qe-fixed` using the real LangSmith SDK `evaluate()`.
Every rerun intentionally creates another dataset, avoiding edits to existing examples.
Under **Datasets & Experiments**, open the printed dataset, select both experiments, and compare
`authorization_correct` and `no_unauthorized_disclosure`. Find `cross-a-b` and inspect status 200 versus 403.
The request output exposes safe facts (`authenticated`, `requestedOwnerMatches`, `returnedOwnerMatches`,
`dataReturned`, `httpStatus`), not a claim that the server emitted instrumented internal spans.
These are independent loopback harness observations, not cryptographically attested production evidence.

### Online evaluator on new request traces

```sh
npm run evals:online -- --upload-synthetic
```

In your agent's **Tracing → Local**, find root runs named `synthetic-lab-request`.
Each contains one request's safe input and observation. Existing `synthetic-qe-verification`
summary traces are different and must not be evaluated by this rule.

1. Open **Evaluators → + Evaluator → Code Evaluator**, select JavaScript.
2. Filter root run name to exactly `synthetic-lab-request`, and metadata `synthetic=true`.
3. Paste the `perform_eval(run)` function in `evals/online-authorization.mjs`, removing only `export`.
4. Test against existing fixed and vulnerable traces. Set sampling to 100% for this tiny demo;
   review plan availability and costs before saving. Do not silently enable this for production.
5. Save/apply, then rerun the online upload command to generate NEW traces. Alternatively use the
   UI's explicit backfill option. Confirm evaluator feedback appears; upload alone is not proof.

Expected feedback: `evidence_complete=1`; the two cross-patient vulnerable requests have
`no_unauthorized_disclosure=0` and `authorization_invariant=0`. Fixed requests score 1.
Missing/malformed evidence returns ONLY `evidence_complete=0`: interpret as **not evaluated**, not pass.
A normal successful trace icon means the function executed, not that authorization passed. Inspect scores.
The command's localMonitoringScores are local results, not proof the hosted rule ran.

```sh
unset LANGSMITH_API_KEY
```

## Verification boundaries

Local HTTP cases and grader tests are executable and checked in CI. Cloud orchestration is unit tested with
stubbed transport and real local requests. No developer key is bundled. No cloud dataset, dashboard feedback,
or hosted online evaluator is claimed verified until you run the commands and inspect your account.
The SDK/API may change; failed uploads must not be interpreted as completed evaluations.

## Interview walkthrough after hands-on completion

“I used deterministic API tests to enforce patient isolation. I then compared a vulnerable and fixed version
on a small labeled dataset. Finally, I evaluated new synthetic request traces using a no-cross-patient-disclosure
invariant. LangSmith let me inspect the failing example and compare outcomes; it did not replace authorization
or turn an after-the-fact alert into prevention.”

Say 'local online-monitoring simulation' until hosted evaluator feedback is visible. Do not call this a live
coding-agent evaluation, full clinical validation, or production monitoring experience.

Sources: [SDK evaluation](https://docs.langchain.com/langsmith/evaluate-llm-application),
[online code evaluators](https://docs.langchain.com/langsmith/online-evaluations-code),
[agent routing](https://docs.langchain.com/langsmith/log-traces-to-agent).
