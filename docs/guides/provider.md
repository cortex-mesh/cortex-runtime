# Writing a Provider

A **provider** is the function or object that executes an AI turn — it receives
a prompt and streams back `StreamChunk` objects. The runtime is provider-agnostic:
anything that yields `StreamChunk` values works.

## Minimal function-based provider

```python
from cortex_runtime.models import StreamChunk, StreamChunkKind
from typing import AsyncIterator


async def my_provider(
    prompt: str,
    *,
    context: dict | None = None,
    working_directory: str | None = None,
) -> AsyncIterator[StreamChunk]:
    # Call your LLM here
    response_text = await call_my_llm(prompt, context=context)

    yield StreamChunk(kind=StreamChunkKind.OUTPUT, data=response_text)
    yield StreamChunk(kind=StreamChunkKind.COMPLETE)
```

Pass it to `TaskConsumer.start()`:

```python
await consumer.start(execute_fn=my_provider)
```

## StreamChunk kinds

| Kind | When to yield |
|------|--------------|
| `OUTPUT` | Each text chunk from the model |
| `TOOL_CALL` | When the model requests a tool; put the serialized call in `data` |
| `TOOL_RESULT` | After executing a tool; put the result in `data` |
| `COMPLETE` | Final chunk — signals end of the turn |
| `ERROR` | Unrecoverable error; put the error message in `data` |

## Implementing `CortexProvider` (optional)

If you want health checks and structured lifecycle, implement the protocol:

```python
from cortex_runtime.provider import CortexProvider
from cortex_runtime.models import HealthStatus, StreamChunk, StreamChunkKind


class MyProvider:
    """Wraps the Anthropic SDK."""

    def __init__(self, api_key: str):
        import anthropic
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def execute(
        self,
        prompt: str,
        *,
        context: dict | None = None,
        working_directory: str | None = None,
    ):
        async with self._client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield StreamChunk(kind=StreamChunkKind.OUTPUT, data=text)
        yield StreamChunk(kind=StreamChunkKind.COMPLETE)

    async def health(self) -> HealthStatus:
        try:
            await self._client.models.list()
            return HealthStatus(ok=True)
        except Exception as e:
            return HealthStatus(ok=False, error=str(e))
```

## Tool use

The runtime does not execute tools itself — it surfaces `TOOL_CALL` chunks for
the consumer to act on. Use `execute_tool_calls()` from `cortex_runtime.providers`
to dispatch to a `PluginRegistry`:

```python
from cortex_runtime.providers import execute_tool_calls, ToolCall, ToolResult

# In your provider's execute loop:
tool_calls = [ToolCall(id=..., name="my-service__do_thing", input={...})]
results: list[ToolResult] = await execute_tool_calls(tool_calls, registry=plugin_registry)
```

Tool names use the `{plugin_name}__{action_name}` format (`TOOL_NAME_SEP = "__"`).
