# Optional LangSmith observability

LangSmith observes this framework; it does not decide whether tests are correct. LangChain is not required. The official `langsmith` SDK is installed by `npm ci`. No account was created and no live traces have been uploaded in this implementation.

After `npm run demo`, run `npm run trace:summary` for local-only allowlisted summary output. Ambient `LANGSMITH_TRACING=true` alone does not activate our wrapper. Raw evidence, source code, patient records, credentials, agent prompts and logs are excluded.

If you choose to send the synthetic stage names, exit codes and test counts to your LangSmith project, configure `LANGSMITH_API_KEY` securely in your local environment and optionally `LANGSMITH_PROJECT`, then run:

```sh
npm run trace:summary -- --upload-synthetic-summary
```

Use your account's correct regional `LANGSMITH_ENDPOINT` if applicable. Never commit a key. Confirm the resulting run in your dashboard: SDK completion alone is not independent delivery verification. No live dashboard check was performed here. Unit tests use a mocked adapter and verify opt-in, field allowlisting, nested stage calls and flush failure handling.

This traces deterministic verification stages, not hidden reasoning or complete Claude/Codex internals. Real model traces remain separate in `auditor/reports/` when a supported host run succeeds. The read-only Codex CLI attempt here failed during app-server startup; it is not an agent-evaluation success.

Sources: [custom instrumentation](https://docs.langchain.com/langsmith/annotate-code), [data masking](https://docs.langchain.com/langsmith/mask-inputs-outputs).
