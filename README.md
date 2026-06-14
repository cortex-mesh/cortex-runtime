# cortex-runtime

**Open agent orchestration runtime** — the bus, dispatch wire models, agent turn loop, context runtime, memory system, and plugin protocol that power the CORTEX multi-agent mesh.

> License: [Functional Source License 1.1](LICENSE) (converts to MIT in 4 years)

---

## What is this?

`cortex-runtime` is the open adoption surface of the CORTEX multi-agent mesh — a production multi-agent AI orchestrator used to run a fleet of AI agents (Forge, Titan, Urza, and others) that collaborate on software engineering, research, and business tasks.

This package gives you:

| Module | What it does |
|--------|-------------|
| `bus` / `bus_redis` | `MessageBus` protocol + `RedisStreamBus` implementation (XADD/XREADGROUP/XAUTOCLAIM) |
| `dispatch_models` | Wire models (`TaskPayload`, `TaskResult`, `MemoryProposal`) that cross the Redis bus |
| `consumer` | `TaskConsumer` — subscribes to domain and agent streams, executes tasks, replies through the channel |
| `dispatch` | `TaskDispatcher` — conductor-side routing (domain + @mention + thread affinity) |
| `context_runtime` | Session lookup, transcript writes, and tiered prompt context rendering |
| `memory` | `MemoryStore` protocol + typed memory categories for agent-proposed write-backs |
| `session` | `SessionManager`, `SessionStore` protocol, tiered hot/warm/cold context |
| `plugins` | `ServicePlugin` protocol + `PluginRegistry` for external service integrations |
| `providers` | Tool execution helpers; LLM loop driver deferred (see `providers/_loop_driver.py`) |
| `redis_keys` | Centralized Redis key namespace with org-partitioned `Keyspace` |

## Quickstart

**Option A — Docker Compose (fastest, 2 minutes)**

```bash
git clone https://github.com/cortex-mesh/cortex-runtime
cd cortex-runtime

docker compose up -d                          # Redis + echo agent
python examples/send_task.py "hello world"    # see a response

# With Claude instead of echo:
ANTHROPIC_API_KEY=sk-ant-... docker compose up -d --build
python examples/send_task.py "write me a haiku about Redis Streams"
```

**Option B — GitHub Codespaces (zero local install)**

Click **Code → Codespaces → Create codespace on main**. Redis starts automatically. Then in the terminal:

```bash
python examples/demo_agent.py &
python examples/send_task.py "hello from Codespaces"
```

**Option C — pip + your own Redis**

```bash
pip install cortex-runtime
```

```python
import asyncio
from cortex_runtime.models import BusConfig
from cortex_runtime.bus_redis import RedisStreamBus
from cortex_runtime.consumer import TaskConsumer

async def my_execute(prompt, *, context=None, working_directory=None):
    """Your AI provider implementation goes here."""
    from cortex_runtime.models import StreamChunk, StreamChunkKind
    yield StreamChunk(kind=StreamChunkKind.OUTPUT, data=f"Response to: {prompt}")
    yield StreamChunk(kind=StreamChunkKind.COMPLETE)

async def main():
    config = BusConfig()  # reads REDIS_HOST / REDIS_PORT / REDIS_PASSWORD from env
    bus = RedisStreamBus(config)

    consumer = TaskConsumer(
        identity="myagent",
        domains=["eng", "personal"],
        bus=bus,
        channel=None,  # inject your channel implementation
    )
    await consumer.start(execute_fn=my_execute)

asyncio.run(main())
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `localhost` | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_PASSWORD` | — | Redis AUTH password |
| `REDIS_SSL` | `false` | Enable TLS |
| `CORTEX_ORG_ID` | — | Org partition (fleet = global namespace) |
| `CORTEX_IDENTITY` | `cortex` | Agent identity name |
| `CORTEX_MEMORY_PATH` | `~/.cortex/memory` | Memory base directory |
| `CORTEX_TASK_EXECUTION_TIMEOUT_SECONDS` | `2700` | Task timeout (0 = disable) |

## Architecture

```
Conductor                          Agent(s)
─────────────────────              ─────────────────────
TaskDispatcher                     TaskConsumer
    │                                  │
    │  XADD cortex:tasks:{domain}      │
    ├──────────────────────────────────▶  XREADGROUP (consumer group)
    │                                  │
    │  XADD cortex:results             │  execute_fn(prompt, context)
    ◀──────────────────────────────────┤
    │                                  │
Redis Streams backbone (RedisStreamBus)
```

The `Keyspace` class provides org-partitioned key scoping for hosted deployments.

## Provider Implementation (Deferred)

The LLM turn-loop driver (`providers/_loop_driver.py`) is intentionally
excluded from this release pending the native loop driver design (ADR-120).

Implement the `CortexProvider` protocol directly in your project:

```python
from cortex_runtime.provider import CortexProvider
from cortex_runtime.models import HealthStatus, StreamChunk, StreamChunkKind

class MyProvider:
    def execute(self, prompt, *, context=None, working_directory=None):
        # yield StreamChunk objects
        ...

    async def health(self) -> HealthStatus:
        return HealthStatus(ok=True)
```

## Plugin System

```python
from cortex_runtime.plugins.models import ActionTier, PluginActionInfo, PluginResult
from cortex_runtime.plugins.registry import PluginRegistry

class MyPlugin:
    name = "my-service"
    version = "1.0.0"
    description = "My service integration"

    async def setup(self, broker): ...
    async def teardown(self): ...

    def list_actions(self):
        return [PluginActionInfo(name="do_thing", description="Does a thing", tier=ActionTier.AUTO)]

    async def execute_action(self, action, params):
        return PluginResult(success=True, data={"result": "done"})

    async def health(self):
        from cortex_runtime.plugins.models import PluginHealthReport, PluginHealthStatus
        return PluginHealthReport(plugin=self.name, status=PluginHealthStatus.HEALTHY)

registry = PluginRegistry()
await registry.load_plugin(MyPlugin(), broker=my_broker)
result = await registry.execute("my-service", "do_thing", {})
```

## License

Functional Source License 1.1 (FSL-1.1-MIT). Converts to MIT on the Change Date
(four years from first publication). See [LICENSE](LICENSE) for full terms.

Not for use in competing AI orchestration products without a separate license.
Contact hello@ctxhost.com for licensing inquiries.
