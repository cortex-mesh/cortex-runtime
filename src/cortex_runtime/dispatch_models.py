"""Dispatch wire models for cortex_runtime.

These models cross the wire between conductor and agent via Redis Streams.
They are separate from the core models to keep the bus payload schema
versioned independently of the runtime's internal types.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

# ── Stream name constants ────────────────────────────────────────────────

DOMAIN_STREAM_PREFIX = "tasks"
AGENT_STREAM_PREFIX = "tasks:agent"


# ── Dispatch result ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class DispatchResult:
    """Result of a successful dispatch operation."""

    stream_id: str
    agent: str
    domain: str


# ── Memory proposal (ADR-056 §7.1) ──────────────────────────────────────


class MemoryProposal(BaseModel):
    """A typed memory write-back proposal emitted by an agent.

    These are extracted from ``[MEMORY: category/name]`` markers in agent
    output and forwarded to the conductor for staged human approval.
    No memory is written on the agent side — agents only propose.
    """

    category: str
    name: str
    mode: Literal["create", "update"] = "create"
    content: str


# ── Task payload ─────────────────────────────────────────────────────────


class TaskPayload(BaseModel):
    """Payload published to a Redis Stream for agent consumption.

    The conductor builds this from a channel message; the agent deserializes
    it with ``TaskPayload.model_validate_json(envelope.payload)``.
    """

    task_id: str = Field(default_factory=lambda: uuid4().hex)
    message_id: str
    thread_id: str | None = None
    channel_name: str = ""
    room_id: str | None = None
    domain: str = "personal"
    sender: str = ""
    sender_id: str = ""
    text: str = ""
    mentions: list[str] = Field(default_factory=list)
    has_bot_mention: bool = False
    in_active_thread: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    thread_context: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    preferred_agent: str | None = None
    complexity_tier: str | None = None
    task_type: str | None = None
    # Session context fields (set by ContextRuntime)
    session_id: str | None = None
    context_version: int | None = None
    context_snapshot_id: str | None = None
    dispatched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ── Task result ───────────────────────────────────────────────────────────


class TaskResult(BaseModel):
    """Result published to the results stream after task completion."""

    task_id: str
    message_id: str
    agent: str
    status: Literal["success", "failure"]
    response_text: str | None = None
    error: str | None = None
    duration_seconds: float | None = None
    cost_usd: float | None = None
    num_turns: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_used: str | None = None
    complexity_tier: str | None = None
    domain: str = ""
    sender: str = ""
    text: str = ""
    discoveries: list[str] = Field(default_factory=list)
    memory_proposals: list[MemoryProposal] = Field(default_factory=list)
    session_id: str | None = None
    context_version: int | None = None
    context_snapshot_id: str | None = None


# ── Execution metrics ─────────────────────────────────────────────────────


@dataclass
class ExecutionMetrics:
    """Metrics collected during task execution."""

    duration_seconds: float = 0.0
    cost_usd: float | None = None
    num_turns: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_used: str | None = None
