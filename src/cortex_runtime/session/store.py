"""SessionStore Protocol for cortex_runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from cortex_runtime.models import Domain
    from cortex_runtime.session.models import (
        Session,
        SessionContext,
        SessionMessage,
    )


@runtime_checkable
class SessionStore(Protocol):
    """Protocol for session persistence backends.

    Implementations may be Redis-backed (production), SQLite-backed
    (testing), or in-memory (unit tests). All methods are async.
    """

    async def get(self, session_id: str) -> Session | None:
        """Look up a session by its unique session_id. Returns None if not found."""
        ...

    async def get_by_thread(
        self,
        domain: Domain,
        thread_id: str,
    ) -> Session | None:
        """Look up a session by domain + thread ID. Returns None if not found."""
        ...

    async def create(
        self,
        *,
        channel: str,
        domain: Domain,
        thread_id: str,
        room_id: str | None = None,
        participants: frozenset[str] = frozenset(),
    ) -> Session:
        """Create a new session. Returns the persisted session."""
        ...

    async def update(self, session: Session) -> Session:
        """Persist an updated session. Returns the updated session."""
        ...

    async def add_message(
        self,
        session_id: str,
        message: SessionMessage,
    ) -> Session:
        """Record a message in a session, managing tier overflow.

        Returns the updated session.
        """
        ...

    async def get_context(self, session_id: str) -> SessionContext:
        """Return the tiered context for a session (hot/warm/cold)."""
        ...

    async def get_domain_recent_topics(
        self,
        domain: Domain,
        limit: int = 10,
    ) -> tuple[str, ...]:
        """Return recent topic strings for a domain from Redis hot state."""
        ...

    async def add_domain_recent_topic(
        self,
        domain: Domain,
        topic: str,
        max_length: int = 10,
    ) -> None:
        """Append a topic to the domain's recent-activity list."""
        ...

    async def get_synthetic_thread(
        self,
        channel: str,
        sender_id: str,
    ) -> str | None:
        """Return the current synthetic thread ID for this sender, if any."""
        ...

    async def set_synthetic_thread(
        self,
        channel: str,
        sender_id: str,
        thread_id: str,
    ) -> None:
        """Persist a synthetic thread mapping."""
        ...

    async def touch_synthetic_thread(
        self,
        channel: str,
        sender_id: str,
    ) -> None:
        """Extend the TTL of a synthetic thread mapping."""
        ...
