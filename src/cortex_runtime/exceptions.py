"""CORTEX Runtime exception hierarchy."""

from __future__ import annotations


class CortexRuntimeError(Exception):
    """Base exception for all cortex_runtime errors."""


class CortexProviderError(CortexRuntimeError):
    """Base exception for provider operations.

    Attributes:
        provider: Provider name that triggered the error.
        session_id: Session ID where the error occurred.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        session_id: str = "",
    ) -> None:
        self.provider = provider
        self.session_id = session_id
        super().__init__(message)


class ProviderConnectionError(CortexProviderError):
    """Failed to connect to a provider endpoint.

    Retryable: Yes (with backoff).
    """


class ProviderExecutionError(CortexProviderError):
    """Provider returned an error during execution.

    Retryable: Depends on error code from provider.
    """


class ProviderTimeoutError(CortexProviderError):
    """Provider did not respond within the configured timeout.

    Retryable: Yes (with backoff).
    """


class ProviderCapabilityError(CortexProviderError):
    """Provider does not support a requested capability.

    Retryable: No (caller must use a different provider).
    """


class BusError(CortexRuntimeError):
    """Base exception for message bus operations."""


class BusConnectionError(BusError):
    """Failed to connect or reconnect to the message bus.

    Retryable: Yes (with backoff).
    """


class BusSerializationError(BusError):
    """Failed to serialize or deserialize a bus message.

    Retryable: No (data issue).
    """


class CortexMemoryError(CortexRuntimeError):
    """Base exception for memory operations."""


class MemoryFileNotFoundError(CortexMemoryError):
    """Requested memory file does not exist."""


class MemoryReadError(CortexMemoryError):
    """Failed to read a memory file."""


class MemoryWriteError(CortexMemoryError):
    """Failed to write a memory file."""
