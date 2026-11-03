"""Where step answers come from.

Every provider implements the engine's ``ModelProvider`` interface, so the investigation
code cannot tell them apart; the report and run record always say which one was used.

- ``scripted``  fixed answers read from a JSON file. Not a model. Used for the no-model
                demo and for regression tests. Every report made from it says SCRIPTED.
- ``ollama``    a local model through the engine's Ollama provider. Refuses a non-loopback
                endpoint unless explicitly allowed.
- ``exchange``  file exchange with an agent (for example a coding assistant acting as the
                model). Writes each prompt to a folder and reads the answer the agent saves
                next to it. Whatever model the agent uses sees the evidence.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from ._engine.errors import ConfigError, ProviderError
from ._engine.network import is_loopback_host
from ._engine.providers.base import EXTERNAL, LOCAL, ModelProvider
from ._engine.providers.ollama import OllamaProvider


class AwaitingAnswer(ProviderError):
    """The exchange provider wrote a prompt and has no answer for it yet."""

    kind = "awaiting_answer"


class ScriptedProvider(ModelProvider):
    """Returns pre-written answers by step key. Never contacts anything."""

    name = "scripted"
    location = LOCAL
    label = "SCRIPTED RESPONSES (not a model)"

    def __init__(self, path: Path):
        self.path = Path(path)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("responses"), dict):
            raise ConfigError(f"{path} must be a JSON object with a 'responses' mapping of step key to answer.")
        self.description = str(data.get("description", ""))
        self.responses = data["responses"]
        self.model = f"scripted:{self.path.name}"
        self.current_step = ""

    def list_models(self) -> list[str]:
        return [self.model]

    def check_ready(self) -> None:
        return None

    def generate(self, system_prompt: str, user_prompt: str, *, json_schema: dict | None = None) -> str:
        answer = self.responses.get(self.current_step)
        if answer is None:
            raise ProviderError(f"The scripted responses in {self.path.name} have no answer for step "
                                f"'{self.current_step}'. A missing answer is never filled by a model.")
        return answer if isinstance(answer, str) else json.dumps(answer)


class StaleAnswer(ProviderError):
    """A saved exchange answer is not bound to the request it is being used for."""

    kind = "stale_answer"


def request_binding(step: str, system_prompt: str, user_prompt: str, json_schema: dict | None, inputs: dict) -> str:
    """Digest of exactly what an answer is an answer to.

    The user prompt already contains the evidence, its index and limitations, the case title and the checked results
    of earlier steps; `inputs` adds the evidence file hashes, methodology hashes, tool version and the digest of every
    earlier accepted answer, so that a changed earlier answer invalidates every later one even if its checked result
    happens to read the same."""
    payload = {"step": step, "system": system_prompt, "user": user_prompt, "schema": json_schema, "inputs": inputs}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def short(value: object) -> str:
    """A value from an answer file is shown only if it is a digest; anything else could be a credential."""
    return f"{value[:12]}…" if isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value) \
        else "(not a digest)"


class ExchangeProvider(ModelProvider):
    """File exchange with an agent, one step at a time.

    For each step it writes <dir>/<step>.prompt.md and <dir>/<step>.request.json (which holds the binding), and reads
    <dir>/<step>.answer.json, which must be {"binding": "<the binding>", "answer": {...}}. An answer without the
    current binding is refused, never used; the files are left as they are for the person or agent to replace."""

    name = "exchange"
    location = EXTERNAL  # the agent's own model may be anywhere
    label = "AGENT ANSWERS (unverified model output from the invoking agent)"

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.model = "agent-exchange"
        self.current_step = ""
        self.binding_inputs: dict = {}
        self.bindings: dict[str, str] = {}

    def list_models(self) -> list[str]:
        return [self.model]

    def check_ready(self) -> None:
        return None

    def generate(self, system_prompt: str, user_prompt: str, *, json_schema: dict | None = None) -> str:
        step = self.current_step
        binding = request_binding(step, system_prompt, user_prompt, json_schema, self.binding_inputs)
        prompt = self.folder / f"{step}.prompt.md"
        answer = self.folder / f"{step}.answer.json"
        wrapper = f'{{"binding": "{binding}", "answer": <one JSON object matching the schema>}}'
        prompt.write_text(
            f"<!-- haq exchange: step {step}; binding {binding} -->\n"
            f"<!-- Save {answer.name} as exactly: {wrapper} -->\n\n"
            f"<!-- system -->\n{system_prompt}\n\n<!-- user -->\n{user_prompt}\n", encoding="utf-8")
        (self.folder / f"{step}.request.json").write_text(
            json.dumps({"step": step, "binding": binding, "inputs": self.binding_inputs}, indent=1) + "\n",
            encoding="utf-8")
        if not answer.is_file():
            raise AwaitingAnswer(
                f"Waiting for an answer to step '{step}'. Read {prompt}, save {answer} as {wrapper} "
                "(binding is in the prompt's first line), then run the same command again.")
        try:
            saved = json.loads(answer.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise StaleAnswer(f"{answer} is not readable JSON ({type(exc).__name__}). Save it as {wrapper}.") from exc
        if not isinstance(saved, dict) or "binding" not in saved or "answer" not in saved:
            raise StaleAnswer(f"{answer} has no binding. Save it as {wrapper}; an answer that does not say which "
                              "request it answers is not used.")
        if saved["binding"] != binding:
            raise StaleAnswer(
                f"{answer} was written for a different request (binding {short(saved['binding'])}, current "
                f"{binding[:12]}…): the evidence, prompt, schema or an earlier step's answer has changed. Move or "
                f"delete it (answers for later steps will be stale too) and answer the new prompt in {prompt}.")
        self.bindings[step] = binding
        return json.dumps(saved["answer"], ensure_ascii=False)


def make_ollama(base_url: str, model: str, *, allow_remote: bool = False, temperature: float = 0.1,
                timeout_seconds: float = 600, context_tokens: int | None = 16384,
                think: bool | None = None, transport=None) -> OllamaProvider:
    host = (urlsplit(base_url).hostname or "").lower()
    if not is_loopback_host(host) and not allow_remote:
        raise ConfigError(f"{base_url} is not a loopback address. Evidence would leave this machine. "
                          "Pass --allow-remote only if that endpoint is approved for this evidence.")
    if not model:
        raise ConfigError("No model configured. Set HAQ_MODEL or pass --model (see `ollama list`).")
    provider = OllamaProvider(base_url=base_url, model=model, temperature=temperature,
                              timeout_seconds=timeout_seconds, context_tokens=context_tokens, think=think,
                              transport=transport)
    provider.label = f"LOCAL MODEL via Ollama ({model})" if provider.location == LOCAL else f"REMOTE MODEL ({model})"
    return provider
