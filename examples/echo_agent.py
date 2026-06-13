"""
Minimal cortex-runtime agent: receives tasks on the 'eng' domain and echoes them back.

Requirements:
    pip install cortex-runtime

Usage:
    REDIS_HOST=localhost python examples/echo_agent.py

To send a test task (from another terminal):
    redis-cli XADD cortex:tasks:eng '*' \\
        msg_type task \\
        payload '{"message_id":"t1","text":"hello","sender":"test","sender_id":"u1","domain":"eng"}'
"""

import asyncio
import logging
import os

from cortex_runtime.bus_redis import RedisStreamBus
from cortex_runtime.consumer import TaskConsumer
from cortex_runtime.models import BusConfig, StreamChunk, StreamChunkKind

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


async def echo_execute(prompt: str, *, context=None, working_directory=None):
    """Trivial provider that echoes the prompt. Replace with your LLM call."""
    yield StreamChunk(kind=StreamChunkKind.OUTPUT, data=f"Echo: {prompt}")
    yield StreamChunk(kind=StreamChunkKind.COMPLETE)


async def main() -> None:
    config = BusConfig(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        password=os.environ.get("REDIS_PASSWORD") or None,
    )

    bus = RedisStreamBus(config)

    consumer = TaskConsumer(
        identity="example-agent",
        domains=["eng"],
        bus=bus,
        channel=None,
    )

    logging.getLogger(__name__).info(
        "Echo agent starting — listening on domain 'eng'. Ctrl-C to stop."
    )
    await consumer.start(execute_fn=echo_execute)


if __name__ == "__main__":
    asyncio.run(main())
