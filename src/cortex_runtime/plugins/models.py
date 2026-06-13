"""Plugin data models for cortex_runtime."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ActionTier(StrEnum):
    """Permission tier for plugin actions.

    AUTO   — runs without user notification
    NOTIFY — runs but shows user a notification
    APPROVE — requires explicit user approval before running
    """

    AUTO = "auto"
    NOTIFY = "notify"
    APPROVE = "approve"


class PluginHealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class PluginActionInfo(BaseModel):
    """Metadata about a single plugin action."""

    name: str
    description: str
    tier: ActionTier = ActionTier.AUTO
    parameters: dict[str, Any] = Field(default_factory=dict)
    required_parameters: list[str] = Field(default_factory=list)


class PluginResult(BaseModel):
    """Result of executing a plugin action."""

    success: bool
    data: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PluginInfo(BaseModel):
    """Metadata about a registered plugin."""

    name: str
    version: str
    description: str
    actions: list[PluginActionInfo] = Field(default_factory=list)


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timed_out"


class ApprovalRequest(BaseModel):
    """Request for user approval of a plugin action."""

    request_id: str
    plugin: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = 300.0


class ApprovalResponse(BaseModel):
    """Response to an approval request."""

    request_id: str
    status: ApprovalStatus
    approved: bool = False


class PluginHealthReport(BaseModel):
    """Health report from a plugin."""

    plugin: str
    status: PluginHealthStatus
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
