"""MessageBus Protocol for cortex_runtime.

The concrete implementation is :class:`~cortex_runtime.bus_redis.RedisStreamBus`.
Any class with matching method signatures satisfies this protocol — no
inheritance required (structural typing via ``typing.Protocol``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from cortex_runtime.models import Envelope, HealthStatus


@runtime_checkable
class MessageBus(Protocol):
    """Protocol for the CORTEX message bus.

    The bus is the communication backbone between conductors and agents.
    Publishers push Envelopes; subscribers receive them via consumer groups
    for exactly-once delivery.
    """

    async def publish(
        self,
        stream: str,
        payload: bytes,
        *,
        msg_type: str = "task",
        maxlen: int = 1000,
    ) -> str:
        """Publish a message to *stream*.

        Args:
            stream: Redis Stream name (without org prefix — caller manages scoping).
            payload: Raw bytes payload (typically JSON-encoded).
            msg_type: Logical message type tag stored in the stream entry.
            maxlen: Approximate maximum stream length (MAXLEN ~ trimming).

        Returns:
            Stream entry ID (e.g. ``"1234567890-0"``).

        Raises:
            BusConnectionError: If the bus is unreachable.
            BusSerializationError: If serialization fails.
        """
        ...

    def subscribe(
        self,
        stream: str,
        group: str,
        consumer: str,
    ) -> AsyncIterator[Envelope]:
        """Subscribe to *stream* via a consumer group.

        Yields :class:`~cortex_runtime.models.Envelope` objects as they arrive.
        Blocks (with periodic wakeups) when the stream is empty.

        Args:
            stream: Redis Stream name.
            group: Consumer group name (auto-created if absent).
            consumer: Unique consumer name within the group.

        Yields:
            Envelope objects containing deserialized payloads.

        Raises:
            BusConnectionError: If the connection drops during iteration.
        """
        ...

    async def ack(self, stream: str, group: str, msg_id: str) -> None:
        """Acknowledge a processed message (XACK).

        Args:
            stream: Redis Stream name.
            group: Consumer group name.
            msg_id: Stream entry ID returned by ``subscribe``.
        """
        ...

    async def health(self) -> HealthStatus:
        """Check bus connectivity and return a health report."""
        ...

    async def close(self) -> None:
        """Close the underlying connection pool gracefully."""
        ...
