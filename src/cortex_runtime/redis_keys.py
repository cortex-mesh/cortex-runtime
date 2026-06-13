"""Centralized Redis key patterns for cortex_runtime.

Every Redis key used by cortex_runtime is defined here. This prevents key
collisions, makes the namespace visible at a glance, and ensures
consistent prefixing across all modules.

All keys share the ``cortex:`` prefix. Patterns are grouped by subsystem.

Usage::

    from cortex_runtime.redis_keys import HEARTBEAT_STREAM, agent_hash

    await redis.xadd(HEARTBEAT_STREAM, fields)
    await redis.hgetall(agent_hash("forge"))
"""

from __future__ import annotations

# ── Namespace root ────────────────────────────────────────────────────────

PREFIX = "cortex"

# ── Mesh sync (Redis hashes) ─────────────────────────────────────────────

MESH_PREFIX = f"{PREFIX}:mesh"
MESH_SKILL_PREFIX = f"{MESH_PREFIX}:skill"
MESH_TYPED_PREFIX = f"{MESH_PREFIX}:typed"
MESH_SYNC_PREFIX = f"{MESH_PREFIX}:sync"
MESH_SYNC_RESULTS_STREAM = f"{MESH_SYNC_PREFIX}:results"


def mesh_sync_stream(agent_name: str) -> str:
    """Stream for mesh sync signals. E.g. ``cortex:mesh:sync:forge``."""
    return f"{MESH_SYNC_PREFIX}:{agent_name}"


def mesh_key(file_name: str) -> str:
    """Key for a mesh-synced memory file. E.g. ``cortex:mesh:USER``."""
    return f"{MESH_PREFIX}:{file_name}"


def mesh_skill_key(skill_name: str) -> str:
    """Key for a mesh-synced skill. E.g. ``cortex:mesh:skill:code-review``."""
    return f"{MESH_SKILL_PREFIX}:{skill_name}"


def mesh_typed_key(category: str, name: str) -> str:
    """Key for a mesh-synced typed memory file.

    E.g. ``cortex:mesh:typed:people:ryan``.
    """
    return f"{MESH_TYPED_PREFIX}:{category}:{name}"


# ── Task dispatch (Redis Streams) ────────────────────────────────────────

TASKS_PREFIX = f"{PREFIX}:tasks"
TASKS_AGENT_PREFIX = f"{PREFIX}:tasks:agent"
RESULTS_STREAM = f"{PREFIX}:results"
EVENTS_STREAM = f"{PREFIX}:events"


def tasks_domain_stream(domain: str) -> str:
    """Stream for domain-routed tasks. E.g. ``cortex:tasks:eng``."""
    return f"{TASKS_PREFIX}:{domain}"


def tasks_agent_stream(agent_name: str) -> str:
    """Stream for agent-specific tasks. E.g. ``cortex:tasks:agent:forge``."""
    return f"{TASKS_AGENT_PREFIX}:{agent_name}"


# ── Heartbeat & agent state ──────────────────────────────────────────────

HEARTBEAT_STREAM = f"{PREFIX}:heartbeat"
AGENT_HASH_PREFIX = f"{PREFIX}:agent"


def agent_hash(agent_name: str) -> str:
    """Hash key for agent state. E.g. ``cortex:agent:forge``."""
    return f"{AGENT_HASH_PREFIX}:{agent_name}"


# ── Response tracking (dedup) ────────────────────────────────────────────

RESPONDED_PREFIX = f"{PREFIX}:responded"


def responded_key(message_id: str) -> str:
    """Dedup key for a responded message. E.g. ``cortex:responded:msg123``."""
    return f"{RESPONDED_PREFIX}:{message_id}"


# ── Sessions ─────────────────────────────────────────────────────────────

SESSION_PREFIX = f"{PREFIX}:session"

# ── Domain hot state ─────────────────────────────────────────────────────

DOMAIN_PREFIX = f"{PREFIX}:domain"


def domain_recent_key(domain: str) -> str:
    """Key for domain recent topics list. E.g. ``cortex:domain:eng:recent``."""
    return f"{DOMAIN_PREFIX}:{domain}:recent"


# ── Workspace (worktree mapping) ─────────────────────────────────────────

WORKSPACE_THREAD_PREFIX = f"{PREFIX}:workspace:thread"
WORKSPACE_BRANCH_PREFIX = f"{PREFIX}:workspace:branch"


def workspace_thread_key(thread_id: str) -> str:
    """Key for thread→branch mapping. E.g. ``cortex:workspace:thread:abc``."""
    return f"{WORKSPACE_THREAD_PREFIX}:{thread_id}"


def workspace_branch_key(branch_name: str) -> str:
    """Key for branch→thread mapping. E.g. ``cortex:workspace:branch:feat/foo``."""
    return f"{WORKSPACE_BRANCH_PREFIX}:{branch_name}"


# ── Thread affinity (dispatch routing) ───────────────────────────────────

THREAD_AGENT_PREFIX = f"{PREFIX}:thread:agent"


def thread_agent_key(thread_id: str) -> str:
    """Key for thread→agent affinity mapping. E.g. ``cortex:thread:agent:abc123``."""
    return f"{THREAD_AGENT_PREFIX}:{thread_id}"


# ── Approval flow ────────────────────────────────────────────────────────

APPROVAL_PREFIX = f"{PREFIX}:approval"

# ── Vault ────────────────────────────────────────────────────────────────

VAULT_PREFIX = f"{PREFIX}:vault"
VAULT_LOCK_KEY = f"{VAULT_PREFIX}:lock"


def vault_secret_key(var_name: str) -> str:
    """Key for a cached vault secret. E.g. ``cortex:vault:REDIS_PASSWORD``."""
    return f"{VAULT_PREFIX}:{var_name}"


# ── Config ───────────────────────────────────────────────────────────────

CONFIG_PREFIX = f"{PREFIX}:config"
LIGHT_LLM_CONFIG_KEY = f"{CONFIG_PREFIX}:light_llm_provider"
AGENT_RUNTIME_CONFIG_PREFIX = f"{CONFIG_PREFIX}:agent"


def agent_runtime_config_key(agent_name: str) -> str:
    """Hash key for effective runtime config. E.g. ``cortex:config:agent:forge``."""
    return f"{AGENT_RUNTIME_CONFIG_PREFIX}:{agent_name}"


# ── Scheduler ────────────────────────────────────────────────────────────

SCHEDULE_PREFIX = f"{PREFIX}:schedule"
SCHEDULE_CONFIG_CHANGED = f"{SCHEDULE_PREFIX}:config_changed"
SCHEDULER_LIVENESS_KEY = f"{SCHEDULE_PREFIX}:liveness"
SCHEDULER_LEADER_LEASE_KEY = f"{SCHEDULE_PREFIX}:leader_lease"

# ── Fleet updates ────────────────────────────────────────────────────────

FLEET_UPDATE_PREFIX = f"{PREFIX}:fleet:update"
FLEET_RESULTS_STREAM = f"{FLEET_UPDATE_PREFIX}:results"


def fleet_update_stream(agent_name: str) -> str:
    """Stream for fleet update signals. E.g. ``cortex:fleet:update:forge``."""
    return f"{FLEET_UPDATE_PREFIX}:{agent_name}"


# ── Outcomes ─────────────────────────────────────────────────────────────

OUTCOMES_STREAM = f"{PREFIX}:outcomes"
OUTCOME_COLLECTOR_CURSOR = f"{PREFIX}:outcome-collector:cursor"

# ── Idle watcher ─────────────────────────────────────────────────────────

IDLE_DISPATCH_PREFIX = f"{PREFIX}:idle-dispatch"

# ── CI reservation ──────────────────────────────────────────────────────

CI_RESERVED_PREFIX = f"{PREFIX}:ci-reserved"


def ci_reserved_key(agent_name: str) -> str:
    """Key for CI reservation flag. E.g. ``cortex:ci-reserved:forge``."""
    return f"{CI_RESERVED_PREFIX}:{agent_name}"


# ── Plans ─────────────────────────────────────────────────────────────

PLANS_PREFIX = f"{PREFIX}:plans"
PLANS_ALL_SET = f"{PLANS_PREFIX}:all"
PLANS_ACTIVE_SET = f"{PLANS_PREFIX}:active"


def plan_key(plan_id: str) -> str:
    """Key for plan metadata hash. E.g. ``cortex:plans:abc123``."""
    return f"{PLANS_PREFIX}:{plan_id}"


def plan_status_key(plan_id: str) -> str:
    """Key for subtask status hash. E.g. ``cortex:plans:abc123:status``."""
    return f"{PLANS_PREFIX}:{plan_id}:status"


# ── Tenant (cloud multi-user identity) ──────────────────────────────────

TENANT_PREFIX = f"{PREFIX}:tenant"


def tenant_user_key(tenant: str, slack_id: str) -> str:
    """Key for a tenant user hash. E.g. ``cortex:tenant:acme:users:U123``."""
    return f"{TENANT_PREFIX}:{tenant}:users:{slack_id}"


def tenant_admins_key(tenant: str) -> str:
    """Key for tenant admin set. E.g. ``cortex:tenant:acme:admins``."""
    return f"{TENANT_PREFIX}:{tenant}:admins"


# ── Org partitioning ─────────────────────────────────────────────────────
# A conductor's orchestration state is partitioned by org so that one
# conductor per org never collides with another on a shared global key.
# The fleet/personal conductor keeps the legacy un-prefixed ``cortex:*``
# namespace; only hosted per-org conductors get a ``cortex:{org_id}:*``
# partition. See ``Keyspace`` below.

FLEET_ORG_ID = "personal"
"""Org id of the fleet/personal mesh conductor.

Its :class:`Keyspace` renders to the legacy global ``cortex:*`` namespace
(no ``{org_id}`` segment) so the live fleet is untouched by partitioning.
"""


def _is_fleet_org(org_id: str | None) -> bool:
    """Whether *org_id* maps to the legacy global (fleet) namespace."""
    return not org_id or org_id == FLEET_ORG_ID


class Keyspace:
    """Builds org-partitioned Redis keys for conductor orchestration state.

    The fleet/personal conductor keeps the legacy global namespace (see
    :data:`FLEET_ORG_ID`), so constructing a ``Keyspace`` for it yields
    exactly the same keys as the module-level helpers.

    Example::

        fleet = Keyspace()                  # or Keyspace("personal")
        fleet.responded_key("m1")           # -> "cortex:responded:m1"

        demo = Keyspace("demo")
        demo.responded_key("m1")            # -> "cortex:demo:responded:m1"
    """

    __slots__ = ("_org_id",)

    def __init__(self, org_id: str | None = None) -> None:
        normalized = org_id.strip().lower() if org_id is not None else None
        self._org_id = None if _is_fleet_org(normalized) else normalized

    @classmethod
    def fleet(cls) -> Keyspace:
        """Keyspace for the fleet/personal mesh (legacy global namespace)."""
        return cls(None)

    @property
    def org_id(self) -> str | None:
        """Partition org id, or ``None`` for the fleet/global namespace."""
        return self._org_id

    @property
    def is_fleet(self) -> bool:
        """Whether this keyspace is the legacy global (fleet) namespace."""
        return self._org_id is None

    def _scoped(self, suffix: str) -> str:
        if self._org_id is None:
            return f"{PREFIX}:{suffix}"
        return f"{PREFIX}:{self._org_id}:{suffix}"

    # ── Mesh sync ──
    @property
    def mesh_prefix(self) -> str:
        return self._scoped("mesh")

    @property
    def mesh_skill_prefix(self) -> str:
        return self._scoped("mesh:skill")

    @property
    def mesh_typed_prefix(self) -> str:
        return self._scoped("mesh:typed")

    @property
    def mesh_sync_results_stream(self) -> str:
        return self._scoped("mesh:sync:results")

    def mesh_key(self, file_name: str) -> str:
        return self._scoped(f"mesh:{file_name}")

    def mesh_skill_key(self, skill_name: str) -> str:
        return self._scoped(f"mesh:skill:{skill_name}")

    def mesh_typed_key(self, category: str, name: str) -> str:
        return self._scoped(f"mesh:typed:{category}:{name}")

    def mesh_sync_stream(self, agent_name: str) -> str:
        return self._scoped(f"mesh:sync:{agent_name}")

    # ── Task dispatch ──
    @property
    def stream_prefix(self) -> str:
        """Bus stream prefix for org-scoped bus configuration."""
        return PREFIX if self._org_id is None else f"{PREFIX}:{self._org_id}"

    def tasks_domain_stream(self, domain: str) -> str:
        return self._scoped(f"tasks:{domain}")

    def tasks_agent_stream(self, agent_name: str) -> str:
        return self._scoped(f"tasks:agent:{agent_name}")

    @property
    def results_stream(self) -> str:
        return self._scoped("results")

    @property
    def events_stream(self) -> str:
        return self._scoped("events")

    # ── Response tracking (dedup / claim) ──
    @property
    def responded_prefix(self) -> str:
        return self._scoped("responded")

    def responded_key(self, message_id: str) -> str:
        return self._scoped(f"responded:{message_id}")

    # ── Thread affinity ──
    def thread_agent_key(self, thread_id: str) -> str:
        return self._scoped(f"thread:agent:{thread_id}")

    # ── Workspace (worktree mapping) ──
    @property
    def workspace_thread_prefix(self) -> str:
        return self._scoped("workspace:thread")

    def workspace_thread_key(self, thread_id: str) -> str:
        return self._scoped(f"workspace:thread:{thread_id}")

    def workspace_branch_key(self, branch_name: str) -> str:
        return self._scoped(f"workspace:branch:{branch_name}")

    # ── Domain hot state ──
    def domain_recent_key(self, domain: str) -> str:
        return self._scoped(f"domain:{domain}:recent")

    # ── Sessions ──
    @property
    def session_prefix(self) -> str:
        return self._scoped("session")

    # ── Outcomes ──
    @property
    def outcomes_stream(self) -> str:
        return self._scoped("outcomes")

    @property
    def outcome_collector_cursor(self) -> str:
        return self._scoped("outcome-collector:cursor")

    # ── Plans ──
    @property
    def plans_prefix(self) -> str:
        return self._scoped("plans")

    @property
    def plans_all_set(self) -> str:
        return self._scoped("plans:all")

    @property
    def plans_active_set(self) -> str:
        return self._scoped("plans:active")

    def plan_key(self, plan_id: str) -> str:
        return self._scoped(f"plans:{plan_id}")

    def plan_status_key(self, plan_id: str) -> str:
        return self._scoped(f"plans:{plan_id}:status")

    def plan_decision_key(self, plan_id: str) -> str:
        return self._scoped(f"plans:decision:{plan_id}")

    # ── Scheduler ──
    @property
    def schedule_prefix(self) -> str:
        return self._scoped("schedule")

    @property
    def schedule_config_changed(self) -> str:
        return self._scoped("schedule:config_changed")

    @property
    def scheduler_liveness_key(self) -> str:
        return self._scoped("schedule:liveness")

    @property
    def scheduler_leader_lease_key(self) -> str:
        return self._scoped("schedule:leader_lease")

    def workflow_cron_prefix(self, workflow_name: str) -> str:
        return self._scoped(f"workflow:cron:{workflow_name}")
