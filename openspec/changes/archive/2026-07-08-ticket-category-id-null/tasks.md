# Tasks: Ticket Category ID Null Setup Fix

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 200–300 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR (3 work-unit commits) |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | SetupCog + /setup command (TDD) | PR 1 (commit 1) | bot/cogs/setup.py, bot/bot.py, tests/test_setup_cog.py |
| 2 | Error message updates in ticket flows (TDD) | PR 1 (commit 2) | bot/cogs/tickets.py, bot/services/ticket_service.py, tests |
| 3 | i18n keys + dashboard label fix | PR 1 (commit 3) | bot/locales/*.json, dashboard config page |

## Phase 1: SetupCog + /setup Command (TDD)

### 1.1 RED — test admin-only gate
- [x] 1.1.1 Create `tests/test_setup_cog.py`; write test: non-admin calling `/setup` is rejected with permission error (satisfies spec "Non-admin rejected")
- [x] 1.1.2 Verify RED: `uv run pytest tests/test_setup_cog.py` — test fails (no SetupCog exists)

### 1.2 RED — test required param + save
- [x] 1.2.1 Write test: admin invokes `/setup ticket_category:#Tickets` → `guild_service.save_config()` called with `ticket_category_id` set, optional fields preserved (satisfies "Admin runs setup with required param only")
- [x] 1.2.2 Write test: admin invokes `/setup` with all params → all four fields saved (satisfies "Admin runs setup with all params")
- [x] 1.2.3 Verify RED: tests fail

### 1.3 RED — test partial update preserves existing
- [x] 1.3.1 Write test: guild has `mod_role_id=111, log_channel_id=222`; invoke `/setup ticket_category:#Tickets language:en` → mod_role_id and log_channel_id unchanged (satisfies "Partial update preserves existing")
- [x] 1.3.2 Verify RED: test fails

### 1.4 GREEN — implement SetupCog
- [x] 1.4.1 Create `bot/cogs/setup.py` with `SetupCog`, `@commands.hybrid_command(name="setup")`, `@is_admin()`, typed params: `ticket_category: discord.CategoryChannel` (required), `mod_role: discord.Role | None`, `log_channel: discord.TextChannel | None`, `language: Literal["es", "en"] | None`
- [x] 1.4.2 Implement: load existing `GuildConfig` via `guild_service.get_config()`, merge non-None params, call `guild_service.save_config()`, send i18n success embed (ephemeral if slash)
- [x] 1.4.3 Modify `bot/bot.py`: add `await bot.load_extension("bot.cogs.setup")` in `setup_hook()` before tree sync
- [x] 1.4.4 Verify GREEN: `uv run pytest tests/test_setup_cog.py` — all pass

### 1.5 REFACTOR
- [x] 1.5.1 Extract embed-building helper if response logic is duplicated; keep tests green

## Phase 2: Error Message Updates in Ticket Flows (TDD)

### 2.1 RED — test actionable error wording in 3 flows
- [x] 2.1.1 In `tests/test_tickets_cog.py`: write test for `_CategorySelect.callback` when `ticket_category_id` is None → embed description mentions `/setup`, `/create_category`, dashboard URL (satisfies spec error wording)
- [x] 2.1.2 Write test for `/subticket create` when category missing → same actionable embed
- [x] 2.1.3 In `tests/test_ticket_service.py`: write test: `reopen_ticket()` raises `TicketCategoryNotConfiguredError` when category is None (satisfies design "TicketService raises typed exception")
- [x] 2.1.4 Verify RED: tests fail

### 2.2 GREEN — update ticket flows
- [x] 2.2.1 In `bot/services/ticket_service.py`: raise `TicketCategoryNotConfiguredError` (new exception class) when reopen cannot resolve category; keep audit insert
- [x] 2.2.2 In `bot/cogs/tickets.py`: replace raw error strings in `_CategorySelect.callback`, `/subticket create`, and `/reopen` catch with `t(guild_id, "tickets.config_missing.title/description")` embeds
- [x] 2.2.3 Verify GREEN: `uv run pytest tests/test_tickets_cog.py tests/test_ticket_service.py` — all pass

### 2.3 REFACTOR
- [x] 2.3.1 Extract shared `_send_config_missing_embed(ctx, guild_id)` helper if 3 call sites repeat logic; keep tests green

## Phase 3: i18n Keys + Dashboard Label Fix

### 3.1 Add i18n keys
- [x] 3.1.1 Add to `bot/locales/en.json`: `setup.success_title`, `setup.success_description`, `setup.error_title`, `tickets.config_missing.title`, `tickets.config_missing.description` (dashboard URL hardcoded in value)
- [x] 3.1.2 Add equivalent keys to `bot/locales/es.json`
- [x] 3.1.3 Verify: `uv run pytest` — all tests still pass (i18n keys now resolve)

### 3.2 Dashboard label fix
- [x] 3.2.1 In `dashboard/app/(authenticated)/guilds/[guildId]/config/page.tsx`: change `ticket_category_id` hint text to "Discord Category Channel ID (right-click → Copy Channel ID)" (satisfies "Dashboard shows corrected label")
- [x] 3.2.2 Add/verify Vitest or component test for corrected label text
- [x] 3.2.3 Verify: `npm test` or `npx vitest` in dashboard — pass

## Phase 4: Pre-Push Verification + Delivery

### 4.1 Full test suite
- [x] 4.1.1 Run `uv run pytest` — all tests pass, no regressions
- [x] 4.1.2 Run `uv run pytest --cov=bot --cov-report=term` — coverage ≥ 70%
- [x] 4.1.3 Run `python -m py_compile bot/__main__.py` — no syntax errors

### 4.2 Commit + deliver
- [x] 4.2.1 Commit 1: `feat(bot): add setup command for ticket category config` — SetupCog, bot loading, setup tests
- [x] 4.2.2 Commit 2: `fix(tickets): surface actionable missing category guidance` — i18n keys, ticket flow/service updates, tests
- [x] 4.2.3 Commit 3: `fix(dashboard): clarify ticket category id label` — dashboard copy + test
- [x] 4.2.4 Push branch, create PR targeting master
