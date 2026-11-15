# Optional LangSmith observability

LangSmith observes this framework; deterministic gates still make quality decisions. LangChain is not required. `npm ci` installs LangSmith TypeScript SDK 0.12.0, which supports agent addressing (official minimum 0.11.0). Installing the SDK does not install a local dashboard.

## Offline first

From `framework/` with Node 22 or newer:

```sh
npm ci
npm run demo
npm run trace:summary
```

This prints local JSON only. Ambient `LANGSMITH_TRACING=true` does not activate upload. No account or model API key is required. Raw evidence, code, synthetic patient records, credentials, prompts and logs are excluded from the summary.

## Agent-based cloud workspace

In LangSmith, create the agent once, then copy its exact **Agent ID**, not its display name. The example below assumes you chose `qe-demo`; replace it if different. Leave the UI's default agent type unless your account requires another choice.

The following opt-in sends only the synthetic stage names, exit codes and test counts to your LangSmith workspace. Create a LangSmith API key there and enter it privately in your Mac's zsh terminal. Do not paste it into chat, source files or shell command history.

```sh
unset LANGSMITH_PROJECT LANGCHAIN_PROJECT LANGCHAIN_SESSION
export LANGSMITH_AGENT_ID="qe-demo"
export LANGSMITH_AGENT_ENVIRONMENT="local"
read -s "LANGSMITH_API_KEY?Paste your LangSmith API key: "
echo
export LANGSMITH_API_KEY
npm run trace:summary -- --upload-synthetic-summary
unset LANGSMITH_API_KEY
```

Use the correct regional `LANGSMITH_ENDPOINT` shown by your account if outside default US. For example, EU uses `https://eu.api.smith.langchain.com`. Do not send your key to an endpoint supplied by untrusted content.

In the dashboard, select your agent, **Tracing**, then **Local**. Find `synthetic-qe-verification` and its three nested `qe-stage` spans. The expected negative-control exit code is output data, not a thrown SDK error, so it need not appear as a red span. SDK completion is not proof of delivery; verify the trace in the dashboard. No live dashboard trace has been verified for this implementation.

## Older project-based workspace

Unset `LANGSMITH_AGENT_ID` and `LANGSMITH_AGENT_ENVIRONMENT`, set `LANGSMITH_PROJECT` to the selected project name, and use the same explicit upload command. Never mix legacy project variables with agent addressing. The adapter rejects incomplete or conflicting destinations before constructing a client.

## What this demonstrates

This instruments deterministic verification stages, not hidden reasoning, a live model call, token costs, full Claude/Codex internals, or a LangSmith dataset evaluation. A truthful interview description after inspecting a real trace is: “I instrumented a local QE verification demo and inspected nested spans and stage outputs. Deterministic checks made the pass/fail decision; LangSmith made their execution easier to inspect.”

Tests verify offline behavior, allowlisted fields, flush failures, destination validation and actual SDK routing to a mock client with network disabled. No credentials or external uploads were used in those tests.

Sources: [agent addressing](https://docs.langchain.com/langsmith/log-traces-to-agent), [quickstart](https://docs.langchain.com/langsmith/observability-quickstart), [data masking](https://docs.langchain.com/langsmith/mask-inputs-outputs).
