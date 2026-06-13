"""Channel-agnostic context runtime for dispatch tasks.

The runtime is the narrow facade between channel transport, Redis-stream task
dispatch, and provider prompt construction. Channels may still provide raw
thread history, but the runtime records and renders its own session state
whenever Redis session storage is available.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from cortex_runtime.dispatch_models import TaskPayload
from cortex_runtime.models import Department, Domain
from cortex_runtime.session.models import Session, SessionContext, SessionMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContextPrompt:
    """Rendered prompt plus context metadata for a provider execution."""

    prompt: str
    session_id: str | None = None
    context_version: int | None = None
    context_snapshot_id: str | None = None
    used_session_context: bool = False


class ContextRuntime:
    """Owns session lookup, transcript writes, and prompt context rendering."""

    def __init__(self, session_manager: Any) -> None:
        self._session_manager = session_manager
        self._store = session_manager._store

    @property
    def session_manager(self) -> Any:
        return self._session_manager

    async def prepare_payload(self, payload: TaskPayload) -> TaskPayload:
        """Record the incoming message and attach session metadata to a payload.

        Fail-open: context runtime failures degrade to the compatibility
        ``thread_context`` path rather than blocking dispatch.
        """
        try:
            domain = _parse_domain(payload.domain)
            session = await self._session_manager.get_or_create(
                channel=_channel(payload),
                thread_id=_session_thread_id(payload),
                sender_id=payload.sender_id,
                room_id=payload.room_id or None,
                channel_name=payload.channel_name or None,
                domain=domain,
            )

            if session.turn_count == 0 and payload.thread_context:
                session = await self._bootstrap_from_thread_context(session, payload)

            session = await self._session_manager.record_message(
                session,
                SessionMessage(
                    message_id=payload.message_id,
                    sender=payload.sender,
                    sender_id=payload.sender_id,
                    text=payload.text,
                    timestamp=payload.dispatched_at,
                    metadata={
                        "task_id": payload.task_id,
                        "source": _channel(payload),
                        "room_id": payload.room_id,
                        "thread_id": payload.thread_id,
                        "domain": payload.domain,
                    },
                ),
            )

            context_version = session.turn_count
            return payload.model_copy(
                update={
                    "session_id": session.session_id,
                    "context_version": context_version,
                    "context_snapshot_id": _snapshot_id(session.session_id, context_version),
                }
            )
        except Exception:
            logger.warning(
                "Context runtime failed to prepare payload %s; using compatibility context",
                payload.task_id,
                exc_info=True,
            )
            return payload

    async def build_prompt(self, payload: TaskPayload, current_prompt: str) -> ContextPrompt:
        """Build a provider prompt from CORTEX-owned session context."""
        if not payload.session_id:
            return ContextPrompt(prompt=current_prompt)

        try:
            session: Session | None = await self._store.get(payload.session_id)
            if session is None:
                return ContextPrompt(prompt=current_prompt, session_id=payload.session_id)

            context: SessionContext = await self._store.get_context(session.session_id)
            rendered = _render_context(context, current_message_id=payload.message_id)
            if rendered:
                prompt = "\n".join(
                    [
                        rendered,
                        "",
                        f"[Current message from {payload.sender}]",
                        current_prompt,
                    ]
                )
            else:
                prompt = current_prompt

            context_version = session.turn_count
            return ContextPrompt(
                prompt=prompt,
                session_id=session.session_id,
                context_version=context_version,
                context_snapshot_id=_snapshot_id(session.session_id, context_version),
                used_session_context=True,
            )
        except Exception:
            logger.warning(
                "Context runtime failed to build prompt for task %s; using compatibility context",
                payload.task_id,
                exc_info=True,
            )
            return ContextPrompt(
                prompt=current_prompt,
                session_id=payload.session_id,
                context_version=payload.context_version,
                context_snapshot_id=payload.context_snapshot_id,
            )

    async def record_assistant_response(
        self,
        session_id: str | None,
        response_text: str,
    ) -> ContextPrompt:
        """Record an assistant response back into the CORTEX session."""
        if not session_id or not response_text.strip():
            return ContextPrompt(prompt="", session_id=session_id)

        try:
            session: Session | None = await self._store.get(session_id)
            if session is None:
                return ContextPrompt(prompt="", session_id=session_id)
            updated = await self._session_manager.record_response(session, response_text)
            version = updated.turn_count
            return ContextPrompt(
                prompt="",
                session_id=updated.session_id,
                context_version=version,
                context_snapshot_id=_snapshot_id(updated.session_id, version),
                used_session_context=True,
            )
        except Exception:
            logger.warning(
                "Context runtime failed to record assistant response for session %s",
                session_id,
                exc_info=True,
            )
            return ContextPrompt(prompt="", session_id=session_id)

    async def _bootstrap_from_thread_context(
        self,
        session: Session,
        payload: TaskPayload,
    ) -> Session:
        """Seed a new session from channel-provided raw history."""
        messages = _bootstrap_messages(payload)
        for idx, msg in enumerate(messages):
            session = await self._session_manager.record_message(
                session,
                SessionMessage(
                    message_id=f"{payload.message_id}:bootstrap:{idx}",
                    sender=msg["sender"],
                    sender_id=msg.get("sender_id") or msg["sender"],
                    text=msg["text"],
                    timestamp=payload.dispatched_at,
                    is_bot=_looks_like_bot(msg["sender"]),
                    metadata={
                        "source": "thread_context_bootstrap",
                        "task_id": payload.task_id,
                    },
                ),
            )
        return session


def _channel(payload: TaskPayload) -> str:
    source = payload.metadata.get("source")
    return str(source or "dispatch")


def _session_thread_id(payload: TaskPayload) -> str:
    if payload.thread_id:
        return payload.thread_id
    if payload.metadata.get("dm_target"):
        return f"dm:{payload.room_id or payload.metadata.get('dm_target')}:{payload.sender_id}"
    if payload.room_id:
        return payload.message_id
    workflow = payload.metadata.get("workflow_run_id") or payload.metadata.get("dashboard_task_id")
    if workflow:
        return f"{_channel(payload)}:{workflow}"
    return payload.message_id


def _parse_domain(raw_domain: str) -> Domain:
    aliases = {"dev": "eng", "": "general"}
    raw = aliases.get(raw_domain, raw_domain)
    try:
        return Domain.parse(raw)
    except Exception:
        logger.debug("Unknown context domain %r; falling back to personal", raw_domain)
        return Domain(Department.PERSONAL)


def _bootstrap_messages(payload: TaskPayload) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for raw in payload.thread_context:
        sender = str(raw.get("sender", "unknown"))
        text = str(raw.get("text", ""))
        if text.strip():
            messages.append(
                {
                    "sender": sender,
                    "sender_id": str(raw.get("sender_id", sender)),
                    "text": text,
                }
            )

    if messages:
        last = messages[-1]
        if last["text"].strip() == payload.text.strip() and last["sender"] == payload.sender:
            messages.pop()
    return messages


def _looks_like_bot(sender: str) -> bool:
    lowered = sender.lower()
    return "(assistant)" in lowered or lowered.endswith(" assistant")


def _render_context(context: SessionContext, *, current_message_id: str) -> str:
    sections: list[str] = []

    if context.cold_reference:
        sections.append(f"[Archived conversation: {context.cold_message_count} messages]")

    if context.warm_summary:
        if sections:
            sections.append("")
        sections.append(f"[Conversation memory ({context.warm_message_count} messages)]")
        sections.append(context.warm_summary.strip())

    hot_messages = tuple(
        msg for msg in context.hot_messages if msg.message_id != current_message_id
    )
    if hot_messages:
        if sections:
            sections.append("")
        sections.append(f"[Recent conversation - {len(hot_messages)} messages]")
        for msg in hot_messages:
            sender = f"{msg.sender} (assistant)" if msg.is_bot else msg.sender
            sections.append(f"{sender}: {msg.text}")

    return "\n".join(sections)


def _snapshot_id(session_id: str, context_version: int) -> str:
    return f"{session_id}:v{context_version}"
