"""CortexProvider Protocol for cortex_runtime.

The provider is the AI runtime adapter — it translates task payloads into
LLM calls and yields streaming output chunks.

Provider implementations live outside this package (deferred to
``cortex_runtime.providers._loop_driver`` — see that module for the
TODO placeholder). This file defines only the protocol so the rest of
the runtime can be tested without a real LLM key.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from cortex_runtime.models import HealthStatus, StreamChunk


class CortexProvider(Protocol):
    """Protocol for AI runtime adapters.

    Any class with matching method signatures satisfies this protocol.
    Implementations must NOT inherit from this class.

    The ``execute`` method uses a plain ``def`` (not ``async def``) intentionally
    — ``Protocol`` + ``AsyncIterator`` return types interact poorly with mypy
    (issue #5385). Implementations must still be ``async def`` generators or
    return an ``AsyncIterator``; the protocol just validates the signature.
    """

    def execute(
        self,
        prompt: str,
        *,
        context: dict[str, Any] | None = None,
        working_directory: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Execute a prompt and yield streaming output chunks.

        Args:
            prompt: The full prompt text (already context-enriched by the runtime).
            context: Optional dict with task metadata (domain, sender, etc.).
            working_directory: Optional filesystem path to use as CWD.

        Yields:
            :class:`~cortex_runtime.models.StreamChunk` objects.
            At minimum one ``StreamChunkKind.COMPLETE`` chunk must be yielded.

        Raises:
            ProviderConnectionError: If the provider endpoint is unreachable.
            ProviderExecutionError: If the provider returns an error response.
            ProviderTimeoutError: If execution exceeds the configured timeout.
        """
        ...

    async def health(self) -> HealthStatus:
        """Check provider connectivity and return a health report."""
        ...
