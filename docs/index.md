# cortex-runtime

**Open agent orchestration runtime** — the bus, dispatch wire models, agent turn loop, context runtime, memory system, and plugin protocol that power the CORTEX multi-agent mesh.

> **License:** [Functional Source License 1.1](https://fsl.software/) (converts to MIT in 4 years)  
> **Install:** `pip install cortex-runtime`  
> **Source:** [github.com/cortex-mesh/cortex-runtime](https://github.com/cortex-mesh/cortex-runtime)

---

## What is this?

`cortex-runtime` is the open adoption surface of a production multi-agent AI orchestrator. It runs a fleet of AI agents (Forge, Titan, Urza, and others) that collaborate on software engineering, research, and business tasks around the clock.

This package gives you the runtime primitives without the closed-source hosted layer:

| Module | What it does |
|--------|-------------|
| `bus` / `bus_redis` | `MessageBus` protocol + `RedisStreamBus` (XADD/XREADGROUP/XAUTOCLAIM) |
| `dispatch_models` | Wire types crossing the bus: `TaskPayload`, `TaskResult`, `MemoryProposal` |
| `consumer` | `TaskConsumer` — blocking XREADGROUP loop, executes tasks, replies via channel |
| `dispatch` | `TaskDispatcher` — conductor-side routing (domain + @mention + thread affinity) |
| `context_runtime` | Session lookup, transcript writes, tiered prompt context rendering |
| `memory` | `MemoryStore` protocol + typed memory categories for agent write-backs |
| `session` | `SessionManager`, `SessionStore` protocol, hot/warm/cold context tiers |
| `plugins` | `ServicePlugin` protocol + `PluginRegistry` for external service integrations |
| `redis_keys` | Centralized Redis key namespace with org-partitioned `Keyspace` |

## Quickstart

**Requirements:** Python 3.12+, Redis 7+

```bash
pip install cortex-runtime
```

Set environment variables:

```bash
export REDIS_HOST=localhost
export REDIS_PASSWORD=your-redis-password   # omit if no auth
export CORTEX_IDENTITY=myagent
```

Run the minimal echo agent from the examples:

```bash
python examples/echo_agent.py
```

Or wire it yourself:

```python
import asyncio
from cortex_runtime.bus_redis import RedisStreamBus
from cortex_runtime.consumer import TaskConsumer
from cortex_runtime.models import BusConfig, StreamChunk, StreamChunkKind


async def my_execute(prompt, *, context=None, working_directory=None):
    """Replace with your LLM provider."""
    yield StreamChunk(kind=StreamChunkKind.OUTPUT, data=f"Response: {prompt}")
    yield StreamChunk(kind=StreamChunkKind.COMPLETE)


async def main():
    config = BusConfig()  # reads REDIS_HOST / REDIS_PORT / REDIS_PASSWORD from env
    bus = RedisStreamBus(config)
    consumer = TaskConsumer(
        identity="myagent",
        domains=["eng"],
        bus=bus,
        channel=None,
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
| `CORTEX_ORG_ID` | — | Org partition (absent = fleet/global namespace) |
| `CORTEX_IDENTITY` | `cortex` | Agent identity name |
| `CORTEX_MEMORY_PATH` | `~/.cortex/memory` | Memory base directory |
| `CORTEX_TASK_EXECUTION_TIMEOUT_SECONDS` | `2700` | Task timeout in seconds (0 = disable) |

## What's Deferred

The LLM turn-loop driver (`providers/_loop_driver.py`) is intentionally excluded
pending the native loop driver design. Implement `CortexProvider` directly — see the
[Provider Guide](guides/provider.md).
