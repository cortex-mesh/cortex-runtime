"""Session manager for cortex_runtime."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from cortex_runtime.models import Department, Domain
from cortex_runtime.session.exceptions import DomainNotFoundError
from cortex_runtime.session.models import (
    DomainContext,
    Session,
    SessionConfig,
    SessionLifecycleState,
    SessionMessage,
)

if TYPE_CHECKING:
    from cortex_runtime.session.store import SessionStore

logger = logging.getLogger(__name__)

DomainResolverFn = Callable[[str], Domain | None]


class SessionManager:
    """High-level session management interface.

    Coordinates session lookup/creation, context management,
    and domain memory loading. Abstracts away the storage layer.
    """

    def __init__(
        self,
        store: SessionStore,
        config: SessionConfig | None = None,
        identity: str | None = None,
        domain_resolver: DomainResolverFn | None = None,
    ) -> None:
        self._store = store
        self._config = config or SessionConfig()
        self._domain_cache: dict[Domain, DomainContext] = {}
        self._identity = identity or os.environ.get("CORTEX_IDENTITY", "cortex")
        self._domain_resolver = domain_resolver

    # ── Session Operations ───────────────────────────────────────────────────

    async def get_or_create(
        self,
        channel: str,
        thread_id: str | None,
        sender_id: str,
        room_id: str | None = None,
        channel_name: str | None = None,
        domain: Domain | str | None = None,
    ) -> Session:
        """Get existing session or create new one."""
        resolved_domain = self._coerce_domain(domain) if domain is not None else None
        if resolved_domain is None:
            resolved_domain = self._resolve_domain(channel, channel_name, room_id)

        effective_thread_id = thread_id
        if thread_id is None:
            effective_thread_id = await self._get_or_create_synthetic_thread(channel, sender_id)

        assert effective_thread_id is not None

        session = await self._store.get_by_thread(resolved_domain, effective_thread_id)
        if session:
            logger.debug(
                "Found existing session %s for %s:%s",
                session.session_id,
                resolved_domain.value,
                effective_thread_id,
            )
            return session

        session = await self._store.create(
            channel=channel,
            domain=resolved_domain,
            thread_id=effective_thread_id,
            room_id=room_id,
            participants=frozenset({sender_id}),
        )

        logger.info(
            "Created new session %s for %s:%s",
            session.session_id,
            resolved_domain.value,
            effective_thread_id,
        )
        return session

    async def record_message(
        self,
        session: Session,
        message: SessionMessage,
    ) -> Session:
        """Record a message in the session."""
        return await self._store.add_message(session.session_id, message)

    async def record_response(
        self,
        session: Session,
        response_text: str,
    ) -> Session:
        """Record a bot response, incrementing turn count."""
        bot_message = SessionMessage(
            message_id=f"bot-{uuid4().hex[:8]}",
            sender=self._identity.capitalize(),
            sender_id=self._identity,
            text=response_text,
            timestamp=datetime.now(UTC),
            is_bot=True,
        )
        session = await self._store.add_message(session.session_id, bot_message)
        updated = Session(
            **{
                **session.model_dump(),
                "turn_count": session.turn_count + 1,
                "updated_at": datetime.now(UTC),
            }
        )
        return await self._store.update(updated)

    async def touch(self, session: Session) -> Session:
        """Update last_activity_at to prevent idle/archive transitions."""
        updated = Session(
            **{
                **session.model_dump(),
                "last_activity_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )
        return await self._store.update(updated)

    async def close(self, session: Session) -> Session:
        """Explicitly close a session (move to ARCHIVED)."""
        updated = Session(
            **{
                **session.model_dump(),
                "state": SessionLifecycleState.ARCHIVED,
                "updated_at": datetime.now(UTC),
            }
        )
        return await self._store.update(updated)

    # ── Context Building ─────────────────────────────────────────────────────

    async def get_context_for_prompt(
        self,
        session: Session,
        include_domain: bool = True,
    ) -> str:
        """Build context string for LLM prompt."""
        sections: list[str] = []

        if include_domain:
            domain_ctx = await self.load_domain_memory(session.domain)

            if domain_ctx.context_md:
                sections.append(f"[Domain: {session.domain.value.upper()}]")
                sections.append(domain_ctx.context_md.strip())
                sections.append("")

            if domain_ctx.recent_topics:
                sections.append("[Recent domain activity]")
                for topic in domain_ctx.recent_topics[:5]:
                    sections.append(f"- {topic}")
                sections.append("")

        context = await self._store.get_context(session.session_id)

        if context.cold_reference:
            sections.append(f"[Archived history: {context.cold_message_count} messages]")
            sections.append("")

        if context.warm_summary:
            sections.append(f"[Conversation summary ({context.warm_message_count} messages)]")
            sections.append(context.warm_summary.strip())
            sections.append("")

        if context.hot_messages:
            sections.append(f"[Recent conversation - {len(context.hot_messages)} messages]")
            for msg in context.hot_messages:
                sender = msg.sender
                if msg.is_bot:
                    sender = f"{msg.sender} (bot)"
                sections.append(f"{sender}: {msg.text}")
            sections.append("")

        return "\n".join(sections)

    # ── Domain Operations ────────────────────────────────────────────────────

    async def load_domain_memory(self, domain: Domain) -> DomainContext:
        """Load domain context from memory files."""
        if domain in self._domain_cache:
            return self._domain_cache[domain]

        domain_dir = self._config.get_domain_dir(domain)

        context_md = ""
        skills_md = ""

        context_file = domain_dir / "CONTEXT.md"
        skills_file = domain_dir / "SKILLS.md"

        if context_file.exists():
            try:
                context_md = context_file.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning("Failed to read %s: %s", context_file, e)

        if skills_file.exists():
            try:
                skills_md = skills_file.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning("Failed to read %s: %s", skills_file, e)

        recent_topics: tuple[str, ...] = ()
        try:
            recent_topics = await self._store.get_domain_recent_topics(
                domain, self._config.domain_recent_limit
            )
        except Exception as e:
            logger.warning("Failed to load domain hot state for %s: %s", domain.value, e)

        domain_ctx = DomainContext(
            domain=domain,
            context_md=context_md,
            skills_md=skills_md,
            recent_topics=recent_topics,
        )

        self._domain_cache[domain] = domain_ctx
        return domain_ctx

    async def get_domain_context(self, domain: Domain) -> DomainContext:
        """Get domain context (alias for load_domain_memory)."""
        return await self.load_domain_memory(domain)

    def invalidate_domain_cache(self, domain: Domain | None = None) -> None:
        """Invalidate cached domain context."""
        if domain:
            self._domain_cache.pop(domain, None)
        else:
            self._domain_cache.clear()

    async def update_domain_activity(
        self,
        domain: Domain,
        topic: str,
    ) -> None:
        """Update domain hot state with recent activity."""
        try:
            await self._store.add_domain_recent_topic(
                domain, topic, self._config.domain_recent_limit
            )
            self.invalidate_domain_cache(domain)
        except Exception as e:
            logger.warning("Failed to update domain hot state for %s: %s", domain.value, e)

    # ── Private Helpers ──────────────────────────────────────────────────────

    def _resolve_domain(
        self,
        channel: str,
        channel_name: str | None,
        room_id: str | None,
    ) -> Domain:
        """Resolve the domain for a message."""
        if channel_name and self._domain_resolver:
            domain = self._domain_resolver(channel_name)
            if domain:
                return domain

        if room_id and self._domain_resolver:
            domain = self._domain_resolver(room_id)
            if domain:
                return domain

        channel_defaults: dict[str, Domain] = {
            "imessage": Domain(Department.PERSONAL),
            "slack": Domain(Department.BUSINESS),
        }

        if channel in channel_defaults:
            return channel_defaults[channel]

        if channel == "synapse":
            raise DomainNotFoundError(channel_name or room_id or "unknown")

        return Domain(Department.PERSONAL)

    def _coerce_domain(self, domain: Domain | str) -> Domain:
        """Convert a domain input into a Domain, including legacy aliases."""
        if isinstance(domain, Domain):
            return domain
        aliases = {"dev": "eng"}
        raw = aliases.get(domain, domain)
        return Domain.parse(raw)

    async def _get_or_create_synthetic_thread(
        self,
        channel: str,
        sender_id: str,
    ) -> str:
        """Get or create a synthetic thread for threadless channels."""
        existing: str | None = await self._store.get_synthetic_thread(channel, sender_id)  # type: ignore[attr-defined]
        if existing:
            await self._store.touch_synthetic_thread(channel, sender_id)  # type: ignore[attr-defined]
            logger.debug(
                "Reusing synthetic thread %s for %s:%s",
                existing,
                channel,
                sender_id,
            )
            return existing

        synthetic_id = f"synthetic:{channel}:{sender_id}:{uuid4().hex[:8]}"
        await self._store.set_synthetic_thread(channel, sender_id, synthetic_id)  # type: ignore[attr-defined]

        logger.debug(
            "Created synthetic thread %s for %s:%s",
            synthetic_id,
            channel,
            sender_id,
        )
        return synthetic_id
