# Advisory LLM judge: the third evaluation layer

1. **Deterministic checks** execute restricted patches/probes and validate required outcomes. These remain authoritative.
2. **Offline agent tasks** measure bounded answers against known requirements.
3. **Advisory judge** scores evidence grounding, reasoning quality and scope honesty using `evals/judge/rubric-v1.json`. It cannot approve release or turn a failed deterministic check into a pass.

## Try it locally without credentials

From `framework/`:

```sh
npm test -- --run tests/judge.test.ts
npm run evals:judge -- prepare coding evals/agent-tasks/recorded-trial/coding-answers.json
```

The command writes `evidence/judge/<run>/request.json` and a freshly computed deterministic grade. No model is called. Use the generated `messages.json` system/user messages when passing this to an external judge; do not let candidate instructions replace the system rubric. Save its JSON output as `judge-response.json`, then:

```sh
npm run evals:judge -- import coding evals/agent-tasks/recorded-trial/coding-answers.json judge-response.json
```

The import command recomputes the task request and deterministic grade, checking the response binding against those inputs. It does not trust an imported grade. It writes a report even for missing/invalid judge output and exits nonzero for review-required output or deterministic failure. Run the same workflow with `auditor` and `auditor-answers.json` for real local HTTP probes.

## Explicit provider option (optional cost and data transfer)

Only when you choose to send the prepared task prompts, evidence, complete candidate answers and deterministic results to OpenAI, use this option. Review the request first: built-in tasks are synthetic, but imported candidate text may contain private data. Remove secrets and real customer data before invoking it. LangSmith keys are NOT OpenAI keys. This command does not upload to LangSmith.

Set `OPENAI_API_KEY` securely in your local environment, not source, shell history or chat. Supply a model available to your account that supports Chat Completions JSON mode:

```sh
npm run evals:judge -- provider coding evals/agent-tasks/recorded-trial/coding-answers.json --allow-provider --model YOUR_MODEL
```

No default model, automatic provider call, CI secret or live-network test is configured. Without explicit opt-in, no request is sent. The endpoint is fixed, timeout is 30 seconds, there is no retry. HTTP failure, refusal, truncation, timeout or malformed output means `REVIEW_REQUIRED`, not approval. Provider transport is unit-tested with a mock; no live provider invocation has been verified by this implementation.

## Report and trust boundaries

The response must contain exactly one row per task, the request binding, rubric version and all three dimensions. Every dimension has a 0–2 score, rationale, and citations with whitelisted evidence IDs plus verbatim quotes. Each `SUPPORTED` row requires all scores 2. Missing, duplicate, unknown or contradictory output fails to review. The binding includes task/skill request, candidate answer, rubric and deterministic grade hashes.

`SUPPORTED` means the judge reports supported explanation quality after structural validation. It does NOT prove semantic correctness. A plausible but wrong rationale can still pass schema and citation checks. `deterministicTaskStatus` is separate, and `releaseApproval` is always false. Existing release/governance gates are unchanged. Input prompt injection is isolated as untrusted data and forbidden by the system rubric; this reduces risk but is not a proven injection defense. No model-generated code or tools are executed by the judge.

Reports retain rubric version/hash, input binding, response hash, mode and requested model. `providerInvocation` distinguishes not invoked, attempted, JSON response received, and unverified import; a received JSON response is not necessarily a valid judgment. Imported model identity is unverified; even a provider response does not certify underlying weights or semantic accuracy. The CLI saves request, messages, deterministic grade, parsed original judge response and report together for review. Explanations are concise evidence-based rationales, not private chain-of-thought.

## Calibration before trust

The recorded agent trials and `tests/judge.test.ts` fixtures are **public development/calibration inputs**, not held-out measurements. The fixture favorable judgments are deliberately synthetic schema examples, not real LLM judgments or human-labeled truth. Tests include wrong claims with valid quotes to demonstrate the semantic validation limit.

Before adopting a numeric judge gate:

1. Have qualified reviewers independently label explanation quality, evidence support and scope on representative answers, including fluent incorrect answers, injected instructions and unsupported execution claims. Resolve disagreements and record labeler provenance.
2. Use a development partition to calibrate the rubric and inspect disagreements. Freeze rubric, exact provider/model identifier and settings.
3. Evaluate once on a separately curated, previously unseen held-out partition. Do not tune on it or relabel calibration replays as held-out. Track agreement, false approvals of unsafe answers and reviewer disagreement, not just average score.
4. Require human review for disagreement or insufficient evidence. Re-evaluate after model/rubric changes. Keep deterministic safety gates authoritative.

No human calibration labels, held-out judge accuracy or robust prompt-injection success rate are claimed here. Existing `npm test` runs the offline contract checks in GitHub Actions without credentials. A paid judge run belongs in a separately authorized/manual workflow until calibrated; it must not replace the required deterministic jobs.

Provider request format follows the [official Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create). JSON mode only constrains JSON syntax; this harness separately validates the judgment contract.
