"""Conductor-side dispatch logic for cortex_runtime.

The TaskDispatcher classifies incoming messages by domain and publishes
them to Redis Streams for agent consumption.

Dispatch flow:
    Channel message -> resolve target stream -> build TaskPayload
    -> XADD to stream -> add reaction -> mark_responded
"""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING, Any

from cortex_runtime.dispatch_models import (
    AGENT_STREAM_PREFIX,
    DOMAIN_STREAM_PREFIX,
    DispatchResult,
    TaskPayload,
)

if TYPE_CHECKING:
    from cortex_runtime.bus_redis import RedisStreamBus

logger = logging.getLogger(__name__)


class TaskDispatcher:
    """Conductor-side: classifies messages and dispatches to Redis Streams.

    This is the open adoption surface — complexity classification, adaptive
    routing, and plan approval are intentionally excluded. Extend by providing
    an ``agent_registry`` and optionally a ``context_runtime``.

    Example::

        dispatcher = TaskDispatcher(
            bus=bus,
            agent_registry=registry,
            channel=channel_manager,
        )
        result = await dispatcher.dispatch(message)
    """

    def __init__(
        self,
        bus: RedisStreamBus,
        agent_registry: Any | None = None,
        channel: Any | None = None,
        response_tracker: Any | None = None,
        thread_affinity: Any | None = None,
        context_runtime: object | None = None,
    ) -> None:
        self._bus = bus
        self._registry = agent_registry
        self._channel = channel
        self._response_tracker = response_tracker
        self._thread_affinity = thread_affinity
        self._context_runtime = context_runtime

    async def dispatch(self, message: Any) -> DispatchResult | None:
        """Classify message and publish to the appropriate stream.

        Returns a DispatchResult if dispatched, None if skipped.
        """
        domain = message.metadata.get("domain", "personal")

        if self._channel:
            react = getattr(self._channel, "react", None)
            if react:
                await react(message, "eyes")

        stream_name, preferred_agent = await self._resolve_target(message, domain)
        if stream_name is None:
            logger.warning(
                "No agent available for domain '%s', skipping message %s",
                domain,
                message.id,
            )
            if self._channel:
                react = getattr(self._channel, "react", None)
                if react:
                    await react(message, "eyes", remove=True)
            return None

        payload = self._build_payload(message, domain, preferred_agent)

        if self._context_runtime is not None:
            payload = await self._context_runtime.prepare_payload(payload)  # type: ignore[attr-defined]

        if self._channel:
            react = getattr(self._channel, "react", None)
            follow = getattr(self._channel, "follow_thread", None)
            if react:
                await react(message, "eyes", remove=True)
                await react(message, "hourglass_flowing_sand")
            if follow:
                await follow(message)

        payload_bytes = payload.model_dump_json().encode()
        msg_id = await self._bus.publish(stream_name, payload_bytes, msg_type="task", maxlen=1000)

        if self._response_tracker:
            mark = getattr(self._response_tracker, "mark_responded", None)
            if mark:
                await mark(message.id, "dispatched")

        logger.info(
            "Dispatched message %s -> %s (agent=%s, domain=%s, stream_id=%s)",
            message.id,
            stream_name,
            preferred_agent or "any",
            domain,
            msg_id,
        )
        return DispatchResult(
            stream_id=msg_id,
            agent=preferred_agent or "",
            domain=domain,
        )

    async def _resolve_target(
        self, message: Any, domain: str
    ) -> tuple[str | None, str | None]:
        """Determine target stream and preferred agent.

        Priority:
        1. @mention of a specific agent -> agent stream
        2. DM target -> agent stream
        3. Thread affinity -> previously responding agent
        4. Domain-based routing -> primary agent for the domain
        """
        mentions = message.metadata.get("mentions", [])
        for mention in mentions:
            if self._registry is not None:
                get = getattr(self._registry, "get", None)
                entry = get(mention) if get else None
                if entry is not None:
                    return f"{AGENT_STREAM_PREFIX}:{mention}", mention

        dm_target = message.metadata.get("dm_target")
        if dm_target and self._registry is not None:
            get = getattr(self._registry, "get", None)
            entry = get(dm_target) if get else None
            if entry is not None:
                logger.info("DM routing: message -> agent %s", dm_target)
                return f"{AGENT_STREAM_PREFIX}:{dm_target}", dm_target

        if self._thread_affinity and message.thread_id:
            get_agent = getattr(self._thread_affinity, "get_agent", None)
            if get_agent:
                agent = await get_agent(message.thread_id)
                if agent and self._registry is not None:
                    get = getattr(self._registry, "get", None)
                    if get and get(agent) is not None:
                            logger.info(
                                "Thread affinity: routing thread %s to agent %s",
                                message.thread_id,
                                agent,
                            )
                            return f"{AGENT_STREAM_PREFIX}:{agent}", agent

        if self._registry is not None:
            primary_agent = getattr(self._registry, "primary_agent", None)
            if primary_agent:
                primary = primary_agent(domain)
                if primary is not None:
                    name = getattr(primary, "name", str(primary))
                    return f"{DOMAIN_STREAM_PREFIX}:{domain}", name

        return None, None

    def _build_payload(
        self,
        message: Any,
        domain: str,
        preferred_agent: str | None,
    ) -> TaskPayload:
        """Build a TaskPayload from a channel message."""
        text = message.text
        if not text.strip() and getattr(message, "attachments", None):
            for att in message.attachments:
                desc = getattr(att, "description", None) or (
                    att.get("description") if isinstance(att, dict) else None
                )
                if desc:
                    text = desc
                    break

        attachments = getattr(message, "attachments", [])
        serialized_attachments = [
            dataclasses.asdict(att) if dataclasses.is_dataclass(att) else att
            for att in attachments
        ]

        return TaskPayload(
            message_id=message.id,
            thread_id=getattr(message, "thread_id", None),
            channel_name=message.metadata.get("channel_name", ""),
            room_id=getattr(message, "channel", None),
            domain=domain,
            sender=getattr(message, "sender", ""),
            sender_id=getattr(message, "sender_id", ""),
            text=text,
            mentions=message.metadata.get("mentions", []),
            has_bot_mention=message.metadata.get("has_bot_mention", False),
            in_active_thread=message.metadata.get("in_active_thread", False),
            metadata={
                "source": getattr(message, "source", ""),
                "channel": getattr(message, "channel", ""),
                "sender": getattr(message, "sender", ""),
                "sender_id": getattr(message, "sender_id", ""),
                "thread_id": getattr(message, "thread_id", None),
                "message_id": message.id,
                **message.metadata,
            },
            thread_context=message.metadata.get("thread_context", []),
            attachments=serialized_attachments,
            preferred_agent=preferred_agent,
        )
