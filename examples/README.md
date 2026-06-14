# Examples

## Quick demo (Docker Compose)

The fastest way to see cortex-runtime in action:

```bash
# Start Redis + demo agent (echo mode, no API key needed)
docker compose up -d

# Send a task and see the response  (~2 seconds)
python examples/send_task.py "explain Redis Streams in one sentence"

# With Claude instead of echo (set your key first)
ANTHROPIC_API_KEY=sk-ant-... docker compose up -d --build
python examples/send_task.py "write me a haiku about distributed systems"

# Tear down
docker compose down
```

## Files

| File | What it shows |
|------|--------------|
| [`echo_agent.py`](echo_agent.py) | Minimal `TaskConsumer` usage. Echo provider, no API key. |
| [`demo_agent.py`](demo_agent.py) | Echo **or** Claude (auto-detected via `ANTHROPIC_API_KEY`). Includes `DemoChannel` for round-trip replies with `send_task.py`. |
| [`send_task.py`](send_task.py) | CLI: inject a task into a domain stream, block until the agent replies. |
| [`anthropic_agent.py`](anthropic_agent.py) | Production-pattern Anthropic agent — `AnthropicProvider` implementing `CortexProvider`. Copy and extend this for a real agent. |

## GitHub Codespaces

Open this repo in Codespaces for a zero-install environment with Redis pre-configured:

1. Click **Code → Codespaces → Create codespace on main**
2. Wait for the container to build (happens automatically)
3. In the terminal:
   ```bash
   # Terminal 1 — start the agent
   python examples/demo_agent.py

   # Terminal 2 — send a task
   python examples/send_task.py "hello from Codespaces"
   ```

## Next steps

- Replace `echo_provider` in `demo_agent.py` with your LLM — see [`anthropic_agent.py`](anthropic_agent.py)
- Implement a real `channel` (Synapse, Slack, email) and pass it to `TaskConsumer`
- Add plugins — see the [Plugin Guide](https://cortex-mesh.github.io/cortex-runtime/guides/plugin/)
