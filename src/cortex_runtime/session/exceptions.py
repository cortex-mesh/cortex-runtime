"""Session management exceptions for cortex_runtime."""

from __future__ import annotations

from uuid import UUID

from cortex_runtime.exceptions import CortexProviderError


class SessionError(Exception):
    """Base exception for session-related errors."""


class SessionNotFoundError(SessionError, CortexProviderError):
    """Raised when a session cannot be found."""

    def __init__(
        self,
        session_id: UUID | str,
        *,
        provider: str = "",
    ) -> None:
        self.session_id = str(session_id)
        CortexProviderError.__init__(
            self,
            f"Session not found: {session_id}",
            provider=provider,
            session_id=str(session_id),
        )


class SessionStoreError(SessionError):
    """Raised when a session store operation fails."""

    def __init__(self, operation: str, message: str) -> None:
        self.operation = operation
        super().__init__(f"Session store error in {operation}: {message}")


class DomainNotFoundError(SessionError):
    """Raised when a domain cannot be resolved from a channel."""

    def __init__(self, channel_name: str) -> None:
        self.channel_name = channel_name
        super().__init__(f"Cannot resolve domain for channel: {channel_name}")
