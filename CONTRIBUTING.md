# Contributing to cortex-runtime

Thank you for your interest in contributing!

## Contributor License Agreement (CLA)

By submitting a pull request, you agree that your contributions are
licensed under the same terms as the project (Functional Source License
1.1, MIT Future License). You retain copyright over your contributions.

## Getting Started

```bash
git clone https://github.com/cortex-mesh/cortex-runtime
cd cortex-runtime
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest
```

## Linting and Formatting

```bash
ruff check src tests
ruff format src tests
```

## Pull Request Guidelines

- **Branch naming**: `feat/`, `fix/`, `chore/`, `docs/`
- **Commit style**: Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`)
- **Tests**: All new code must include tests
- **No secrets**: Never commit credentials, API keys, or internal hostnames
- **One concern per PR**: Keep PRs focused

## What We Accept

- Bug fixes with tests
- Performance improvements to the bus / consumer loop
- New `MemoryStore` or `SessionStore` implementations
- New plugin adapters (external service integrations)
- Documentation improvements

## What We Don't Accept (Yet)

- Provider loop driver implementations (deferred to a separate release cycle)
- Changes to the dispatch wire models without a corresponding ADR
- Breaking changes to the public protocol surface

## Code of Conduct

Be respectful. We follow the
[Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
