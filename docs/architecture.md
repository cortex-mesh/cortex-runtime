# Architecture

`cortex-runtime` is the kernel of a multi-agent mesh. This page covers the
load-bearing design decisions: why Redis Streams, how the turn loop works,
how session context stays coherent across turns, and how plugins integrate.

---

## System topology

```
Conductor                          Agent(s)
──────────────────────────         ──────────────────────────
TaskDispatcher                     TaskConsumer
    │                                  │
    │  XADD cortex:tasks:{domain}      │
    ├──────────────────────────────────▶ XREADGROUP (consumer group)
    │                                  │
    │  XADD cortex:results             │  execute_fn(prompt, context)
    ◀──────────────────────────────────┤
    │                                  │
        Redis Streams backbone (RedisStreamBus)
```

A mesh has one **conductor** and one or more **agents**. The conductor routes
incoming tasks (via `TaskDispatcher`) onto domain streams or agent-specific
streams. Each agent runs a `TaskConsumer` that blocks on XREADGROUP, executes
tasks, and writes results back.

The runtime ships without a bundled conductor or UI — you supply those.

---

## Bus design: why Redis Streams

The bus (`MessageBus` protocol, `RedisStreamBus` implementation) makes four
commitments that ruled out simpler options:

| Requirement | Design choice |
|-------------|---------------|
| At-least-once delivery with explicit ACK | XREADGROUP + consumer groups |
| Crash recovery without reprocessing from offset 0 | Own-PEL redelivery via XAUTOCLAIM |
| Multi-agent fan-out on domain streams | One stream per domain; each agent is a consumer in the group |
| Agent-specific direct routing | Separate per-agent stream (`cortex:tasks:agent:{name}`) |

**Compared to alternatives:**

- **Kafka** — operationally heavy for a fleet of 2–10 agents; no native
  per-message ACK at the consumer-group level without offset management complexity.
- **SQS / cloud queues** — no offline self-hosted option; adds an AWS dependency
  to what is otherwise a local-first system.
- **pub/sub (Redis PUBLISH)** — fire-and-forget; no at-least-once semantics,
  no crash recovery.

### Stale socket watchdog

Redis keeps TCP connections alive, but a half-open socket (e.g. after a network
partition) will block `XREADGROUP` indefinitely. The consumer uses
`asyncio.wait_for()` around each blocking read with a configurable
`read_watchdog_ms` (default 60 s). On timeout it reconnects and resumes.
This closed a real incident where an agent consumed no tasks for 40+ minutes
after an AWS Redis failover.

### Own-PEL redelivery

On startup, `RedisStreamBus` calls `XAUTOCLAIM` to reclaim any messages in its
own pending-entry list (PEL) that were not ACKed before the last crash. This
prevents messages from sitting in the PEL indefinitely after an agent restart.

---

## Turn loop

A single task execution follows this path:

```
1. XREADGROUP blocks on domain and agent streams
2. Deserialize message → TaskPayload
3. Mark message as "responded" in Redis (idempotency key)
4. Load session context (hot/warm/cold tiers — see below)
5. Build prompt (ContextRuntime.build_prompt)
6. Stream execute_fn(prompt, context) → yields StreamChunks
7. For each OUTPUT chunk → forward to reply channel
8. On COMPLETE chunk → finalize TaskResult, extract discoveries + memory proposals
9. XADD result to cortex:results stream
10. XACK message on the domain/agent stream
```

Steps 3 and 10 bracket the execution window. If the agent crashes between them,
XAUTOCLAIM returns the message on next startup (step 1 of the next run) and
the `resumed: bool` flag on the `Envelope` lets `execute_fn` adjust its behavior.

---

## Session context: hot / warm / cold

Prompt context is tiered to stay within model token budgets without losing
long-term continuity.

| Tier | What it holds | Token cost |
|------|--------------|------------|
| **Hot** | Last N turns (configurable, default 20) | Full verbatim |
| **Warm** | Summarized transcript from older turns | Compressed |
| **Cold** | Agent memory files (long-term facts, user preferences) | On-demand |

`ContextRuntime.prepare_payload()` fills the hot tier from the session store,
requests a warm summary if the transcript exceeds `warm_summary_threshold`, and
attaches relevant cold memory entries. `build_prompt()` assembles the final
string from these tiers plus the incoming message.

Sessions are scoped by `(channel, domain, thread_id)`. The `SessionStore` protocol
is intentionally abstract — swap in Redis, Postgres, or a flat file store.

---

## Plugin system

Plugins give agents access to external services (calendars, databases, APIs)
through a uniform action interface. They are discovered via Python entry points,
not imports, so they can ship in separate packages without modifying the runtime.

### Registering a plugin

In your plugin package's `pyproject.toml`:

```toml
[project.entry-points."cortex_runtime.plugins"]
my-service = my_package.plugin:MyServicePlugin
```

### Plugin lifecycle

```
discover_and_register()   →  instantiate, collect action metadata (no I/O)
                                    │
ensure_ready(name)        →  call plugin.setup(broker)   ← deferred until first use
                                    │
execute(name, action, params)  →  validate params → plugin.execute_action()
                                    │
shutdown()                →  plugin.teardown() for all loaded plugins
```

The two-phase approach means discovery is fast (no network) and setup failures
don't block the agent from starting.

### The `ServicePlugin` protocol

```python
from typing import Protocol, runtime_checkable
from cortex_runtime.plugins.models import PluginActionInfo, PluginHealthReport, PluginResult

@runtime_checkable
class ServicePlugin(Protocol):
    name: str
    version: str
    description: str

    async def setup(self, broker) -> None: ...
    async def teardown(self) -> None: ...
    def list_actions(self) -> list[PluginActionInfo]: ...
    async def execute_action(self, action: str, params: dict) -> PluginResult: ...
    async def health(self) -> PluginHealthReport: ...
```

`broker` is typed as `Any` — supply your own credential broker. The runtime
never imports one, keeping this package dependency-free.

---

## Redis key namespace

`Keyspace` centralizes all Redis key construction. Two modes:

| Mode | Prefix | When |
|------|--------|------|
| Fleet (global) | `cortex:` | `CORTEX_ORG_ID` absent, `None`, or `"personal"` |
| Org-partitioned | `cortex:{org_id}:` | Any other `CORTEX_ORG_ID` |

```python
from cortex_runtime.redis_keys import Keyspace

ks = Keyspace()                          # fleet
ks.tasks_domain_stream("eng")            # → "cortex:tasks:eng"

ks = Keyspace("acme")                    # org-scoped
ks.tasks_domain_stream("eng")            # → "cortex:acme:tasks:eng"
```

All stream names, result keys, responded keys, and session keys go through
`Keyspace`. This makes multi-tenant hosting possible by changing one config value.

---

## Honest tradeoffs

These are known limitations of the current extraction, not future promises:

- **Consumer name is hardcoded** to `{identity}-1`. Multi-consumer parallelism
  within a single agent process requires a naming scheme — not yet designed.
- **Memory proposals use string-matching** (`[MEMORY: category/name]`) rather
  than a structured protocol. Works in practice; fragile at the edges.
- **Domain file cache** in `ContextRuntime` is never invalidated within a
  process lifetime. Long-running agents see stale domain facts after an update.
- **The provider turn-loop driver** (`providers/_loop_driver.py`) is a TODO
  stub. You must implement `CortexProvider` yourself for now.
