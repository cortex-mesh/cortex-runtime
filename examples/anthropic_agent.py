"""
Production-pattern Anthropic agent.

Shows how to implement CortexProvider with the Anthropic SDK and wire it
into TaskConsumer. This is the starting point for a real agent — copy it
into your project and add a channel implementation.

Requirements:
  pip install cortex-runtime[anthropic]
  export ANTHROPIC_API_KEY=sk-ant-...
  export REDIS_HOST=localhost

Usage:
  python examples/anthropic_agent.py
"""

from __future__ import annotations

import asyncio
import logging
import os

from cortex_runtime.bus_redis import RedisStreamBus
from cortex_runtime.consumer import TaskConsumer
from cortex_runtime.models import BusConfig, HealthStatus, StreamChunk, StreamChunkKind
from cortex_runtime.provider import CortexProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-20s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("anthropic_agent")


# ── Provider ──────────────────────────────────────────────────────────────────


class AnthropicProvider(CortexProvider):
    """CortexProvider implementation using the Anthropic SDK.

    Drop-in replacement for any AsyncIterator[StreamChunk] execute function.
    Copy this into your project and add your system prompt, tool definitions,
    memory injection, etc.
    """

    DEFAULT_MODEL = "claude-sonnet-4-6"
    DEFAULT_MAX_TOKENS = 8192

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        system_prompt: str | None = None,
    ) -> None:
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._system = system_prompt or (
            "You are a helpful AI agent in a multi-agent mesh. "
            "Be concise and practical in your responses."
        )

    async def execute(
        self,
        prompt: str,
        *,
        context: dict | None = None,
        working_directory: str | None = None,
    ):
        """Stream a Claude response for the given prompt.

        Yields OUTPUT chunks as text arrives, then a COMPLETE chunk.
        On API error yields an ERROR chunk so the consumer can surface it.
        """
        messages = []

        # Inject prior context turns if available (hot tier from ContextRuntime)
        if context and context.get("history"):
            messages.extend(context["history"])

        messages.append({"role": "user", "content": prompt})

        try:
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=self._max_tokens,
                system=self._system,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield StreamChunk(kind=StreamChunkKind.OUTPUT, data=text)
            yield StreamChunk(kind=StreamChunkKind.COMPLETE)

        except Exception as exc:
            log.exception("Anthropic API error: %s", exc)
            yield StreamChunk(kind=StreamChunkKind.ERROR, data=str(exc))

    async def health(self) -> HealthStatus:
        """Check connectivity by listing available models."""
        try:
            await self._client.models.list()
            return HealthStatus(ok=True)
        except Exception as exc:
            return HealthStatus(ok=False, error=str(exc))


# ── Entry point ───────────────────────────────────────────────────────────────


async def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY is required")

    config = BusConfig(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        password=os.environ.get("REDIS_PASSWORD") or None,
    )

    provider = AnthropicProvider(
        api_key=api_key,
        model=os.environ.get("ANTHROPIC_MODEL", AnthropicProvider.DEFAULT_MODEL),
    )

    # Verify connectivity before starting the consumer loop
    health = await provider.health()
    if not health.ok:
        raise SystemExit(f"Anthropic health check failed: {health.error}")
    log.info("Anthropic health OK — model=%s", provider._model)

    identity = os.environ.get("CORTEX_IDENTITY", "anthropic-agent")
    domains = os.environ.get("CORTEX_DOMAINS", "eng").split(",")

    bus = RedisStreamBus(config)

    consumer = TaskConsumer(
        identity=identity,
        domains=domains,
        bus=bus,
        channel=None,  # Replace with your channel implementation
    )

    log.info("Agent starting — identity=%s domains=%s", identity, domains)
    await consumer.start(execute_fn=provider.execute)


if __name__ == "__main__":
    asyncio.run(main())
