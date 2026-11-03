# Local model (Ollama)

## Setup

1. Install Ollama yourself and start it.
2. Install a model you are allowed to use: `ollama pull <model>`. `haq` never downloads one.
3. Check: `haq doctor --ollama --model <model>` (lists installed models; runs no generation).
4. Run: `haq investigate <case> --out <dir> --model <model>`.

## Settings

| Flag | Environment | Default | Notes |
| --- | --- | --- | --- |
| `--base-url` | `HAQ_OLLAMA_URL` | `http://localhost:11434` | |
| `--model` | `HAQ_MODEL` | — | required |
| `--context-tokens` | `HAQ_CONTEXT_TOKENS` | 16384 | sent as `num_ctx`; Ollama truncates longer prompts silently, so `haq` warns above 90% |
| — | `HAQ_TIMEOUT_SECONDS` | 600 | per call |
| — | `HAQ_TEMPERATURE` | 0.1 | |
| — | `HAQ_THINK` | unset | `true`/`false` for models with a thinking toggle |
| `--allow-remote` | — | off | required for any non-loopback endpoint |

Estimated at four characters per token, the demo case's prompts are about 4,800, 6,100
and 9,900 tokens for the three steps (before the answer); real cases are larger.

## Behavior

- Each step sends one chat request with the step's JSON Schema as Ollama's `format`.
- An answer that does not match the schema, or uses a confidence or status outside the
  methodology's set, gets one repair request; a second failure stops the run.
- Every attempt is recorded in `raw/<step>.attempt-<n>.json` before it is validated: the
  decoded, sanitized answer restricted to the step's schema fields, or for an unparseable answer only its length and the parser's reason
  (its text is not kept, because it cannot be sanitized safely). Repair prompts quote the field
  and message of each problem, never the answer's values.
- An answer cut off at the output limit is never used.
- A loopback endpoint is contacted without any proxy from the environment (engine behavior).
- `localhost.example.com` and similar names are not treated as local.

## Testing status

Tested only with a mocked HTTP transport (`tests/test_boundary.py`): request shape, schema,
context size, repair, cut-off and locality refusal. **Not run against a live model.** No
statement about any model's accuracy or usefulness on this task is supported by this
project's tests. Speed and memory use of this three-step flow have not been measured.
