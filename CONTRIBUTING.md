# Contributing to AdverSI

Thanks for considering a contribution. AdverSI is maintained by one person, so the
process is designed to keep reviews quick and the codebase small.

## Development setup

```bash
git clone https://github.com/Yashjindal11/adversi && cd adversi
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pre-commit install

pytest -q          # no network or API keys needed
ruff check src tests examples scripts && ruff format --check src tests
mypy               # strict

# web UI
cd web && npm ci && npm run dev     # proxies /api to 127.0.0.1:8765
python scripts/demo_server.py       # scripted backend, no keys needed
```

## What makes a good contribution

- **Providers, tools, steps, roles and scorers** should usually be plugins or examples
  first. Move them into the core only when they are broadly useful and have no extra
  dependencies. Providers can be shipped as separate packages via the `adversi.providers`
  entry point.
- **Reasoning changes** (prompts, policies, workflow shapes) should come with a way to
  evaluate them. "It produces better-looking answers" is not evidence; a benchmark
  comparison with confidence intervals is.
- **Protocol changes** (anything in `adversi.protocol`) are public API. Additive fields are
  fine. Renames/removals need a `RESULT_SCHEMA_VERSION` bump and a CHANGELOG entry.
- **Prompt changes** to a built-in role must bump that role's `version` so runs remain
  traceable.

## Tests

Tests must assert behaviour, not just execute code. Use
`adversi.testing.ScriptedProvider` to script model responses by `request.metadata`
(`agent`, `role`, `step`, `schema`); see `tests/conftest.py` for a full scripted run.
Tests that call real providers must be marked `@pytest.mark.live` and are skipped by
default.

## Style

- Python 3.11+, full type hints, `mypy --strict` clean.
- `ruff format` owns formatting.
- Keep the core dependency list at `pydantic` + `httpx`.
- Comments explain *why*, not *what*.

## Commits and releases

Conventional, descriptive commit messages. Versions follow [SemVer](https://semver.org);
before 1.0, minor versions may contain breaking changes, always noted in
[CHANGELOG.md](CHANGELOG.md). Releases are cut by tagging `vX.Y.Z`; CI builds the web UI
into the wheel and publishes via PyPI trusted publishing.

## Conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
