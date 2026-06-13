"""ServicePlugin protocol for cortex_runtime.

Defines the ``ServicePlugin`` protocol — the contract that any external
service integration must satisfy to work with the cortex_runtime plugin system.

Uses ``typing.Protocol`` (structural typing) so implementations do NOT
need to inherit from or import this class.

Plugins receive a credential broker during ``setup()``. The broker type is
intentionally left as ``Any`` here to avoid a closed-set dependency on a
specific credential management system. Implement the protocol duck-typing:
any object with a ``get_client(service, **kwargs)`` async method works.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from cortex_runtime.plugins.models import PluginActionInfo, PluginHealthReport, PluginResult


@runtime_checkable
class ServicePlugin(Protocol):
    """Interface for external service integrations.

    Plugins expose actions that agents can invoke. Each action has a
    permission tier controlling whether it runs automatically, notifies
    the user, or requires explicit approval.

    Lifecycle:
        1. Registry calls ``setup(broker)`` when loading the plugin
        2. Plugin stores the broker reference for later use
        3. Registry calls ``list_actions()`` to discover capabilities
        4. Orchestrator routes action requests via ``execute_action()``
        5. Registry calls ``teardown()`` during shutdown
    """

    @property
    def name(self) -> str:
        """Unique plugin identifier (e.g. ``"google-calendar"``)."""
        ...

    @property
    def version(self) -> str:
        """Semantic version of the plugin."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description of the plugin."""
        ...

    async def setup(self, broker: Any) -> None:
        """Initialize the plugin with credential access.

        Args:
            broker: Credential broker. Any object with a ``get_client()``
                async method that returns an authenticated HTTP client.
        """
        ...

    async def teardown(self) -> None:
        """Clean up resources (HTTP sessions, caches, etc.)."""
        ...

    def list_actions(self) -> list[PluginActionInfo]:
        """List all actions this plugin supports."""
        ...

    async def execute_action(
        self,
        action: str,
        params: dict[str, Any],
    ) -> PluginResult:
        """Execute a named action.

        Args:
            action: Action name (e.g. ``"list_events"``).
            params: Action parameters (pre-validated by registry).

        Returns:
            Result with success/failure status and data.

        Raises:
            PluginActionError: Action failed.
            PluginAuthError: Credentials missing or expired.
            PluginRateLimitError: Service rate limit exceeded.
        """
        ...

    async def health(self) -> PluginHealthReport:
        """Check plugin health and credential validity."""
        ...
