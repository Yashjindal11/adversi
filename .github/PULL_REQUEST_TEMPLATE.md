## What and why

<!-- What does this change and what problem does it solve? Link issues. -->

## Checklist

- [ ] Tests cover the new behaviour (they assert outcomes, not just that code runs)
- [ ] `ruff check`, `ruff format --check`, `mypy` and `pytest` pass locally
- [ ] Public API / result schema changes are noted in `CHANGELOG.md`
- [ ] If the serialized `AdverSIResult` changed incompatibly, `RESULT_SCHEMA_VERSION` was bumped
- [ ] Prompt/role changes bump the role `version`
- [ ] No claims about reasoning quality without an evaluation to back them
