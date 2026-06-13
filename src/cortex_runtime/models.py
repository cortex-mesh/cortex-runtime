"""Core data models for cortex_runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from cortex_runtime.redis_keys import Keyspace

# ── Domain / Department ──────────────────────────────────────────────────


class Department(StrEnum):
    """Organizational department — maps to a Redis domain stream."""

    PERSONAL = "personal"
    BUSINESS = "business"
    ENG = "eng"
    OPS = "ops"
    CORTEX = "cortex"
    FINANCE = "finance"
    RESEARCH = "research"
    THOUGHTS = "thoughts"
    MAKER = "maker"
    CREATIVE = "creative"
    SYNAPSE = "synapse"
    GENERAL = "general"


@dataclass(frozen=True)
class Domain:
    """A routing domain, wrapping a Department value.

    Domains map to Redis stream names (``cortex:tasks:{domain.value}``).
    Use :meth:`parse` to construct from an unknown string.
    """

    department: Department

    @property
    def value(self) -> str:
        return self.department.value

    @classmethod
    def parse(cls, raw: str) -> Domain:
        """Parse a domain string, raising ValueError on unknown department."""
        try:
            dept = Department(raw.lower().strip())
        except ValueError:
            raise ValueError(f"Unknown department: {raw!r}") from None
        return cls(dept)

    def __str__(self) -> str:
        return self.value


# ── Task priority ────────────────────────────────────────────────────────


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


# ── Session state ────────────────────────────────────────────────────────


class SessionState(StrEnum):
    ACTIVE = "active"
    IDLE = "idle"
    ARCHIVED = "archived"


# ── Stream chunk kind ────────────────────────────────────────────────────


class StreamChunkKind(StrEnum):
    OUTPUT = "output"
    COMPLETE = "complete"
    ERROR = "error"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


# ── Stream chunk ──────────────────────────────────────────────────────────


class StreamChunk(BaseModel):
    """A chunk of streaming output from a provider."""

    kind: StreamChunkKind
    data: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Health status ─────────────────────────────────────────────────────────


class HealthStatus(BaseModel):
    """Health report from a provider or bus."""

    ok: bool
    latency_ms: float | None = None
    error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


# ── Envelope ──────────────────────────────────────────────────────────────


class Envelope(BaseModel):
    """A message envelope from a Redis Stream."""

    msg_id: str
    payload: bytes
    msg_type: str = "task"
    resumed: bool = False

    model_config = {"arbitrary_types_allowed": True}


# ── Bus config ────────────────────────────────────────────────────────────


class BusConfig(BaseModel):
    """Configuration for RedisStreamBus.

    ``stream_prefix`` scopes all stream names (e.g. ``"cortex"`` → streams
    like ``"cortex:tasks:eng"``). For hosted orgs, pass the org-partitioned
    prefix from ``Keyspace(org_id).stream_prefix``.

    Connection parameters mirror ``redis.asyncio.Redis`` constructor kwargs.
    Use ``get_redis_config()`` from :mod:`cortex_runtime.env` to populate
    host/port/password from environment variables.
    """

    stream_prefix: str = Field(
        default_factory=lambda: Keyspace(os.environ.get("CORTEX_ORG_ID")).stream_prefix
    )
    consumer_group: str = "cortex-agents"
    # Redis connection
    host: str = Field(default_factory=lambda: os.environ.get("REDIS_HOST", "localhost"))
    port: int = Field(default_factory=lambda: int(os.environ.get("REDIS_PORT", "6379")))
    password: str | None = Field(
        default_factory=lambda: os.environ.get("REDIS_PASSWORD") or None
    )
    db: int = 0
    max_connections: int = 20
    socket_timeout: float = 10.0
    health_check_interval: int = 30
    # Bus tuning
    block_ms: int = 5000
    claim_idle_ms: int = 30_000
    read_watchdog_ms: int = 60_000
    retry_backoff_base: float = 1.0
    max_retries: int = 3
