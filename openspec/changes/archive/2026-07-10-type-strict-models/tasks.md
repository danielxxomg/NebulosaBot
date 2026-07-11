# Tasks: Type-Strict Models

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 30–40 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

## Phase 1: RED — Failing Tests

- [x] 1.1 Add `TestMypyNoModelsWildcard` class to `tests/test_mypy_config.py` with `test_no_models_wildcard_override` asserting no override targets `bot.models.*` (mirrors `TestMypyNoServicesWildcard` pattern)
- [x] 1.2 Run `uv run pytest tests/test_mypy_config.py -k "NoModelsWildcard"` → MUST fail (override still present)
- [x] 1.3 Run `uv run mypy bot/models/` → MUST show 18 `type-arg` errors (confirms baseline)

## Phase 2: GREEN — Annotate Models

- [x] 2.1 `bot/models/guild.py` — import `Any`; change `from_db_row(cls, row: dict)` → `dict[str, Any]` and `to_db_dict(self) -> dict` → `dict[str, Any]`
- [x] 2.2 `bot/models/infraction.py` — import `Any`; same `from_db_row`/`to_db_dict` annotation
- [x] 2.3 `bot/models/member.py` — import `Any`; same `from_db_row`/`to_db_dict` annotation
- [x] 2.4 `bot/models/ticket_note.py` — import `Any`; same `from_db_row`/`to_db_dict` annotation
- [x] 2.5 `bot/models/economy_config.py` — import `Any`; same `from_db_row`/`to_db_dict` annotation
- [x] 2.6 `bot/models/greeting_config.py` — import `Any`; same `from_db_row`/`to_db_dict` annotation
- [x] 2.7 `bot/models/ticket.py` — import `Any`; annotate `custom_fields: dict[str, Any] | None`, `from_db_row(row: dict[str, Any])`, `to_db_dict() -> dict[str, Any]`
- [x] 2.8 `bot/models/ticket_category.py` — import `Any`; annotate `field_definitions: list[dict[str, Any]]`, `from_db_row(row: dict[str, Any])`, `to_db_dict() -> dict[str, Any]`

## Phase 3: GREEN — Remove Override

- [x] 3.1 Delete the `[[tool.mypy.overrides]]` block for `bot.models.*` (lines 148–150) from `pyproject.toml`
- [x] 3.2 Run `uv run pytest tests/test_mypy_config.py -k "NoModelsWildcard"` → MUST pass
- [x] 3.3 Run `uv run mypy bot/models/` → MUST report 0 errors

## Phase 4: Verify

- [x] 4.1 Run `uv run mypy` (full project) → confirm total error count drops by 18
- [x] 4.2 Run `uv run pytest` (full suite) → all existing model tests pass unchanged
- [x] 4.3 Verify no bare `dict` annotations remain in `bot/models/*.py` (search for `: dict` without `[`)
