# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.1] — 2026-06-13

### Fixed

- `SessionState` in `__init__.py` now correctly re-exports `SessionLifecycleState`
  from `cortex_runtime.session.models`. The previous duplicate `StrEnum` in
  `models.py` caused comparisons against `Session.state` to silently return `False`.
- `RedisStreamBus.publish()` default for `msg_type` changed from `""` to `"task"`;
  default for `maxlen` changed from `None` to `1000`; guard changed to
  `if maxlen > 0` to prevent unbounded stream growth.
- `PluginRegistry.ensure_ready()` now evicts a plugin from `_pending_setup` and
  `_plugin_info` on setup failure, preventing an infinite retry loop on each
  subsequent `execute()` call.
- `PluginRegistry.shutdown()` now clears `_plugin_info` entries for plugins that
  were discovered but never set up (pending state), preventing stale registry state.
- `Keyspace` now lowercases `org_id` before comparison, so `"Personal"`,
  `"PERSONAL"`, and `"  Personal  "` correctly map to the fleet (global) namespace.
- `is_safe_typed_name()` regex tightened from `[a-z0-9][a-z0-9\-]*` to
  `[a-z0-9]+(-[a-z0-9]+)*`, rejecting trailing and leading hyphens and empty strings.

## [0.1.0] — 2026-06-13

### Added

- Initial open-source extraction of the CORTEX mesh runtime kernel.
- `MessageBus` protocol and `RedisStreamBus` implementation using Redis Streams
  (`XADD` / `XREADGROUP` / `XAUTOCLAIM`) with client-side `asyncio.wait_for()`
  watchdog and own-PEL redelivery for crash recovery.
- `TaskConsumer` — agent-side blocking XREADGROUP loop with domain and
  per-agent stream subscriptions, task ACK/NACK, and discovery/memory extraction.
- `TaskDispatcher` — conductor-side routing with domain, @mention, and thread
  affinity resolution.
- `ContextRuntime` (ADR-088) — hot/warm/cold three-tier session context with
  `prepare_payload()` and `build_prompt()`.
- `MemoryStore` protocol with file-based implementation and typed memory categories.
- `SessionManager`, `SessionStore` protocol, `Session` model with lifecycle states.
- `ServicePlugin` structural protocol and `PluginRegistry` with two-phase
  (discover / setup) loading via entry point group `cortex_runtime.plugins`.
- `Keyspace` — org-partitioned Redis key builder with fleet/org namespace scoping.
- Dispatch wire models: `TaskPayload`, `TaskResult`, `MemoryProposal`, `DispatchResult`.
- `BusConfig` pydantic model with env-var defaults for Redis connection and bus tuning.
- FSL-1.1-MIT license with CLA in `CONTRIBUTING.md`.
