"""Provider loop driver — deferred (TODO).

The concrete LLM provider implementations (Anthropic API, etc.) are
intentionally excluded from this initial release pending the native
loop driver design (ADR-120 — "Pillar" phase).

This module is the designated seam. Future provider implementations
should be added here as classes that satisfy the :class:`CortexProvider`
protocol::

    from cortex_runtime.provider import CortexProvider
    from cortex_runtime.models import HealthStatus, StreamChunk, StreamChunkKind

    class AnthropicAPIProvider:
        \"\"\"Anthropic API provider (to be implemented).\"\"\"

        def execute(
            self,
            prompt: str,
            *,
            context: dict | None = None,
            working_directory: str | None = None,
        ):
            # TODO: implement streaming execution via anthropic SDK
            raise NotImplementedError("Provider loop driver not yet implemented")

        async def health(self) -> HealthStatus:
            raise NotImplementedError("Provider loop driver not yet implemented")

Tracking issue: https://github.com/cortex-mesh/cortex-runtime/issues (TBD)
"""

# TODO(ADR-120): Implement native loop driver provider implementations.
# This module is intentionally empty until the Pillar phase design is finalized.
