"""Agent-side task consumer for cortex_runtime.

The TaskConsumer subscribes to Redis Streams (domain streams + agent-specific
stream), processes dispatched tasks via the provider execute function, and
replies through the source channel.

This is the open adoption surface: workspace management, idle-dispatch
post-processing, outcome logging, and evaluation hooks are intentionally
excluded. Extend by subclassing and overriding ``_deliver_reply`` and
``_activity_agent_label``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Any, Literal

from cortex_runtime.dispatch_models import (
    AGENT_STREAM_PREFIX,
    DOMAIN_STREAM_PREFIX,
    MemoryProposal,
    TaskPayload,
    TaskResult,
)
from cortex_runtime.prompt_utils import append_attachments_to_prompt, format_thread_context

if TYPE_CHECKING:
    from cortex_runtime.bus_redis import RedisStreamBus
    from cortex_runtime.models import Envelope, StreamChunk

# Type alias for the execute function signature
ExecuteFn = Callable[..., AsyncIterator["StreamChunk"]]

logger = logging.getLogger(__name__)

CONSUMER_GROUP = "cortex-agents"

# Detect [DISCOVERY] tags in agent output
_DISCOVERY_RE = re.compile(r"^\[DISCOVERY\][ \t]*(.+)$", re.MULTILINE)

# Detect [MEMORY: category/name] write-back proposals in agent output (ADR-056 §7.1)
_MEMORY_PROPOSAL_RE = re.compile(
    r"^\[MEMORY:[ \t]*(?P<category>[^/\]\s]+)/(?P<name>[^\]\s]+?)"
    r"(?:[ \t]+(?P<mode>create|update))?[ \t]*\]"
    r"(?P<body>.*?)(?=^\[MEMORY:|\Z)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

RESULTS_STREAM = "results"


def extract_discoveries(text: str) -> list[str]:
    """Extract [DISCOVERY] tag contents from agent output."""
    return [m.group(1).strip() for m in _DISCOVERY_RE.finditer(text) if m.group(1).strip()]


def extract_memory_proposals(text: str) -> list[MemoryProposal]:
    """Parse [MEMORY: category/name] write-back proposals from agent output.

    Parse-only and intentionally permissive about category/name values.
    Validation happens in the conductor's staging/write-back path.
    """
    proposals: list[MemoryProposal] = []
    for match in _MEMORY_PROPOSAL_RE.finditer(text):
        body = match.group("body").strip()
        if not body:
            continue
        mode_word = (match.group("mode") or "create").lower()
        mode: Literal["create", "update"] = "update" if mode_word == "update" else "create"
        proposals.append(
            MemoryProposal(
                category=match.group("category").strip().lower(),
                name=match.group("name").strip(),
                mode=mode,
                content=body,
            )
        )
    return proposals


class TaskConsumer:
    """Agent-side: consumes tasks from Redis Streams and executes them.

    Subscribes to:
    - ``cortex:tasks:{domain}`` for each domain in the agent's config
    - ``cortex:tasks:agent:{identity}`` for @mentions and DMs

    Uses Redis consumer groups for exactly-once delivery.

    Example::

        consumer = TaskConsumer(
            identity="myagent",
            domains=["eng", "personal"],
            bus=bus,
            channel=channel,
        )
        await consumer.start(execute_fn=provider.execute)
    """

    def __init__(
        self,
        identity: str,
        domains: list[str],
        bus: RedisStreamBus,
        channel: Any,
        heartbeat: Any | None = None,
        thread_affinity: Any | None = None,
        context_runtime: object | None = None,
    ) -> None:
        self._identity = identity
        self._domains = domains
        self._bus = bus
        self._channel = channel
        self._heartbeat = heartbeat
        self._thread_affinity = thread_affinity
        self._context_runtime = context_runtime
        self._running = False
        self._execute_fn: ExecuteFn | None = None
        self._stream_restart_base_delay_seconds = 1.0
        self._stream_restart_max_delay_seconds = 30.0

    @property
    def is_running(self) -> bool:
        return self._running

    async def _deliver_reply(
        self,
        payload: TaskPayload,
        response: str,
        thread_target: str | None,
    ) -> None:
        """Post the visible reply for a completed task (overridable)."""
        send = getattr(self._channel, "send", None)
        if send is not None:
            await send(
                payload.room_id,
                response,
                thread_id=thread_target,
            )

    def _activity_agent_label(self, payload: TaskPayload) -> str:
        """Display label for agent-activity updates (overridable)."""
        del payload
        return self._identity

    async def _publish_agent_activity(
        self,
        payload: TaskPayload,
        *,
        phase: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        include_in_context: bool = False,
    ) -> None:
        """Best-effort Synapse task activity update for user-visible agent work."""
        if (
            payload.metadata.get("source") != "synapse"
            or not payload.room_id
            or not payload.message_id
        ):
            return
        publish = getattr(self._channel, "publish_agent_activity", None)
        if publish is None:
            return
        try:
            activity_task_id = str(
                payload.metadata.get("agent_activity_task_id") or payload.task_id
            )
            activity_metadata = {"domain": payload.domain, **(metadata or {})}
            await publish(
                room_id=payload.room_id,
                parent_message_id=payload.message_id,
                thread_id=payload.thread_id,
                task_id=activity_task_id,
                agent_identity=self._identity,
                phase=phase,
                text=text,
                metadata=activity_metadata,
                include_in_context=include_in_context,
            )
        except Exception:
            logger.debug(
                "Failed to publish agent activity for %s",
                payload.task_id,
                exc_info=True,
            )

    def _reaction_message_id(self, payload: TaskPayload) -> str:
        """Format message_id for reaction calls."""
        if payload.metadata.get("source") == "synapse" and payload.room_id:
            return f"{payload.room_id}:{payload.message_id}"
        return payload.message_id

    async def start(self, execute_fn: ExecuteFn) -> None:
        """Subscribe to domain streams + agent stream, process tasks."""
        self._running = True
        self._execute_fn = execute_fn

        streams: list[str] = []
        for domain in self._domains:
            streams.append(f"{DOMAIN_STREAM_PREFIX}:{domain}")
        streams.append(f"{AGENT_STREAM_PREFIX}:{self._identity}")

        consumer_name = f"{self._identity}-1"

        logger.info(
            "TaskConsumer starting for %s (streams=%s, group=%s, consumer=%s)",
            self._identity,
            streams,
            CONSUMER_GROUP,
            consumer_name,
        )

        tasks = []
        for stream in streams:
            task = asyncio.create_task(self._consume_stream(stream, consumer_name, execute_fn))
            tasks.append(task)

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("TaskConsumer cancelled for %s", self._identity)
        finally:
            self._running = False
            for task in tasks:
                task.cancel()

    async def _ack_with_retries(self, stream: str, msg_id: str) -> None:
        """ACK a stream entry, retrying until success or shutdown."""
        delay = self._stream_restart_base_delay_seconds
        while self._running:
            try:
                await self._bus.ack(stream, CONSUMER_GROUP, msg_id)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Failed to ACK task %s on %s: %s; retrying in %.1fs",
                    msg_id,
                    stream,
                    exc,
                    delay,
                    exc_info=True,
                )
                if delay > 0:
                    await asyncio.sleep(delay)
                delay = min(
                    max(delay * 2, self._stream_restart_base_delay_seconds),
                    self._stream_restart_max_delay_seconds,
                )

        await self._bus.ack(stream, CONSUMER_GROUP, msg_id)

    async def _consume_stream(
        self,
        stream: str,
        consumer_name: str,
        execute_fn: ExecuteFn,
    ) -> None:
        """Consume from a single Redis Stream, restarting after transient failures."""
        restart_delay = self._stream_restart_base_delay_seconds
        while self._running:
            logger.info("Subscribing to stream: %s", stream)
            try:
                async for envelope in self._bus.subscribe(stream, CONSUMER_GROUP, consumer_name):
                    restart_delay = self._stream_restart_base_delay_seconds
                    try:
                        await self._process_task(envelope, stream, execute_fn)
                    except Exception as e:
                        logger.error(
                            "Error processing task from %s: %s",
                            stream,
                            e,
                            exc_info=True,
                        )
                        await self._ack_with_retries(stream, envelope.msg_id)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if not self._running:
                    break
                logger.warning(
                    "Stream consumer %s failed: %s; restarting in %.1fs",
                    stream,
                    e,
                    restart_delay,
                    exc_info=True,
                )
                if restart_delay > 0:
                    await asyncio.sleep(restart_delay)
                restart_delay = min(
                    max(restart_delay * 2, self._stream_restart_base_delay_seconds),
                    self._stream_restart_max_delay_seconds,
                )

    def _task_execution_timeout_seconds(self) -> float | None:
        """Return max seconds a task may run. Set to 0 to disable."""
        raw = os.getenv("CORTEX_TASK_EXECUTION_TIMEOUT_SECONDS", "2700").strip()
        try:
            timeout = float(raw)
        except ValueError:
            logger.warning("Invalid CORTEX_TASK_EXECUTION_TIMEOUT_SECONDS=%r; using 2700", raw)
            timeout = 2700.0
        return None if timeout <= 0 else timeout

    async def _run_execute_with_timeout(
        self,
        execute_fn: ExecuteFn,
        *,
        prompt: str,
        context: dict[str, Any],
        working_directory: str | None,
    ) -> tuple[list[str], float | None, int | None, str | None, int | None, int | None]:
        """Run provider execution under a wall-clock timeout."""
        from cortex_runtime.models import StreamChunkKind

        response_parts: list[str] = []
        cost_usd: float | None = None
        num_turns: int | None = None
        model_used: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None

        async def collect() -> None:
            nonlocal cost_usd, num_turns, model_used, input_tokens, output_tokens
            iterator = execute_fn(
                prompt=prompt,
                context=context,
                working_directory=working_directory,
            )
            try:
                async for chunk in iterator:
                    if chunk.kind == StreamChunkKind.OUTPUT:
                        response_parts.append(chunk.data)
                    elif chunk.kind == StreamChunkKind.COMPLETE:
                        cost_usd = chunk.metadata.get("cost_usd")
                        num_turns = chunk.metadata.get("num_turns")
                        model_used = chunk.metadata.get("model_used")
                        input_tokens = chunk.metadata.get("input_tokens")
                        output_tokens = chunk.metadata.get("output_tokens")
            finally:
                aclose = getattr(iterator, "aclose", None)
                if aclose is not None:
                    await aclose()

        timeout = self._task_execution_timeout_seconds()
        if timeout is None:
            await collect()
        else:
            try:
                async with asyncio.timeout(timeout):
                    await collect()
            except TimeoutError as exc:
                raise TimeoutError(f"Task execution timed out after {timeout:.0f}s") from exc

        return response_parts, cost_usd, num_turns, model_used, input_tokens, output_tokens

    async def _process_task(
        self,
        envelope: Envelope,
        stream: str,
        execute_fn: ExecuteFn,
    ) -> None:
        """Process a single dispatched task."""
        self._execute_fn = execute_fn
        start_time = time.monotonic()

        payload = TaskPayload.model_validate_json(envelope.payload)
        logger.info(
            "Processing task %s: sender=%s domain=%s tier=%s text=%.50s",
            payload.task_id,
            payload.sender,
            payload.domain,
            payload.complexity_tier or "unclassified",
            payload.text,
        )

        # Build task context for execution
        task_context: dict[str, Any] = {
            "source": "dispatch",
            "channel": payload.room_id,
            "sender": payload.sender,
            "sender_id": payload.sender_id,
            "thread_id": payload.thread_id,
            "message_id": payload.message_id,
            "channel_name": payload.channel_name,
            "domain": payload.domain,
            "mentions": payload.mentions,
            "has_bot_mention": payload.has_bot_mention,
            "in_active_thread": payload.in_active_thread,
            "thread_context": payload.thread_context,
            "session_id": payload.session_id,
            "context_version": payload.context_version,
            "context_snapshot_id": payload.context_snapshot_id,
            "complexity_tier": payload.complexity_tier,
            "task_type": payload.task_type,
            "metadata": payload.metadata,
        }

        # Build prompt from text + attachment descriptions
        effective_text = payload.text
        if not effective_text.strip() and payload.attachments:
            for att in payload.attachments:
                desc = att.get("description", "")
                if desc:
                    effective_text = desc
                    break

        prompt = effective_text
        if payload.attachments:
            prompt = append_attachments_to_prompt(payload.attachments, prompt)

        prompt_context_version = payload.context_version
        prompt_snapshot_id = payload.context_snapshot_id

        if self._context_runtime is not None and payload.session_id:
            prompt_ctx = await self._context_runtime.build_prompt(payload, prompt)  # type: ignore[attr-defined]
            prompt = prompt_ctx.prompt
            prompt_context_version = prompt_ctx.context_version
            prompt_snapshot_id = prompt_ctx.context_snapshot_id
            task_context["context_version"] = prompt_context_version
            task_context["context_snapshot_id"] = prompt_snapshot_id
            task_context["used_session_context"] = prompt_ctx.used_session_context
        elif payload.thread_context:
            prompt = format_thread_context(payload.thread_context, payload.sender, prompt)

        await self._publish_agent_activity(
            payload,
            phase="started",
            text=f"{self._activity_agent_label(payload)} started working",
            metadata={"domain": payload.domain, "complexity_tier": payload.complexity_tier},
        )

        heartbeat_key = payload.task_id
        if self._heartbeat:
            task_desc = f"{payload.sender}: {effective_text[:80]}"
            add_task = getattr(self._heartbeat, "add_task", None)
            if add_task:
                add_task(heartbeat_key, task_desc)
            publish = getattr(self._heartbeat, "publish", None)
            if publish:
                await publish()

        try:
            (
                response_parts,
                cost_usd,
                num_turns,
                model_used,
                input_tokens,
                output_tokens,
            ) = await self._run_execute_with_timeout(
                execute_fn,
                prompt=prompt,
                context=task_context,
                working_directory=None,
            )

            response = "".join(response_parts)
            duration = time.monotonic() - start_time

            discoveries = extract_discoveries(response) if response else []
            memory_proposals = extract_memory_proposals(response) if response else []

            is_provider_error = response.lstrip().startswith("API Error:")

            if is_provider_error:
                logger.warning(
                    "Task %s: provider returned error text: %.100s",
                    payload.task_id,
                    response,
                )
                if payload.room_id:
                    rid = self._reaction_message_id(payload)
                    react = getattr(self._channel, "react", None)
                    if react:
                        await react(rid, "hourglass_flowing_sand", remove=True)
                        await react(rid, "x")
                await self._publish_agent_activity(
                    payload,
                    phase="failed",
                    text=f"{self._activity_agent_label(payload)} provider error",
                    metadata={"duration_seconds": round(duration, 2)},
                )
                result = TaskResult(
                    task_id=payload.task_id,
                    message_id=payload.message_id,
                    agent=self._identity,
                    status="failure",
                    error=response[:500],
                    duration_seconds=round(duration, 2),
                    complexity_tier=payload.complexity_tier,
                    domain=payload.domain,
                    sender=payload.sender,
                    text=payload.text[:100],
                    discoveries=discoveries,
                    session_id=payload.session_id,
                    context_version=prompt_context_version,
                    context_snapshot_id=prompt_snapshot_id,
                )

            elif response.strip():
                if payload.room_id:
                    thread_target = payload.thread_id or payload.message_id
                    await self._deliver_reply(payload, response, thread_target)

                    if self._thread_affinity:
                        set_agent = getattr(self._thread_affinity, "set_agent", None)
                        if set_agent:
                            claimed = await set_agent(thread_target, self._identity)
                            if not claimed:
                                refresh = getattr(self._thread_affinity, "refresh_ttl", None)
                                if refresh:
                                    await refresh(thread_target)

                    rid = self._reaction_message_id(payload)
                    react = getattr(self._channel, "react", None)
                    if react:
                        await react(rid, "hourglass_flowing_sand", remove=True)
                        await react(rid, "white_check_mark")

                response_ctx = await self._record_context_response(payload, response)
                if response_ctx.context_version is not None:
                    prompt_context_version = response_ctx.context_version
                    prompt_snapshot_id = response_ctx.context_snapshot_id

                result = TaskResult(
                    task_id=payload.task_id,
                    message_id=payload.message_id,
                    agent=self._identity,
                    status="success",
                    response_text=response,
                    duration_seconds=round(duration, 2),
                    cost_usd=cost_usd,
                    num_turns=num_turns,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model_used=model_used,
                    complexity_tier=payload.complexity_tier,
                    domain=payload.domain,
                    sender=payload.sender,
                    text=payload.text[:100],
                    session_id=payload.session_id,
                    context_version=prompt_context_version,
                    context_snapshot_id=prompt_snapshot_id,
                    discoveries=discoveries,
                    memory_proposals=memory_proposals,
                )
                await self._publish_agent_activity(
                    payload,
                    phase="completed",
                    text=f"{self._activity_agent_label(payload)} completed in {duration:.1f}s",
                    metadata={
                        "duration_seconds": round(duration, 2),
                        "response_chars": len(response),
                        "model_used": model_used,
                        "cost_usd": cost_usd,
                    },
                )
                logger.info(
                    "Task %s completed: %d chars in %.1fs",
                    payload.task_id,
                    len(response),
                    duration,
                )

            else:
                if payload.room_id:
                    rid = self._reaction_message_id(payload)
                    react = getattr(self._channel, "react", None)
                    if react:
                        await react(rid, "hourglass_flowing_sand", remove=True)
                        await react(rid, "warning")

                result = TaskResult(
                    task_id=payload.task_id,
                    message_id=payload.message_id,
                    agent=self._identity,
                    status="failure",
                    response_text=None,
                    error="No response generated",
                    duration_seconds=round(duration, 2),
                    cost_usd=cost_usd,
                    num_turns=num_turns,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model_used=model_used,
                    complexity_tier=payload.complexity_tier,
                    domain=payload.domain,
                    sender=payload.sender,
                    text=payload.text[:100],
                    session_id=payload.session_id,
                    context_version=prompt_context_version,
                    context_snapshot_id=prompt_snapshot_id,
                    discoveries=discoveries,
                )
                await self._publish_agent_activity(
                    payload,
                    phase="failed",
                    text="No response generated",
                    metadata={"duration_seconds": round(duration, 2)},
                )
                logger.warning("Task %s: no response generated", payload.task_id)

        except Exception as e:
            duration = time.monotonic() - start_time
            if payload.room_id:
                try:
                    rid = self._reaction_message_id(payload)
                    react = getattr(self._channel, "react", None)
                    if react:
                        await react(rid, "hourglass_flowing_sand", remove=True)
                        await react(rid, "x")
                except Exception:
                    logger.debug("Failed to update reactions for %s", payload.task_id)

            result = TaskResult(
                task_id=payload.task_id,
                message_id=payload.message_id,
                agent=self._identity,
                status="failure",
                error=str(e),
                duration_seconds=round(duration, 2),
                complexity_tier=payload.complexity_tier,
                domain=payload.domain,
                sender=payload.sender,
                text=payload.text[:100],
                session_id=payload.session_id,
                context_version=prompt_context_version,
                context_snapshot_id=prompt_snapshot_id,
            )
            await self._publish_agent_activity(
                payload,
                phase="failed",
                text=f"{self._activity_agent_label(payload)} failed",
                metadata={"duration_seconds": round(duration, 2)},
            )
            logger.error("Task %s failed after %.1fs: %s", payload.task_id, duration, e)

        finally:
            if self._heartbeat:
                remove_task = getattr(self._heartbeat, "remove_task", None)
                if remove_task:
                    remove_task(heartbeat_key)
                publish = getattr(self._heartbeat, "publish", None)
                if publish:
                    await publish()

        # Publish result to results stream
        try:
            await self._bus.publish(
                RESULTS_STREAM,
                result.model_dump_json().encode(),
                msg_type="result",
                maxlen=3000,
            )
        except Exception as e:
            logger.warning("Failed to publish result for %s: %s", payload.task_id, e)

        # ACK the message
        await self._bus.ack(stream, CONSUMER_GROUP, envelope.msg_id)

    async def _record_context_response(self, payload: TaskPayload, response: str) -> Any:
        """Record assistant response in session context, fail-open."""
        if self._context_runtime is None or not payload.session_id:
            from cortex_runtime.context_runtime import ContextPrompt

            return ContextPrompt(
                prompt="",
                session_id=payload.session_id,
                context_version=payload.context_version,
                context_snapshot_id=payload.context_snapshot_id,
            )

        return await self._context_runtime.record_assistant_response(  # type: ignore[attr-defined]
            payload.session_id,
            response,
        )

    async def stop(self) -> None:
        """Signal the consumer to stop."""
        self._running = False
