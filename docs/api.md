# API Reference

Public names exported from `cortex_runtime`. All are stable within a minor version.

---

## Bus

### `MessageBus` (protocol)

```python
from cortex_runtime.bus import MessageBus
```

Structural protocol that `RedisStreamBus` satisfies. Implement it to swap
in a different transport (e.g. an in-memory bus for testing).

| Method | Signature | Description |
|--------|-----------|-------------|
| `publish` | `async (stream, payload, *, msg_type, maxlen) → str` | XADD to a stream. Returns the message ID. |
| `read_group` | `async (streams, group, consumer, count, block_ms) → list[Envelope]` | XREADGROUP. Blocks for up to `block_ms`. |
| `ack` | `async (stream, group, msg_id) → None` | XACK. |
| `create_group` | `async (stream, group, mkstream) → None` | XGROUP CREATE. |
| `health` | `async () → HealthStatus` | Ping the broker. |
| `close` | `async () → None` | Tear down connections. |
| `subscribe` | `async (*streams) → AsyncIterator[Envelope]` | High-level streaming iterator. |

### `RedisStreamBus`

```python
from cortex_runtime.bus_redis import RedisStreamBus
from cortex_runtime.models import BusConfig

bus = RedisStreamBus(BusConfig())
```

Production Redis implementation. Handles connection pooling, XAUTOCLAIM own-PEL
redelivery, and the `asyncio.wait_for()` watchdog for stale sockets.

### `BusConfig`

```python
from cortex_runtime.models import BusConfig
```

Pydantic model. All fields have env-var defaults:

| Field | Env var | Default |
|-------|---------|---------|
| `host` | `REDIS_HOST` | `"localhost"` |
| `port` | `REDIS_PORT` | `6379` |
| `password` | `REDIS_PASSWORD` | `None` |
| `stream_prefix` | `CORTEX_ORG_ID` (via Keyspace) | `"cortex"` |
| `consumer_group` | — | `"cortex-agents"` |
| `block_ms` | — | `5000` |
| `claim_idle_ms` | — | `30000` |
| `read_watchdog_ms` | — | `60000` |
| `max_retries` | — | `3` |

---

## Consumer

### `TaskConsumer`

```python
from cortex_runtime.consumer import TaskConsumer
```

Agent-side turn loop. Subscribes to domain and agent-specific streams.

```python
consumer = TaskConsumer(
    identity="myagent",
    domains=["eng", "personal"],
    bus=bus,
    channel=channel,  # your ChannelProvider implementation
)
await consumer.start(execute_fn=my_provider_fn)
```

`execute_fn` signature:

```python
async def execute_fn(
    prompt: str,
    *,
    context: dict | None = None,
    working_directory: str | None = None,
) -> AsyncIterator[StreamChunk]:
    ...
```

### `extract_discoveries(text: str) → list[str]`

Extracts `[DISCOVERY] <text>` lines from agent output.

### `extract_memory_proposals(text: str) → list[MemoryProposal]`

Extracts `[MEMORY: category/name]\n<content>` blocks from agent output.

---

## Dispatch

### `TaskDispatcher`

```python
from cortex_runtime.dispatch import TaskDispatcher
```

Conductor-side router. Routes messages to domain streams or agent-specific
streams based on @mention, thread affinity, and domain.

---

## Models

### `Department` / `Domain`

```python
from cortex_runtime.models import Department, Domain

domain = Domain.parse("eng")        # raises ValueError on unknown department
domain = Domain(Department.ENG)
```

Valid departments: `personal`, `business`, `eng`, `ops`, `cortex`, `finance`,
`research`, `thoughts`, `maker`, `creative`, `synapse`, `general`.

### `TaskPriority`

```python
from cortex_runtime.models import TaskPriority
# LOW | NORMAL | HIGH | URGENT
```

### `StreamChunk` / `StreamChunkKind`

```python
from cortex_runtime.models import StreamChunk, StreamChunkKind

StreamChunk(kind=StreamChunkKind.OUTPUT, data="Hello")
StreamChunk(kind=StreamChunkKind.COMPLETE)
StreamChunk(kind=StreamChunkKind.ERROR, data="timeout")
StreamChunk(kind=StreamChunkKind.TOOL_CALL, data="...", metadata={"id": "tc_1"})
StreamChunk(kind=StreamChunkKind.TOOL_RESULT, data="...", metadata={"tool_call_id": "tc_1"})
```

### `HealthStatus`

```python
from cortex_runtime.models import HealthStatus
# Fields: ok: bool, latency_ms: float | None, error: str | None, details: dict
```

### `Envelope`

```python
from cortex_runtime.models import Envelope
# Fields: msg_id: str, payload: bytes, msg_type: str, resumed: bool
```

---

## Dispatch models

```python
from cortex_runtime.dispatch_models import (
    TaskPayload, TaskResult, MemoryProposal, DispatchResult,
    DOMAIN_STREAM_PREFIX,   # "tasks"
    AGENT_STREAM_PREFIX,    # "tasks:agent"
)
```

### `TaskPayload`

Wire model for a task arriving on a domain stream.

| Field | Type | Description |
|-------|------|-------------|
| `message_id` | `str` | Unique message ID |
| `text` | `str` | The prompt/task text |
| `sender` | `str` | Sender display name |
| `sender_id` | `str` | Sender opaque ID |
| `channel_id` | `str \| None` | Reply channel |
| `thread_id` | `str \| None` | Thread for context lookup |
| `domain` | `str` | Target domain |
| `priority` | `TaskPriority` | Task priority |
| `attachments` | `list` | File/media attachments |
| `metadata` | `dict` | Extension metadata |

---

## Memory

```python
from cortex_runtime.memory import MemoryStore, MemoryFile, TypedMemoryCategory, is_safe_typed_name
```

### `MemoryStore` (protocol)

| Method | Description |
|--------|-------------|
| `read(category, name) → MemoryFile` | Read a named memory entry |
| `write(category, name, content, mode) → MemoryFile` | Write (overwrite/append/prepend) |
| `list(category) → list[MemoryFile]` | List entries in a category |
| `delete(category, name) → None` | Delete an entry |
| `exists(category, name) → bool` | Check existence |

### `TypedMemoryCategory`

Named categories: `people`, `projects`, `context`, `facts`, `skills`, `preferences`.

### `is_safe_typed_name(name: str) → bool`

Validates a memory entry name: lowercase alphanumeric, internal hyphens only,
no leading/trailing hyphens, non-empty.

---

## Session

```python
from cortex_runtime.session import SessionManager, SessionStore, SessionConfig, Session
from cortex_runtime import SessionState
```

### `SessionState`

Lifecycle states: `ACTIVE`, `IDLE`, `PAUSED`, `CLOSED`.

### `SessionConfig`

| Field | Default | Description |
|-------|---------|-------------|
| `memory_base_path` | `~/.cortex/memory` | Memory directory root |
| `hot_window_size` | `20` | Turns kept verbatim |
| `warm_summary_threshold` | `50` | Turns before warm summarization |

---

## Plugins

```python
from cortex_runtime.plugins import ServicePlugin, PluginRegistry, ActionTier
from cortex_runtime.plugins.models import PluginActionInfo, PluginResult, PluginHealthReport
```

See the [Plugin Guide](guides/plugin.md) for a complete walkthrough.

---

## Keyspace

```python
from cortex_runtime.redis_keys import Keyspace, FLEET_ORG_ID

ks = Keyspace()                            # fleet (FLEET_ORG_ID = "personal")
ks = Keyspace("acme")                      # org-scoped

ks.tasks_domain_stream("eng")              # stream name
ks.agent_stream("forge")                   # per-agent stream
ks.responded_key("msg-id")                 # idempotency key
ks.stream_prefix                           # e.g. "cortex" or "cortex:acme"
```

---

## Exceptions

```python
from cortex_runtime import (
    CortexRuntimeError,       # base
    BusError,                 # base for bus errors
    BusConnectionError,
    BusSerializationError,
    CortexProviderError,
    ProviderConnectionError,
    ProviderExecutionError,
    ProviderTimeoutError,
    CortexMemoryError,        # base for memory errors
    MemoryFileNotFoundError,
    MemoryReadError,
    MemoryWriteError,
)
```
