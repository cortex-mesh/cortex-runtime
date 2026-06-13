"""Import smoke tests for cortex_runtime.

Verifies that the package and all public sub-modules can be imported
without error. No Redis or provider credentials needed.
"""

import importlib


def test_package_imports():
    """Top-level package imports without error."""
    import cortex_runtime

    assert cortex_runtime.__version__ == "0.1.1"


def test_exceptions_import():
    m = importlib.import_module("cortex_runtime.exceptions")
    assert hasattr(m, "CortexRuntimeError")
    assert hasattr(m, "BusConnectionError")
    assert hasattr(m, "ProviderConnectionError")
    assert hasattr(m, "CortexMemoryError")


def test_models_import():
    m = importlib.import_module("cortex_runtime.models")
    assert hasattr(m, "Department")
    assert hasattr(m, "Domain")
    assert hasattr(m, "BusConfig")
    assert hasattr(m, "Envelope")
    assert hasattr(m, "StreamChunk")
    assert hasattr(m, "HealthStatus")


def test_redis_keys_import():
    m = importlib.import_module("cortex_runtime.redis_keys")
    assert hasattr(m, "Keyspace")
    assert hasattr(m, "FLEET_ORG_ID")
    assert m.PREFIX == "cortex"


def test_keyspace_fleet():
    from cortex_runtime.redis_keys import Keyspace

    ks = Keyspace()
    assert ks.is_fleet
    assert ks.responded_key("m1") == "cortex:responded:m1"
    assert ks.tasks_domain_stream("eng") == "cortex:tasks:eng"


def test_keyspace_org():
    from cortex_runtime.redis_keys import Keyspace

    ks = Keyspace("demo")
    assert not ks.is_fleet
    assert ks.responded_key("m1") == "cortex:demo:responded:m1"
    assert ks.tasks_domain_stream("eng") == "cortex:demo:tasks:eng"


def test_keyspace_personal_is_fleet():
    from cortex_runtime.redis_keys import Keyspace

    ks = Keyspace("personal")
    assert ks.is_fleet
    assert ks.responded_key("m1") == "cortex:responded:m1"


def test_keyspace_case_insensitive():
    from cortex_runtime.redis_keys import Keyspace

    # 'Personal' and 'PERSONAL' must map to the fleet namespace, not a scoped org
    assert Keyspace("Personal").is_fleet
    assert Keyspace("PERSONAL").is_fleet
    assert Keyspace("  Personal  ").is_fleet


def test_env_import():
    m = importlib.import_module("cortex_runtime.env")
    assert hasattr(m, "REDIS_KEEPALIVE_OPTIONS")
    assert hasattr(m, "get_redis_config")


def test_env_get_redis_config_defaults(monkeypatch):
    monkeypatch.delenv("REDIS_HOST", raising=False)
    monkeypatch.delenv("REDIS_PORT", raising=False)
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)

    from cortex_runtime.env import get_redis_config

    config = get_redis_config()
    assert config["host"] == "localhost"
    assert config["port"] == 6379
    assert "password" not in config


def test_bus_import():
    m = importlib.import_module("cortex_runtime.bus")
    assert hasattr(m, "MessageBus")


def test_bus_redis_import():
    m = importlib.import_module("cortex_runtime.bus_redis")
    assert hasattr(m, "RedisStreamBus")


def test_provider_import():
    m = importlib.import_module("cortex_runtime.provider")
    assert hasattr(m, "CortexProvider")


def test_dispatch_models_import():
    m = importlib.import_module("cortex_runtime.dispatch_models")
    assert hasattr(m, "TaskPayload")
    assert hasattr(m, "TaskResult")
    assert hasattr(m, "MemoryProposal")
    assert hasattr(m, "DispatchResult")
    assert m.DOMAIN_STREAM_PREFIX == "tasks"
    assert m.AGENT_STREAM_PREFIX == "tasks:agent"


def test_dispatch_models_task_payload_roundtrip():
    from cortex_runtime.dispatch_models import TaskPayload

    payload = TaskPayload(message_id="msg1", text="hello", sender="alice", sender_id="U123")
    json_bytes = payload.model_dump_json().encode()
    restored = TaskPayload.model_validate_json(json_bytes)
    assert restored.message_id == "msg1"
    assert restored.text == "hello"


def test_memory_import():
    m = importlib.import_module("cortex_runtime.memory")
    assert hasattr(m, "MemoryFile")
    assert hasattr(m, "MemoryStore")
    assert hasattr(m, "TypedMemoryCategory")
    assert hasattr(m, "is_safe_typed_name")


def test_memory_safe_name():
    from cortex_runtime.memory import is_safe_typed_name

    assert is_safe_typed_name("ryan")
    assert is_safe_typed_name("a")  # single char valid
    assert is_safe_typed_name("ryan-lee")
    assert is_safe_typed_name("my-project-v2")
    assert not is_safe_typed_name("../evil")
    assert not is_safe_typed_name("has space")
    assert not is_safe_typed_name("UPPER")
    assert not is_safe_typed_name("foo-")  # trailing hyphen rejected
    assert not is_safe_typed_name("-foo")  # leading hyphen rejected
    assert not is_safe_typed_name("")  # empty rejected


def test_context_runtime_import():
    m = importlib.import_module("cortex_runtime.context_runtime")
    assert hasattr(m, "ContextRuntime")
    assert hasattr(m, "ContextPrompt")


def test_consumer_import():
    m = importlib.import_module("cortex_runtime.consumer")
    assert hasattr(m, "TaskConsumer")
    assert hasattr(m, "extract_discoveries")
    assert hasattr(m, "extract_memory_proposals")


def test_consumer_extract_discoveries():
    from cortex_runtime.consumer import extract_discoveries

    text = "some output\n[DISCOVERY] Found a bug in module X\nmore output"
    discoveries = extract_discoveries(text)
    assert discoveries == ["Found a bug in module X"]


def test_consumer_extract_memory_proposals():
    from cortex_runtime.consumer import extract_memory_proposals

    text = "[MEMORY: people/ryan]\nRyan is a dev/engineer.\n"
    proposals = extract_memory_proposals(text)
    assert len(proposals) == 1
    assert proposals[0].category == "people"
    assert proposals[0].name == "ryan"
    assert "dev/engineer" in proposals[0].content


def test_dispatch_import():
    m = importlib.import_module("cortex_runtime.dispatch")
    assert hasattr(m, "TaskDispatcher")


def test_session_import():
    m = importlib.import_module("cortex_runtime.session")
    assert hasattr(m, "SessionManager")
    assert hasattr(m, "SessionStore")
    assert hasattr(m, "SessionConfig")
    assert hasattr(m, "Session")


def test_plugins_import():
    m = importlib.import_module("cortex_runtime.plugins")
    assert hasattr(m, "ServicePlugin")
    assert hasattr(m, "PluginRegistry")
    assert hasattr(m, "ActionTier")


def test_providers_import():
    m = importlib.import_module("cortex_runtime.providers")
    assert hasattr(m, "ToolCall")
    assert hasattr(m, "ToolResult")
    assert hasattr(m, "build_tool_schemas")
    assert hasattr(m, "execute_tool_calls")


def test_session_state_alias_matches_session_model():
    """SessionState exported from cortex_runtime must be the same type as Session.state."""
    from cortex_runtime import SessionState
    from cortex_runtime.session.models import Session, SessionLifecycleState

    # SessionState must be the same class as SessionLifecycleState so comparisons work
    assert SessionState is SessionLifecycleState

    # Comparison against session.state must not silently return False
    s = Session(
        channel="test",
        domain=__import__("cortex_runtime.models", fromlist=["Domain"]).Domain(
            __import__("cortex_runtime.models", fromlist=["Department"]).Department.ENG
        ),
        thread_id="t1",
    )
    assert s.state == SessionState.ACTIVE


def test_no_closed_set_imports():
    """Verify no closed-set internal modules are imported at module load time."""
    closed_set_markers = [
        "cortex.hosted",
        "plexus_client",
        "cortex_cloud_agent",
        "boto3",
        "engram",
    ]
    import sys

    loaded_modules = set(sys.modules.keys())
    for marker in closed_set_markers:
        for mod_name in loaded_modules:
            assert marker not in mod_name, (
                f"Closed-set marker '{marker}' found in loaded module: {mod_name}"
            )
