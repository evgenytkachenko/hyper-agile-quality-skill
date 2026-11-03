"""The only model interface the assessment logic depends on."""

from __future__ import annotations

from abc import ABC, abstractmethod


LOCAL, EXTERNAL = "local", "external"


TOKEN_COUNTERS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def reported_token_usage(value: dict | None) -> dict[str, int] | None:
    """Allow only provider-reported nonnegative integer counters; absence is unknown."""
    if not isinstance(value, dict):
        return None
    counters = {key: value[key] for key in TOKEN_COUNTERS
                if type(value.get(key)) is int and value[key] >= 0}
    return counters or None


class ModelProvider(ABC):
    name: str
    model: str
    # Where prompts go: LOCAL stays on this machine, EXTERNAL leaves it. A provider that
    # can be either decides per instance.
    location: str = LOCAL
    # Token counts the provider reported for the most recent generate() call, or None
    # when it reports none: {"input_tokens": int, "output_tokens": int, ...}. Counts only.
    last_usage: dict | None = None
    # The most tokens one call may generate, or None for the provider's own default. Set
    # with limit_output() before a call; a provider that supports a cap sends it.
    max_output_tokens: int | None = None

    def limit_output(self, tokens: int | None) -> None:
        """Cap the output of the calls that follow. A call that reaches the cap while the
        model is still generating raises OutputLimitExceeded: a cut-off answer is not a result."""
        self.max_output_tokens = tokens if tokens and tokens > 0 else None

    def resource_observation(self) -> dict | None:
        """What the provider can safely report about the resources the model is using,
        e.g. {"model_memory_bytes": int}. None when it cannot."""
        return None

    @abstractmethod
    def list_models(self) -> list[str]:
        """Models available at the endpoint. Raises ProviderError if it is unreachable."""

    @abstractmethod
    def check_ready(self) -> None:
        """Raise ProviderError unless the endpoint is reachable and the model is available."""

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_schema: dict | None = None,
    ) -> str:
        """Return the model's text response.

        json_schema, when given, asks for output constrained to that JSON Schema. Providers
        that cannot enforce it may ignore it: callers still validate the response."""
