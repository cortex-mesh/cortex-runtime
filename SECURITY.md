# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |

## Threat Model

`cortex_runtime` is an orchestration layer that sits between AI providers and
Redis Streams. The primary attack surfaces are:

**Redis**
- Credentials must be injected via environment variables (`REDIS_PASSWORD`),
  not hardcoded. The runtime trusts data from Redis — ensure your Redis
  instance is network-isolated and authenticated.

**Provider credentials**
- The provider turn-loop implementations (deferred — see `providers/_loop_driver.py`)
  will accept API keys via environment variables only. Keys must never be
  logged or included in error messages.

**Plugin system**
- Plugins are loaded via Python entry points. Only install plugins from
  trusted sources. Plugins that call `execute_action()` have access to
  external services via the credential broker.

**Task payloads**
- `TaskPayload` arrives via Redis Streams. Validate `domain` and `sender_id`
  fields in your agent implementation before acting on them.

**Memory proposals**
- `[MEMORY: category/name]` markers in agent output are proposals only.
  The conductor must apply human-gated approval before writing. Never auto-
  apply memory proposals without a human-in-the-loop gate.

## Reporting a Vulnerability

Please report security vulnerabilities via email to **security@ctxhost.com**.

Do NOT open a public GitHub issue for security vulnerabilities.

We will acknowledge your report within **48 hours** and provide a timeline
for a fix within **7 days**.

## Disclosure Policy

We follow coordinated disclosure:
1. You report privately.
2. We confirm and develop a fix (≤ 30 days for critical issues).
3. We release the fix and publish a security advisory.
4. You may then disclose publicly.
