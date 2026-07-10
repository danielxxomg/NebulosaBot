# Tasks: Type-Strict Services

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 35–55 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Remove override + fix all service type errors + regression test | PR 1 | Single atomic PR; all changes interdependent |

## Phase 1: RED — Regression Test for Override Removal

- [x] 1.1 Write test in `tests/test_mypy_config.py`: `TestMypyNoServicesWildcard` class asserting no override targets `bot.services.*` module pattern — must FAIL against current `pyproject.toml`

## Phase 2: GREEN — Fix Type Errors + Remove Override

- [x] 2.1 `bot/services/guild_service.py`: import `cast` from `typing`; cast non-`None` cache hit to `GuildConfig` at the config-return site
- [x] 2.2 `bot/services/greeting_service.py`: import `cast`; cast cached config to `GuildConfig`; add `discord.Member` annotation to `_format_template`, `discord.abc.Messageable` to `_send_text_only_if_message`, `discord.Member` to `_resolve_avatar_url`; coalesce `member.guild.member_count` with `or 0`
- [x] 2.3 `bot/services/economy_service.py`: import `Any`, `cast`; type `get_leaderboard` return as `list[dict[str, Any]]`, `get_economy_config` return as `dict[str, Any] | None`; cast cached leaderboard to `list[dict[str, Any]]`
- [x] 2.4 `bot/services/ticket_service.py`: replace bare `dict` annotations in reopening helper with `dict[str, Any]`
- [x] 2.5 `bot/services/ticket_invariants.py`: replace bare `dict` annotations in `check_can_unclaim` and related signatures with `dict[str, Any]`
- [x] 2.6 `bot/services/logging_service.py`: add `# type: ignore[arg-type]` with rationale at both `can_log_in_channel(message.channel)` call sites
- [x] 2.7 `bot/services/image_service.py`: add `# type: ignore[attr-defined]` with rationale at both `Image.LANCZOS` uses
- [x] 2.8 `pyproject.toml`: delete the `[[tool.mypy.overrides]]` block targeting `bot.services.*` (lines ~135-137)

## Phase 3: Verify

- [x] 3.1 `uv run mypy bot/services/` — zero errors
- [x] 3.2 `uv run pytest tests/test_mypy_config.py` — regression test passes
- [x] 3.3 `uv run pytest` — full suite (1376 tests) green
