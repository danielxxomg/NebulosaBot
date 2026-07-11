# Tasks: Strict Core and Listener Typing

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 100–150 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | auto-chain (inherited) |
| Chain strategy | single-pr |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: single-pr
400-line budget risk: Low

## Phase 1: RED — Failing Config Guard Tests

- [x] 1.1 Rewrite `tests/test_mypy_config.py` `TestMypyOverrides`: remove `test_bot_bot_override_exists`, `test_bot_bot_override_disables_attr_defined`, `test_attr_defined_not_suppressed_in_other_bot_modules`; add tests asserting NO override targets `bot.core.*`, `bot.listeners.*`, or `bot.bot`; keep `test_cogs_*` and `test_no_*_wildcard_override` unchanged. Run RED: `uv run pytest tests/test_mypy_config.py -x` — new tests fail because overrides still exist.

## Phase 2: GREEN — Fix Type Errors (bot/core/db/*.py)

- [x] 2.1 `bot/core/db/base.py`: replace bare `dict` / `list[dict]` return annotations with `dict[str, Any]` / `list[dict[str, Any]]`; add `from __future__ import annotations` and `Any` import if missing.
- [x] 2.2 `bot/core/db/economy_db.py`: same type-arg fixes for all bare dict annotations.
- [x] 2.3 `bot/core/db/greeting_db.py`, `bot/core/db/guild_db.py`, `bot/core/db/member_db.py`: type-arg fixes.
- [x] 2.4 `bot/core/db/infraction_db.py`, `bot/core/db/ticket_audit_db.py`, `bot/core/db/ticket_note_db.py`: type-arg fixes.
- [x] 2.5 `bot/core/db/ticket_category_db.py`, `bot/core/db/ticket_db.py`: type-arg fixes.

## Phase 3: GREEN — Fix Type Errors (core/context, core/realtime, core/i18n)

- [x] 3.1 `bot/core/context.py`: add `cast()` on `self.bot.db` → `Database` and `self.bot.cache` → `TTLCache` in property accessors.
- [x] 3.2 `bot/core/realtime.py`: parameterize bare `dict` / `list[dict]` annotations as `dict[str, Any]` / `list[dict[str, Any]]`.
- [x] 3.3 `bot/core/i18n.py`: same type-arg fixes.

## Phase 4: GREEN — Fix Type Errors (listeners, bot.py)

- [x] 4.1 `bot/listeners/audit_listener.py`: add `isinstance(before.channel, discord.abc.GuildChannel)` guard before the visibility check; early-return otherwise.
- [x] 4.2 `bot/listeners/xp_listener.py`: narrow `guild.get_channel()` result with `isinstance` check before assigning as messageable send target.
- [x] 4.3 `bot/bot.py`: add `assert isinstance(ctx, NebulosaContext)` after `super().get_context()` in `get_context()` override.

## Phase 5: GREEN — Remove Override Blocks

- [x] 5.1 `pyproject.toml`: delete the three `[[tool.mypy.overrides]]` blocks for `bot.bot` (lines 132–134), `bot.core.*` (lines 140–142), and `bot.listeners.*` (lines 144–146). Keep `bot.cogs.*` and `tests.*` blocks.
- [x] 5.2 Run GREEN: `uv run pytest tests/test_mypy_config.py -x` — all tests pass.

## Phase 6: REFACTOR — Verify and Clean

- [x] 6.1 Run full mypy: `uv run mypy --strict --python-version 3.11 bot/core/ bot/listeners/ bot/bot.py` — 0 errors.
- [x] 6.2 Run full test suite: `uv run pytest` — all tests pass, no regressions.
- [x] 6.3 Verify only `bot.cogs.*` and `tests.*` overrides remain in `pyproject.toml`.
