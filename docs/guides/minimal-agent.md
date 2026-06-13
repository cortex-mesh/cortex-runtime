# Minimal Agent

This guide walks through the `examples/echo_agent.py` example — the smallest
possible cortex-runtime agent that can receive and respond to tasks.

## Prerequisites

- Python 3.12+
- Redis running locally (or via Docker: `docker run -p 6379:6379 redis:7-alpine`)
- `pip install cortex-runtime`

## The code

```python title="examples/echo_agent.py"
--8<-- "examples/echo_agent.py"
```

## What it does

1. `BusConfig()` reads `REDIS_HOST`, `REDIS_PORT`, and `REDIS_PASSWORD` from
   the environment. Defaults to `localhost:6379` with no auth.
2. `RedisStreamBus(config)` creates the Redis connection pool.
3. `TaskConsumer` subscribes to the `eng` domain stream
   (`cortex:tasks:eng` in the default namespace).
4. `echo_execute` is the provider: it yields one `OUTPUT` chunk and then a
   `COMPLETE` chunk.
5. `consumer.start()` blocks until interrupted.

## Sending a test task

With the agent running, open another terminal and push a task directly:

```bash
redis-cli XADD cortex:tasks:eng '*' \
  msg_type task \
  payload '{"message_id":"test-1","text":"hello world","sender":"test","sender_id":"u1","domain":"eng"}'
```

The agent will log the task and echo a response.

## Next steps

- Replace `echo_execute` with a real LLM call — see the [Provider Guide](provider.md).
- Add external service integrations — see the [Plugin Guide](plugin.md).
- Use `domains=["eng", "personal"]` to subscribe to multiple streams.
- Set `CORTEX_ORG_ID=myorg` to partition all keys under `cortex:myorg:*`.
