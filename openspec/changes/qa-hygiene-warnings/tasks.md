# Tasks: QA Hygiene Warnings

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 130–150 |
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
| 1 | Ruff fixes + load resilience | PR 1 | All 3 phases included; single PR |

## Phase 1: Ruff Fixes + Load Resilience

- [x] 1.1 **RED** — Write `tests/test_bot_load_resilience.py`: test that `setup_hook()` logs ERROR and continues when one `load_extension()` raises, test that all valid extensions still load
- [x] 1.2 **GREEN** — Fix I001 in `bot/cogs/core.py` lines 20–21: swap `bot.utils.brand` before `bot.utils.checks` (alphabetical import order)
- [x] 1.3 **GREEN** — Fix SIM102 in `bot/services/ticket_field_service.py` lines 91–95: collapse nested `if placeholder is not None:` + inner `if` into single condition
- [x] 1.4 **GREEN** — Wrap each `load_extension()` call in `bot/bot.py` lines 224–252 with try/except, `logging.exception()` per failure, continue loading remaining cogs
- [x] 1.5 **REFACTOR** — Run `ruff check bot/` and `pytest tests/test_bot_load_resilience.py` — verify 0 ruff errors, load resilience tests pass

## Phase 2: AsyncMock + ResourceWarning Fixes

- [x] 2.1 **RED** — Run `pytest -W error::RuntimeWarning:unittest.mock` to confirm the 5–6 AsyncMock warnings reproduce as failures
- [x] 2.2 **GREEN** — Fix `tests/test_tickets_cog.py`: `TestReopenByTicketRef::test_reopen_wrong_guild_denied` and `TestCloseEdgeCases::test_close_no_ticket` — consume or suppress residual AsyncMock coroutines (adjust `side_effect` ordering or add explicit `await` on mock calls)
- [x] 2.3 **GREEN** — Fix `tests/test_ticket_service.py`: `test_create_ticket_without_custom_fields` and `test_claim_ticket_updates_status` — fix `AsyncMock` coroutine tracking (ensure `side_effect` entries are fully consumed)
- [x] 2.4 **GREEN** — Fix `tests/test_sentinel_i18n.py`: `TestUnwarnI18n::test_unwarn_success_es` — fix residual `AsyncMock` coroutines from `get_active_warnings`, `deactivate_infraction`, `update_member_warnings`
- [x] 2.5 **GREEN** — Fix `bot/cogs/ocio.py` line 83: wrap `discord.File()` in context manager or explicit `file.close()` after `ctx.send()` to eliminate ResourceWarning on `banana.webp`
- [x] 2.6 **REFACTOR** — Run `pytest -W error::RuntimeWarning:unittest.mock -W error::ResourceWarning` — verify 0 warnings from these categories

## Phase 3: TextInput.label Suppression + Filterwarnings

- [x] 3.1 **RED** — Run `pytest -W error::DeprecationWarning:discord.ui` to confirm the TextInput.label deprecation warning reproduces
- [x] 3.2 **GREEN** — Add `"ignore::DeprecationWarning:discord.ui"` to `pyproject.toml` `filterwarnings` section (full `Label` migration deferred to separate change)
- [x] 3.3 **GREEN** — Add `"error"` to `filterwarnings` in `pyproject.toml` to promote all remaining warnings to errors (locks zero-warning discipline)
- [x] 3.4 **REFACTOR** — Run full `pytest` suite — verify 0 warnings, all 1268+ tests pass, `ruff check bot/` clean

## Phase 4: Verification

- [x] 4.1 Run `pytest --tb=short -q` — confirm 0 warnings, exit code 0
- [x] 4.2 Run `ruff check bot/` — confirm 0 errors
- [x] 4.3 Manual smoke: start bot, verify all cogs load (or log errors for broken ones), confirm no crash on single cog failure
