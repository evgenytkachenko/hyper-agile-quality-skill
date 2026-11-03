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


class ExchangeProvider(ModelProvider):
    """Writes <dir>/<step>.prompt.md and reads <dir>/<step>.answer.json."""

    name = "exchange"
    location = EXTERNAL  # the agent's own model may be anywhere
    label = "AGENT ANSWERS (unverified model output from the invoking agent)"

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.model = "agent-exchange"
        self.current_step = ""

    def list_models(self) -> list[str]:
        return [self.model]

    def check_ready(self) -> None:
        return None

    def generate(self, system_prompt: str, user_prompt: str, *, json_schema: dict | None = None) -> str:
        prompt = self.folder / f"{self.current_step}.prompt.md"
        answer = self.folder / f"{self.current_step}.answer.json"
        prompt.write_text(f"<!-- system -->\n{system_prompt}\n\n<!-- user -->\n{user_prompt}\n", encoding="utf-8")
        if not answer.is_file():
            raise AwaitingAnswer(
                f"Waiting for an answer to step '{self.current_step}'. Read {prompt}, save one JSON object to "
                f"{answer}, then run the same command again.")
        return answer.read_text(encoding="utf-8")


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
