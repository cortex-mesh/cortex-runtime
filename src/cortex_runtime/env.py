"""Environment configuration for cortex_runtime.

Reads Redis connection details from environment variables.
No vault or cloud-provider resolver — credentials are passed in via
environment variables (or injected by the caller via ``BusConfig``).

Required environment variables
-------------------------------
REDIS_HOST       Hostname of the Redis server (default: localhost)
REDIS_PORT       Port of the Redis server (default: 6379)
REDIS_PASSWORD   Optional password for Redis AUTH

Optional
--------
REDIS_SSL        Set to "true" to enable TLS (default: false)
CORTEX_ORG_ID    Org partition for Keyspace (default: fleet/global namespace)
CORTEX_IDENTITY  Agent identity name (default: cortex)
"""

from __future__ import annotations

import os
import socket

# ── TCP keepalive options for redis-py ───────────────────────────────────
# redis-py passes these to the underlying socket when ``socket_keepalive=True``.
# Values match Linux defaults; tune via env override if needed.

REDIS_KEEPALIVE_OPTIONS: dict[int, int] = {}

if hasattr(socket, "TCP_KEEPIDLE"):
    REDIS_KEEPALIVE_OPTIONS[socket.TCP_KEEPIDLE] = 30
if hasattr(socket, "TCP_KEEPINTVL"):
    REDIS_KEEPALIVE_OPTIONS[socket.TCP_KEEPINTVL] = 10
if hasattr(socket, "TCP_KEEPCNT"):
    REDIS_KEEPALIVE_OPTIONS[socket.TCP_KEEPCNT] = 3


def get_redis_config() -> dict[str, object]:
    """Build a redis-py client kwargs dict from environment variables.

    Returns a dict suitable for passing to ``redis.asyncio.Redis(**config)``
    or storing in ``BusConfig``.

    Example::

        import redis.asyncio as aioredis
        from cortex_runtime.env import get_redis_config

        client = aioredis.Redis(**get_redis_config())
    """
    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    password = os.environ.get("REDIS_PASSWORD") or None
    ssl = os.environ.get("REDIS_SSL", "").lower() in ("1", "true", "yes")

    config: dict[str, object] = {
        "host": host,
        "port": port,
        "decode_responses": False,
        "socket_keepalive": True,
        "socket_keepalive_options": REDIS_KEEPALIVE_OPTIONS,
    }
    if password:
        config["password"] = password
    if ssl:
        config["ssl"] = True

    return config
