"""Errors the CLI reports as a plain message instead of a stack trace."""


class HyperAgileError(Exception):
    """Base class for expected, user-facing failures."""


class ConfigError(HyperAgileError):
    pass


class MethodologyError(HyperAgileError):
    pass


class EvidenceError(HyperAgileError):
    pass


class ProviderError(HyperAgileError):
    # Why a model call produced nothing usable, for the run's diagnostics.
    kind = "provider_error"


class ProviderTimeout(ProviderError):
    """The model did not answer within the call timeout. The call produced no result."""

    kind = "timeout"


class OutputLimitExceeded(ProviderError):
    """The model was still generating when it reached the output cap. What it produced is
    incomplete by construction and is never used as a result."""

    kind = "output_limit"


class PassOutputError(HyperAgileError):
    pass


class ReportConsistencyError(HyperAgileError):
    """Raised when the assembled report would silently drop or contradict a
    validated structured finding and the problem cannot be repaired deterministically."""


class ContextBudgetError(HyperAgileError):
    """A pass would not fit the model's context window and was not invoked."""

