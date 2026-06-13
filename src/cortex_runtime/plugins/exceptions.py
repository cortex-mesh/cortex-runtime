"""Plugin exception hierarchy for cortex_runtime."""

from __future__ import annotations

from cortex_runtime.exceptions import CortexProviderError


class PluginError(CortexProviderError):
    """Base exception for all plugin operations.

    All exceptions raised by plugin implementations MUST inherit from
    this class so the orchestrator can catch ``PluginError`` uniformly.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        session_id: str = "",
        plugin: str = "",
        action: str = "",
    ) -> None:
        self.plugin = plugin
        self.action = action
        super().__init__(message, provider=provider, session_id=session_id)


class PluginActionError(PluginError):
    """Action execution failed (API error, business logic failure)."""


class PluginAuthError(PluginError):
    """Credentials missing, expired, or revoked."""


class PluginRateLimitError(PluginError):
    """Service rate limit exceeded.

    Attributes:
        retry_after_seconds: Suggested wait time before retry, if known.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        session_id: str = "",
        plugin: str = "",
        action: str = "",
        retry_after_seconds: float | None = None,
    ) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            message,
            provider=provider,
            session_id=session_id,
            plugin=plugin,
            action=action,
        )


class PluginNotFoundError(PluginError):
    """Plugin not registered in the registry."""


class PluginValidationError(PluginError):
    """Action parameters failed schema validation."""
