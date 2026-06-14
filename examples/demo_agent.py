"""
Demo agent — works with send_task.py for a local round-trip.

Modes:
  echo (default)      No API key required. Echoes the prompt back.
  Claude (auto)       Set ANTHROPIC_API_KEY and the agent uses claude-haiku-4-5.

Usage with Docker Compose:
  docker compose up -d
  python examples/send_task.py "what is the capital of France?"

Usage standalone (Redis already running):
  REDIS_HOST=localhost python examples/demo_agent.py
  REDIS_HOST=localhost ANTHROPIC_API_KEY=sk-ant-... python examples/demo_agent.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import redis.asyncio as aioredis

from cortex_runtime.bus_redis import RedisStreamBus
from cortex_runtime.consumer import TaskConsumer
from cortex_runtime.models import BusConfig, StreamChunk, StreamChunkKind

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-20s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("demo_agent")

DOMAIN = os.environ.get("CORTEX_DOMAIN", "eng")
IDENTITY = os.environ.get("CORTEX_IDENTITY", "demo-agent")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


# ── Provider ─────────────────────────────────────────────────────────────────


async def echo_provider(prompt: str, *, context=None, working_directory=None):
    """Trivial echo — no API key required."""
    yield StreamChunk(kind=StreamChunkKind.OUTPUT, data=f"[echo] {prompt}")
    yield StreamChunk(kind=StreamChunkKind.COMPLETE)


async def anthropic_provider(prompt: str, *, context=None, working_directory=None):
    """Claude haiku via the Anthropic SDK."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    async with client.messages.stream(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        async for text in stream.text_stream:
            yield StreamChunk(kind=StreamChunkKind.OUTPUT, data=text)
    yield StreamChunk(kind=StreamChunkKind.COMPLETE)


# ── Demo channel ──────────────────────────────────────────────────────────────


class DemoChannel:
    """Minimal reply channel for the demo.

    Writes replies to a Redis list keyed by ``demo:reply:{message_id}``
    so that send_task.py can BLPOP the response.

    The consumer calls ``channel.send(room_id, text, thread_id=...)``.
    ``room_id`` here carries the reply key written by send_task.py.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def send(self, room_id: str | None, text: str, *, thread_id: str | None = None) -> None:
        if not room_id:
            return
        await self._redis.rpush(room_id, json.dumps({"text": text}))
        await self._redis.expire(room_id, 120)


# ── Entry point ───────────────────────────────────────────────────────────────


async def main() -> None:
    config = BusConfig(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        password=os.environ.get("REDIS_PASSWORD") or None,
    )

    # Separate raw Redis client for reply writes (bus uses its own pool)
    reply_redis = aioredis.Redis(
        host=config.host,
        port=config.port,
        password=config.password,
        decode_responses=True,
    )

    channel = DemoChannel(reply_redis)

    if ANTHROPIC_API_KEY:
        log.info("Provider: Anthropic Claude (claude-haiku-4-5-20251001)")
        execute_fn = anthropic_provider
    else:
        log.info("Provider: echo  (set ANTHROPIC_API_KEY to use Claude)")
        execute_fn = echo_provider

    bus = RedisStreamBus(config)

    consumer = TaskConsumer(
        identity=IDENTITY,
        domains=[DOMAIN],
        bus=bus,
        channel=channel,
    )

    log.info("Demo agent starting — domain=%s identity=%s", DOMAIN, IDENTITY)
    log.info("Send a task:  python examples/send_task.py 'hello'")

    try:
        await consumer.start(execute_fn=execute_fn)
    finally:
        await reply_redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
