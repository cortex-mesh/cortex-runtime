"""Session data models for cortex_runtime."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from cortex_runtime.models import Domain
from cortex_runtime.redis_keys import Keyspace


class SessionLifecycleState(StrEnum):
    ACTIVE = "active"
    IDLE = "idle"
    ARCHIVED = "archived"


class SessionMessage(BaseModel):
    """A single message within a session."""

    message_id: str
    sender: str
    sender_id: str
    text: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_bot: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionContext(BaseModel):
    """Tiered session context for prompt injection."""

    session_id: str
    hot_messages: list[SessionMessage] = Field(default_factory=list)
    warm_summary: str | None = None
    warm_message_count: int = 0
    cold_reference: str | None = None
    cold_message_count: int = 0
    context_version: int = 0
    context_snapshot_id: str | None = None


class Session(BaseModel):
    """A conversation session between a user and an agent."""

    session_id: str = Field(default_factory=lambda: uuid4().hex)
    channel: str
    domain: Domain
    thread_id: str
    room_id: str | None = None
    participants: frozenset[str] = Field(default_factory=frozenset)
    state: SessionLifecycleState = SessionLifecycleState.ACTIVE
    turn_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_activity_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    context_version: int = 0
    context_snapshot_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


class DomainContext(BaseModel):
    """Loaded domain memory context for prompt injection."""

    domain: Domain
    context_md: str = ""
    skills_md: str = ""
    recent_topics: tuple[str, ...] = Field(default_factory=tuple)

    model_config = {"arbitrary_types_allowed": True}


class SessionConfig(BaseModel):
    """Configuration for SessionManager and SessionStore."""

    memory_base_path: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("CORTEX_MEMORY_PATH", "~/.cortex/memory")
        ).expanduser()
    )
    hot_window_size: int = 20
    warm_summary_threshold: int = 50
    domain_recent_limit: int = 10
    synthetic_thread_ttl_seconds: int = 3600
    key_prefix: str = Field(
        default_factory=lambda: Keyspace(os.environ.get("CORTEX_ORG_ID")).session_prefix
    )

    def get_domain_dir(self, domain: Domain) -> Path:
        return self.memory_base_path / domain.value

    model_config = {"arbitrary_types_allowed": True}
