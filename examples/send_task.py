"""
Send a task to the demo agent and print the streamed response.

Requires:
  pip install cortex-runtime
  Redis + demo_agent.py running (or: docker compose up -d)

Usage:
  python examples/send_task.py "what is the capital of France?"
  python examples/send_task.py "write me a haiku about Redis Streams" --domain eng
  REDIS_HOST=myhost python examples/send_task.py "hello"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid

import redis.asyncio as aioredis

from cortex_runtime.dispatch_models import DOMAIN_STREAM_PREFIX, TaskPayload
from cortex_runtime.models import BusConfig, TaskPriority
from cortex_runtime.redis_keys import Keyspace

TIMEOUT_SECONDS = 30


async def send_and_receive(text: str, domain: str) -> int:
    config = BusConfig(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        password=os.environ.get("REDIS_PASSWORD") or None,
    )

    ks = Keyspace(os.environ.get("CORTEX_ORG_ID"))
    message_id = str(uuid.uuid4())

    # room_id is the reply key — DemoChannel writes the response here
    reply_key = f"demo:reply:{message_id}"

    payload = TaskPayload(
        message_id=message_id,
        text=text,
        sender="send_task",
        sender_id="cli",
        domain=domain,
        priority=TaskPriority.NORMAL,
        room_id=reply_key,
    )

    stream_name = f"{ks.stream_prefix}:{DOMAIN_STREAM_PREFIX}:{domain}"

    r = aioredis.Redis(
        host=config.host,
        port=config.port,
        password=config.password,
        decode_responses=True,
    )

    try:
        await r.xadd(
            stream_name,
            {"msg_type": "task", "payload": payload.model_dump_json()},
        )
        print(f"→ task sent  (id={message_id[:8]}…, stream={stream_name})")
        print(f"  waiting up to {TIMEOUT_SECONDS}s for response…\n")

        result = await r.blpop(reply_key, timeout=TIMEOUT_SECONDS)
        if result is None:
            print("✗ timed out — is the agent running?  docker compose up -d", file=sys.stderr)
            return 1

        data = json.loads(result[1])
        print(data.get("text", data))
        return 0

    finally:
        await r.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a task to the demo agent")
    parser.add_argument("text", help="Task text / prompt")
    parser.add_argument(
        "--domain",
        default=os.environ.get("CORTEX_DOMAIN", "eng"),
        help="Domain stream to target (default: eng)",
    )
    args = parser.parse_args()

    sys.exit(asyncio.run(send_and_receive(args.text, args.domain)))


if __name__ == "__main__":
    main()
