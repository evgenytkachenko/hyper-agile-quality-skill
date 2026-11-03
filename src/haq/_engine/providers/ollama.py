"""Ollama over its local HTTP API. Nothing outside this module knows about Ollama."""

from __future__ import annotations

import httpx

from urllib.parse import urlsplit

from ..errors import OutputLimitExceeded, ProviderError, ProviderTimeout
from ..network import is_loopback_host
from .base import EXTERNAL, LOCAL, ModelProvider, reported_token_usage


class OllamaProvider(ModelProvider):
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        temperature: float = 0.1,
        timeout_seconds: float = 600,
        context_tokens: int | None = None,
        think: bool | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.context_tokens = context_tokens
        self.think = think
        host = (urlsplit(self.base_url).hostname or "").lower()
        self.location = LOCAL if is_loopback_host(host) else EXTERNAL
        self.last_usage = None
        self._client = httpx.Client(
            base_url=self.base_url, timeout=timeout_seconds, transport=transport,
            # A loopback address must not send prompts through an ambient proxy.
            # Explicitly remote endpoints retain their existing environment behavior.
            trust_env=self.location != LOCAL, follow_redirects=False,
        )

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(
                f"Ollama did not respond within {self.timeout_seconds:g} seconds at "
                f"{self.base_url}. Raise runtime.model_call_timeout_seconds (or model.timeout_seconds) "
                "or use a smaller model."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Ollama is not reachable at {self.base_url}") from exc

        if response.is_redirect:
            raise ProviderError("Ollama returned a redirect; endpoint redirection is refused.")

        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code == 404 and "not found" in str(data.get("error", "")):
            raise ProviderError(self._not_installed())
        if response.is_error:
            detail = data.get("error") or response.text[:300]
            raise ProviderError(f"Ollama returned HTTP {response.status_code}: {detail}")
        if not isinstance(data, dict):
            raise ProviderError(f"Ollama returned an unexpected response from {path}.")
        return data

    def _not_installed(self, installed: list[str] | None = None) -> str:
        message = f"Configured model '{self.model}' is not installed in Ollama."
        if installed is not None:
            message += f" Installed models: {', '.join(installed) or 'none'}."
        return (
            f"{message} Install it yourself with `ollama pull {self.model}` "
            "or configure a different model."
        )

    def list_models(self) -> list[str]:
        data = self._request("GET", "/api/tags")
        return [m["name"] for m in data.get("models", []) if "name" in m]

    def check_ready(self) -> None:
        installed = self.list_models()
        if self.model not in installed and f"{self.model}:latest" not in installed:
            raise ProviderError(self._not_installed(installed))

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_schema: dict | None = None,
    ) -> str:
        options: dict = {"temperature": self.temperature}
        if self.context_tokens:
            options["num_ctx"] = self.context_tokens
        if self.max_output_tokens:
            # Without it Ollama generates until the model stops, however long that takes.
            options["num_predict"] = self.max_output_tokens
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": options,
        }
        if json_schema is not None:
            payload["format"] = json_schema
        if self.think is not None:
            payload["think"] = self.think

        self.last_usage = None
        data = self._request("POST", "/api/chat", json=payload)
        self.last_usage = reported_token_usage({"input_tokens": data.get("prompt_eval_count"),
                                                "output_tokens": data.get("eval_count")})
        if data.get("done_reason") == "length":
            # Cut off by the cap, not finished: whatever came back is not a complete answer.
            raise OutputLimitExceeded(
                f"The model '{self.model}' was still generating at the output limit of "
                f"{self.max_output_tokens or 'the provider default'} tokens. Its answer is incomplete and was not used."
            )
        content = (data.get("message") or {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderError(
                f"Ollama returned an empty response for model '{self.model}'."
            )
        return content

    def resource_observation(self) -> dict | None:
        """Memory the loaded model occupies, as Ollama reports it. None if it is not loaded
        or the endpoint does not say."""
        try:
            running = self._request("GET", "/api/ps").get("models", [])
        except ProviderError:
            return None
        for entry in running:
            if entry.get("name") in (self.model, f"{self.model}:latest") and isinstance(entry.get("size"), int):
                observed = {"model_memory_bytes": entry["size"]}
                if isinstance(entry.get("size_vram"), int):
                    observed["model_gpu_memory_bytes"] = entry["size_vram"]
                return observed
        return None
