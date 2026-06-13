"""cortex_runtime — open agent orchestration runtime.

The adoption surface of the CORTEX multi-agent mesh:
bus + Redis, dispatch wire models, agent turn loop (consumer/dispatch),
context runtime + memory, provider protocol, and plugin system.

Provider implementations (LLM turn-loop drivers) are released separately.
"""

from cortex_runtime.bus import MessageBus
from cortex_runtime.bus_redis import RedisStreamBus
from cortex_runtime.consumer import TaskConsumer, extract_discoveries, extract_memory_proposals
from cortex_runtime.context_runtime import ContextPrompt, ContextRuntime
from cortex_runtime.dispatch import TaskDispatcher
from cortex_runtime.dispatch_models import (
    AGENT_STREAM_PREFIX,
    DOMAIN_STREAM_PREFIX,
    DispatchResult,
    MemoryProposal,
    TaskPayload,
    TaskResult,
)
from cortex_runtime.exceptions import (
    BusConnectionError,
    BusError,
    BusSerializationError,
    CortexMemoryError,
    CortexProviderError,
    CortexRuntimeError,
    MemoryFileNotFoundError,
    MemoryReadError,
    MemoryWriteError,
    ProviderConnectionError,
    ProviderExecutionError,
    ProviderTimeoutError,
)
from cortex_runtime.memory import MemoryFile, MemoryStore, MemoryWriteMode, TypedMemoryCategory
from cortex_runtime.models import (
    BusConfig,
    Department,
    Domain,
    Envelope,
    HealthStatus,
    SessionState,
    StreamChunk,
    StreamChunkKind,
    TaskPriority,
)
from cortex_runtime.provider import CortexProvider
from cortex_runtime.redis_keys import Keyspace

__version__ = "0.1.0"

__all__ = [
    "AGENT_STREAM_PREFIX",
    "BusConfig",
    "BusConnectionError",
    "BusError",
    "BusSerializationError",
    "CortexMemoryError",
    "CortexProvider",
    "CortexProviderError",
    "CortexRuntimeError",
    "ContextPrompt",
    "ContextRuntime",
    "Department",
    "DispatchResult",
    "DOMAIN_STREAM_PREFIX",
    "Domain",
    "Envelope",
    "HealthStatus",
    "Keyspace",
    "MemoryFile",
    "MemoryFileNotFoundError",
    "MemoryProposal",
    "MemoryReadError",
    "MemoryStore",
    "MemoryWriteError",
    "MemoryWriteMode",
    "MessageBus",
    "ProviderConnectionError",
    "ProviderExecutionError",
    "ProviderTimeoutError",
    "RedisStreamBus",
    "SessionState",
    "StreamChunk",
    "StreamChunkKind",
    "TaskConsumer",
    "TaskDispatcher",
    "TaskPayload",
    "TaskPriority",
    "TaskResult",
    "TypedMemoryCategory",
    "extract_discoveries",
    "extract_memory_proposals",
]
