# Writing a Plugin

Plugins give agents access to external services through a uniform action interface.
They ship in separate packages and are discovered via Python entry points.

## 1. Create the plugin class

```python
# my_package/plugin.py

from cortex_runtime.plugins.models import (
    ActionTier,
    PluginActionInfo,
    PluginHealthReport,
    PluginHealthStatus,
    PluginResult,
)


class CalendarPlugin:
    name = "calendar"
    version = "1.0.0"
    description = "Read and write calendar events"

    def __init__(self):
        self._client = None

    async def setup(self, broker) -> None:
        """Called once before the first action. broker is your credential source."""
        api_key = await broker.get("calendar_api_key")
        self._client = MyCalendarClient(api_key)

    async def teardown(self) -> None:
        if self._client:
            await self._client.close()

    def list_actions(self) -> list[PluginActionInfo]:
        return [
            PluginActionInfo(
                name="list_events",
                description="List calendar events for a date range",
                tier=ActionTier.AUTO,
                parameters={
                    "type": "object",
                    "properties": {
                        "start": {"type": "string", "description": "ISO date"},
                        "end":   {"type": "string", "description": "ISO date"},
                    },
                    "required": ["start", "end"],
                },
            ),
            PluginActionInfo(
                name="create_event",
                description="Create a calendar event",
                tier=ActionTier.CONFIRM,  # requires user confirmation
            ),
        ]

    async def execute_action(self, action: str, params: dict) -> PluginResult:
        if action == "list_events":
            events = await self._client.list(params["start"], params["end"])
            return PluginResult(success=True, data={"events": events})
        if action == "create_event":
            event = await self._client.create(**params)
            return PluginResult(success=True, data={"event_id": event.id})
        return PluginResult(success=False, error=f"Unknown action: {action}")

    async def health(self) -> PluginHealthReport:
        try:
            await self._client.ping()
            return PluginHealthReport(plugin=self.name, status=PluginHealthStatus.HEALTHY)
        except Exception as e:
            return PluginHealthReport(
                plugin=self.name,
                status=PluginHealthStatus.UNHEALTHY,
                error=str(e),
            )
```

## 2. Register the entry point

In your plugin package's `pyproject.toml`:

```toml
[project.entry-points."cortex_runtime.plugins"]
calendar = my_package.plugin:CalendarPlugin
```

The key (`calendar`) is the plugin name. The value is `module:class`.

## 3. Install and use

```bash
pip install my-calendar-plugin
```

The registry discovers and loads it:

```python
from cortex_runtime.plugins.registry import PluginRegistry

registry = PluginRegistry(broker=my_credential_broker)
await registry.discover_and_register()   # finds CalendarPlugin via entry points
await registry.setup_all_pending()       # calls setup(broker) on each

result = await registry.execute("calendar", "list_events", {
    "start": "2026-06-01",
    "end": "2026-06-30",
})
print(result.data)
```

## Action tiers

| Tier | Meaning |
|------|---------|
| `AUTO` | Agent can invoke without confirmation |
| `CONFIRM` | Requires explicit user approval before execution |
| `ADMIN` | Reserved for privileged operations |

## Parameter validation

If `PluginActionInfo.parameters` is a JSON Schema object and `jsonschema` is
installed (`pip install cortex-runtime[plugins]`), the registry validates
`params` before calling `execute_action()`. Invalid params raise
`PluginValidationError` before your code runs.

## Testing a plugin in isolation

```python
import pytest
from my_package.plugin import CalendarPlugin


@pytest.fixture
async def plugin():
    p = CalendarPlugin()
    await p.setup(broker=FakeBroker({"calendar_api_key": "test-key"}))
    yield p
    await p.teardown()


async def test_list_events(plugin):
    result = await plugin.execute_action("list_events", {"start": "2026-06-01", "end": "2026-06-30"})
    assert result.success
```
