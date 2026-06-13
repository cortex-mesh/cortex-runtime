"""Plugin registry for cortex_runtime.

Discovers, loads, and manages service plugin lifecycle. The registry is
the central coordination point between the orchestrator and individual
service plugins.

Plugins are discovered via the ``cortex_runtime.plugins`` entry point group.
Any installable package can expose plugins by adding an entry point::

    [project.entry-points."cortex_runtime.plugins"]
    my-plugin = my_package.plugin:MyPlugin
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any

from cortex_runtime.plugins.exceptions import (
    PluginActionError,
    PluginNotFoundError,
    PluginValidationError,
)
from cortex_runtime.plugins.models import (
    PluginHealthReport,
    PluginHealthStatus,
    PluginInfo,
    PluginResult,
)
from cortex_runtime.plugins.protocol import ServicePlugin

logger = logging.getLogger(__name__)

PLUGIN_ENTRY_POINT_GROUP = "cortex_runtime.plugins"


@dataclass
class DiscoveredPlugin:
    """Metadata about a discovered (but not yet loaded) plugin."""

    name: str
    module: str
    attr: str
    error: str | None = None


class PluginRegistry:
    """Discovers, loads, and manages service plugins.

    Supports two-phase loading for resilient startup:
        - **Eager discovery** (``discover_and_register``): instantiate plugins
          and collect action metadata WITHOUT calling ``setup()``.
        - **Deferred setup** (``ensure_ready``): call ``setup(broker)`` on
          first use or eagerly via ``setup_all_pending()``.

    Example::

        registry = PluginRegistry()
        await registry.load_plugin(MyPlugin(), broker=my_broker)

        result = await registry.execute("my-plugin", "do_thing", {"key": "value"})
        await registry.shutdown()
    """

    def __init__(self, broker: Any = None) -> None:
        """Initialize the registry.

        Args:
            broker: Credential broker to inject into plugins. Can be None
                for discovery-only mode.
        """
        self._broker = broker
        self._plugins: dict[str, ServicePlugin] = {}
        self._pending_setup: dict[str, ServicePlugin] = {}
        self._plugin_info: dict[str, PluginInfo] = {}
        self._loading: set[str] = set()

    def set_broker(self, broker: Any) -> None:
        """Set or replace the credential broker."""
        self._broker = broker

    async def load_plugin(self, plugin: ServicePlugin, broker: Any = None) -> None:
        """Load and initialize a plugin.

        Args:
            plugin: The plugin instance to load.
            broker: Optional broker override (uses registry broker if None).
        """
        name = plugin.name
        if name in self._plugins:
            raise ValueError(f"Plugin '{name}' is already loaded")

        effective_broker = broker or self._broker
        if effective_broker is None:
            raise ValueError("Cannot load plugin without a credential broker")

        logger.info("Loading plugin: %s v%s", name, plugin.version)
        await plugin.setup(effective_broker)

        self._plugins[name] = plugin
        self._plugin_info[name] = PluginInfo(
            name=name,
            version=plugin.version,
            description=plugin.description,
            actions=plugin.list_actions(),
        )

        logger.info(
            "Plugin loaded: %s (%d actions)",
            name,
            len(self._plugin_info[name].actions),
        )

    def is_known(self, name: str) -> bool:
        """Check if a plugin is loaded or pending setup."""
        return name in self._plugins or name in self._pending_setup

    def is_loaded(self, name: str) -> bool:
        """Check if a plugin has completed setup."""
        return name in self._plugins

    @property
    def pending_count(self) -> int:
        return len(self._pending_setup)

    @property
    def registered_count(self) -> int:
        return len(self._plugins) + len(self._pending_setup)

    def discover_plugins(self) -> list[DiscoveredPlugin]:
        """Scan the entry point group for available plugins."""
        discovered: list[DiscoveredPlugin] = []
        eps = entry_points(group=PLUGIN_ENTRY_POINT_GROUP)
        for ep in eps:
            discovered.append(
                DiscoveredPlugin(
                    name=ep.name,
                    module=ep.value.rsplit(":", 1)[0] if ":" in ep.value else ep.value,
                    attr=ep.value.rsplit(":", 1)[1] if ":" in ep.value else "",
                )
            )
        logger.info("Discovered %d plugin(s) via entry points", len(discovered))
        return discovered

    async def discover_and_register(self) -> list[DiscoveredPlugin]:
        """Discover plugins via entry points and register without setup."""
        discovered = self.discover_plugins()
        eps = entry_points(group=PLUGIN_ENTRY_POINT_GROUP)
        ep_map = {ep.name: ep for ep in eps}

        for dp in discovered:
            if dp.name in self._plugins or dp.name in self._pending_setup:
                continue
            try:
                ep = ep_map.get(dp.name)
                if ep is None:
                    dp.error = f"Entry point '{dp.name}' not found"
                    continue

                plugin_factory = ep.load()
                plugin = plugin_factory()
                self._pending_setup[plugin.name] = plugin
                self._plugin_info[plugin.name] = PluginInfo(
                    name=plugin.name,
                    version=plugin.version,
                    description=plugin.description,
                    actions=plugin.list_actions(),
                )
                logger.info("Registered plugin (pending setup): %s", plugin.name)
            except Exception as e:
                dp.error = str(e)
                logger.warning("Failed to register plugin '%s': %s", dp.name, e)

        return discovered

    async def ensure_ready(self, name: str) -> bool:
        """Ensure a plugin has completed setup, triggering it if needed."""
        if name in self._plugins:
            return True
        if name not in self._pending_setup:
            return False
        if self._broker is None:
            logger.warning("Cannot setup plugin '%s': no broker available", name)
            return False
        if name in self._loading:
            return False
        self._loading.add(name)
        try:
            plugin = self._pending_setup[name]
            await plugin.setup(self._broker)
            del self._pending_setup[name]
            self._plugins[name] = plugin
            logger.info("Plugin setup complete: %s", name)
            return True
        except Exception as e:
            logger.warning("Plugin '%s' setup failed: %s", name, e)
            return False
        finally:
            self._loading.discard(name)

    async def setup_all_pending(self) -> int:
        """Best-effort eager setup of all pending plugins."""
        if not self._pending_setup:
            return 0
        loaded = 0
        for name in list(self._pending_setup.keys()):
            if await self.ensure_ready(name):
                loaded += 1
        return loaded

    async def execute(
        self,
        plugin_name: str,
        action: str,
        params: dict[str, Any],
    ) -> PluginResult:
        """Execute a plugin action.

        Raises:
            PluginNotFoundError: Plugin not loaded.
            PluginValidationError: Parameters invalid.
            PluginActionError: Action not found or execution failed.
        """
        if plugin_name not in self._plugins and plugin_name in self._pending_setup:
            ready = await self.ensure_ready(plugin_name)
            if not ready:
                raise PluginNotFoundError(
                    f"Plugin '{plugin_name}' registered but setup failed",
                    plugin=plugin_name,
                )

        if plugin_name not in self._plugins:
            raise PluginNotFoundError(
                f"Plugin '{plugin_name}' is not loaded",
                plugin=plugin_name,
            )

        plugin = self._plugins[plugin_name]
        info = self._plugin_info[plugin_name]

        action_info = next((a for a in info.actions if a.name == action), None)
        if action_info is None:
            raise PluginActionError(
                f"Action '{action}' not found in plugin '{plugin_name}'",
                plugin=plugin_name,
                action=action,
            )

        if action_info.parameters:
            try:
                import jsonschema
                jsonschema.validate(instance=params, schema=action_info.parameters)
            except ImportError:
                pass  # jsonschema optional — skip validation if not installed
            except Exception as e:
                raise PluginValidationError(
                    f"Invalid parameters for {plugin_name}.{action}: {e}",
                    plugin=plugin_name,
                    action=action,
                ) from e

        logger.debug("Executing %s.%s", plugin_name, action)
        return await plugin.execute_action(action, params)

    def get_plugin(self, name: str) -> ServicePlugin | None:
        return self._plugins.get(name)

    def list_plugins(self) -> list[PluginInfo]:
        return list(self._plugin_info.values())

    def get_plugin_info(self, name: str) -> PluginInfo | None:
        return self._plugin_info.get(name)

    async def health(self, plugin_name: str) -> PluginHealthReport:
        """Check health of a specific plugin."""
        if plugin_name not in self._plugins:
            raise PluginNotFoundError(
                f"Plugin '{plugin_name}' is not loaded",
                plugin=plugin_name,
            )
        return await self._plugins[plugin_name].health()

    async def health_all(self) -> dict[str, PluginHealthReport]:
        """Check health of all loaded plugins."""
        reports: dict[str, PluginHealthReport] = {}
        for name in self._plugins:
            try:
                reports[name] = await self.health(name)
            except Exception as e:
                logger.warning("Health check failed for %s: %s", name, e)
                reports[name] = PluginHealthReport(
                    plugin=name,
                    status=PluginHealthStatus.UNHEALTHY,
                    error=str(e),
                )
        return reports

    async def unload_plugin(self, name: str) -> None:
        """Unload a plugin and call teardown."""
        if name not in self._plugins:
            raise PluginNotFoundError(f"Plugin '{name}' is not loaded", plugin=name)
        await self._plugins[name].teardown()
        del self._plugins[name]
        del self._plugin_info[name]
        logger.info("Plugin unloaded: %s", name)

    async def shutdown(self) -> None:
        """Gracefully shut down all plugins."""
        for name in list(self._plugins.keys()):
            try:
                await self.unload_plugin(name)
            except Exception as e:
                logger.error("Error unloading plugin %s: %s", name, e)
        self._pending_setup.clear()
        logger.info("Plugin registry shutdown complete")

    def __len__(self) -> int:
        return len(self._plugins)

    def __contains__(self, name: str) -> bool:
        return name in self._plugins
