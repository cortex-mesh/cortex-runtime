"""Redis Streams implementation of the cortex_runtime message bus.

Provides :class:`RedisStreamBus` — a concrete ``MessageBus`` implementation
backed by Redis Streams. Uses XADD for publishing, XREADGROUP for
consumer-group-based subscription, and XAUTOCLAIM for crash recovery.

Requires ``redis>=5.0.0`` (async support via ``redis.asyncio``).

Example::

    from cortex_runtime.bus_redis import RedisStreamBus
    from cortex_runtime.models import BusConfig

    config = BusConfig(host="redis.internal", password="secret")
    bus = RedisStreamBus(config)

    # Publish a task
    msg_id = await bus.publish("tasks:eng", payload_bytes, msg_type="task")

    # Subscribe to results
    async for envelope in bus.subscribe("results", "cortex-agents", "myagent-1"):
        result = TaskResult.model_validate_json(envelope.payload)
        await bus.ack("results", "cortex-agents", envelope.msg_id)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ResponseError

from cortex_runtime.env import REDIS_KEEPALIVE_OPTIONS
from cortex_runtime.exceptions import BusConnectionError, BusSerializationError
from cortex_runtime.models import BusConfig, Envelope, HealthStatus

logger = logging.getLogger(__name__)


class RedisStreamBus:
    """Message bus implementation using Redis Streams.

    Satisfies the ``MessageBus`` protocol via structural typing — no
    inheritance needed.

    Features:
        - Automatic connection with exponential backoff retry
        - Consumer group auto-creation (XGROUP CREATE with MKSTREAM)
        - Crash recovery via XAUTOCLAIM on subscribe startup
        - Own-PEL re-delivery after fast restart (fleet updates)
        - Client-side watchdog for half-dead sockets
        - Graceful shutdown with connection pool cleanup

    The bus prefixes all stream names with ``config.stream_prefix``
    (default ``"cortex"``), so publishing to ``"tasks:eng"`` writes to
    ``"cortex:tasks:eng"`` in Redis.
    """

    def __init__(self, config: BusConfig) -> None:
        self._config = config
        self._redis: aioredis.Redis | None = None
        self._groups_created: set[tuple[str, str]] = set()
        # Watchdog must always outlast the server-side block window
        self._read_watchdog_seconds: float = (
            max(config.read_watchdog_ms, config.block_ms + 1_000) / 1_000.0
        )

    # ── Connection management ───────────────────────────────────────────

    async def _ensure_connected(self) -> aioredis.Redis:
        """Lazily initialize the Redis connection with retry config."""
        if self._redis is not None:
            return self._redis

        retry = Retry(
            ExponentialBackoff(base=self._config.retry_backoff_base),
            self._config.max_retries,
        )

        self._redis = aioredis.Redis(
            host=self._config.host,
            port=self._config.port,
            password=self._config.password,
            db=self._config.db,
            decode_responses=False,
            max_connections=self._config.max_connections,
            socket_timeout=self._config.socket_timeout,
            health_check_interval=self._config.health_check_interval,
            socket_keepalive=True,
            socket_keepalive_options=REDIS_KEEPALIVE_OPTIONS,
            retry=retry,
            retry_on_error=[ConnectionError, TimeoutError, OSError],
        )
        return self._redis

    def _full_stream(self, stream: str) -> str:
        """Resolve a logical stream name to the full Redis key."""
        return f"{self._config.stream_prefix}:{stream}"

    # ── Public API ──────────────────────────────────────────────────────

    async def publish(
        self,
        stream: str,
        payload: bytes,
        *,
        msg_type: str = "",
        maxlen: int | None = None,
    ) -> str:
        """Publish a message to a Redis stream via XADD."""
        r = await self._ensure_connected()
        full_stream = self._full_stream(stream)

        fields: dict[str, bytes] = {
            "type": msg_type.encode(),
            "payload": payload,
        }

        xadd_kwargs: dict[str, object] = {}
        if maxlen is not None:
            xadd_kwargs["maxlen"] = maxlen
            xadd_kwargs["approximate"] = True

        try:
            msg_id = await r.xadd(full_stream, fields, **xadd_kwargs)  # type: ignore[arg-type]
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise BusConnectionError(
                f"Failed to publish to stream '{full_stream}': {exc}",
            ) from exc

        result = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
        logger.debug("Published to %s: %s (type=%s)", full_stream, result, msg_type)
        return result

    async def subscribe(
        self,
        stream: str,
        group: str,
        consumer: str,
    ) -> AsyncIterator[Envelope]:
        """Subscribe to a Redis stream via consumer group.

        Auto-creates the consumer group on first call, performs
        XAUTOCLAIM for crash recovery, then enters the XREADGROUP
        blocking read loop.
        """
        r = await self._ensure_connected()
        full_stream = self._full_stream(stream)

        # Auto-create consumer group (idempotent)
        await self._ensure_group(r, full_stream, group)

        # Crash recovery: reclaim pending messages from crashed consumers
        async for envelope in self._reclaim_pending(r, full_stream, group, consumer):
            yield envelope

        # Re-deliver own pending entries (fast-restart after interrupt)
        async for envelope in self._read_own_pending(r, full_stream, group, consumer):
            yield envelope

        # Main read loop
        consecutive_timeouts = 0
        while True:
            try:
                results: list[Any] = await asyncio.wait_for(
                    r.xreadgroup(
                        groupname=group,
                        consumername=consumer,
                        streams={full_stream: ">"},
                        count=10,
                        block=self._config.block_ms,
                    ),
                    timeout=self._read_watchdog_seconds,
                )
            except TimeoutError:
                # Client-side watchdog triggered — asyncio.wait_for raises the
                # builtin TimeoutError when a blocking XREADGROUP outlives its
                # server-side block window. This indicates a half-dead socket
                # (idle proxy dropped it without RST). redis-py reconnects on
                # the next call; XREADGROUP ">" re-reads entries that arrived.
                consecutive_timeouts += 1
                if consecutive_timeouts == 1:
                    logger.warning(
                        "XREADGROUP watchdog fired on '%s' — connection may be stale",
                        full_stream,
                    )
                continue
            except (ConnectionError, OSError) as exc:
                raise BusConnectionError(
                    f"XREADGROUP failed on '{full_stream}': {exc}",
                ) from exc

            if consecutive_timeouts > 0:
                logger.info(
                    "XREADGROUP recovered on '%s' after %d stale-read timeout(s)",
                    full_stream,
                    consecutive_timeouts,
                )
                consecutive_timeouts = 0

            if not results:
                continue

            for _stream_key, messages in results:
                for msg_id_raw, fields in messages:
                    try:
                        yield self._parse_message(msg_id_raw, full_stream, fields)
                    except BusSerializationError:
                        logger.warning(
                            "Skipping unparseable message %s on %s",
                            msg_id_raw,
                            full_stream,
                        )
                        await r.xack(full_stream, group, msg_id_raw)

    async def ack(
        self,
        stream: str,
        group: str,
        msg_id: str,
    ) -> None:
        """Acknowledge a consumed message via XACK."""
        r = await self._ensure_connected()
        full_stream = self._full_stream(stream)

        try:
            await r.xack(full_stream, group, msg_id)
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise BusConnectionError(
                f"XACK failed on '{full_stream}': {exc}",
            ) from exc

        logger.debug("ACK %s on %s/%s", msg_id, full_stream, group)

    async def health(self) -> HealthStatus:
        """Check Redis connectivity via PING."""
        try:
            r = await self._ensure_connected()
            pong = await r.ping()  # type: ignore[misc]
            info: dict[str, Any] = await r.info(section="server")

            return HealthStatus(
                ok=bool(pong),
                details={
                    "redis_version": info.get("redis_version", "unknown"),
                    "connected_clients": info.get("connected_clients", -1),
                    "host": self._config.host,
                    "port": self._config.port,
                },
            )
        except (ConnectionError, TimeoutError, OSError) as exc:
            return HealthStatus(
                ok=False,
                error=str(exc),
            )

    async def close(self) -> None:
        """Close the Redis connection pool."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
            self._groups_created.clear()
            logger.debug("Redis connection closed")

    # ── Internal helpers ────────────────────────────────────────────────

    async def _ensure_group(
        self,
        r: aioredis.Redis,
        full_stream: str,
        group: str,
    ) -> None:
        """Create a consumer group if it doesn't already exist."""
        key = (full_stream, group)
        if key in self._groups_created:
            return

        try:
            await r.xgroup_create(
                name=full_stream,
                groupname=group,
                id="0",
                mkstream=True,
            )
            logger.info("Created consumer group '%s' on '%s'", group, full_stream)
        except ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                logger.debug("Consumer group '%s' already exists on '%s'", group, full_stream)
            else:
                raise BusConnectionError(
                    f"XGROUP CREATE failed on '{full_stream}': {exc}",
                ) from exc

        self._groups_created.add(key)

    async def _reclaim_pending(
        self,
        r: aioredis.Redis,
        full_stream: str,
        group: str,
        consumer: str,
    ) -> AsyncIterator[Envelope]:
        """Reclaim pending messages idle longer than claim_idle_ms via XAUTOCLAIM."""
        try:
            result = await r.xautoclaim(
                name=full_stream,
                groupname=group,
                consumername=consumer,
                min_idle_time=self._config.claim_idle_ms,
                start_id="0-0",
            )
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise BusConnectionError(
                f"XAUTOCLAIM failed on '{full_stream}': {exc}",
            ) from exc
        except ResponseError:
            return

        claimed_messages: list[Any] = result[1] if len(result) > 1 else []

        if claimed_messages:
            logger.info(
                "Reclaimed %d pending messages on '%s/%s'",
                len(claimed_messages),
                full_stream,
                group,
            )

        for msg_id_raw, fields in claimed_messages:
            try:
                yield self._parse_message(msg_id_raw, full_stream, fields)
            except BusSerializationError:
                logger.warning(
                    "Skipping unparseable reclaimed message %s on %s",
                    msg_id_raw,
                    full_stream,
                )
                await r.xack(full_stream, group, msg_id_raw)

    async def _read_own_pending(
        self,
        r: aioredis.Redis,
        full_stream: str,
        group: str,
        consumer: str,
    ) -> AsyncIterator[Envelope]:
        """Re-deliver this consumer's own pending entries via XREADGROUP 0-0.

        Handles the fast-restart case where a fleet update cancels an in-flight
        task and the process restarts within the XAUTOCLAIM idle threshold.
        Messages whose fields are empty (stream trimmed by MAXLEN) are ACK'd.
        """
        try:
            results: list[Any] = await r.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={full_stream: "0-0"},
                count=100,
            )
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise BusConnectionError(
                f"XREADGROUP 0-0 failed on '{full_stream}': {exc}",
            ) from exc
        except ResponseError:
            return

        if not results:
            return

        pending_count = 0
        for _stream_key, messages in results:
            for msg_id_raw, fields in messages:
                if not fields:
                    logger.debug(
                        "Auto-ACK trimmed pending message %s on %s",
                        msg_id_raw,
                        full_stream,
                    )
                    await r.xack(full_stream, group, msg_id_raw)
                    continue

                try:
                    envelope = self._parse_message(msg_id_raw, full_stream, fields)
                    pending_count += 1
                    yield envelope.model_copy(update={"resumed": True})
                except BusSerializationError:
                    logger.warning(
                        "Skipping unparseable own-pending message %s on %s",
                        msg_id_raw,
                        full_stream,
                    )
                    await r.xack(full_stream, group, msg_id_raw)

        if pending_count:
            logger.info(
                "Re-delivering %d own pending messages on '%s/%s' (consumer=%s)",
                pending_count,
                full_stream,
                group,
                consumer,
            )

    def _parse_message(
        self,
        msg_id_raw: bytes | str,
        full_stream: str,
        fields: dict[bytes, bytes],
    ) -> Envelope:
        """Parse a raw Redis stream message into an Envelope."""
        msg_id = msg_id_raw.decode() if isinstance(msg_id_raw, bytes) else str(msg_id_raw)

        try:
            msg_type = fields.get(b"type", b"").decode()
            payload = fields.get(b"payload", b"")
        except (ValueError, AttributeError, UnicodeDecodeError) as exc:
            raise BusSerializationError(
                f"Failed to parse message {msg_id} on '{full_stream}': {exc}",
            ) from exc

        return Envelope(
            msg_id=msg_id,
            payload=payload,
            msg_type=msg_type,
        )
