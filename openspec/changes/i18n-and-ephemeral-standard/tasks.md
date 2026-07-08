# Tasks: i18n and Ephemeral Standard

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 1000–1200 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 |
| Delivery strategy | auto-chain |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | i18n core + locale files + embeds + Core/Utility/Ocio | PR 1 | Base: main. Tests: test_i18n.py, cog visibility. |
| 2 | Tickets cog + ticket/transcript service migration | PR 2 | Base: PR 1 branch. Tests: ticket string + ephemeral. |
| 3 | Sentinel + Stellar + Greetings + remaining services | PR 3 | Base: PR 2 branch. Tests: sentinel string + perms. |
| 4 | Ephemeral standard + default_permissions + error DM + "," prefix | PR 4 | Base: PR 3 branch. Tests: ephemeral, DM fallback, prefix. |

## Phase 1: i18n Core (PR 1)

- [x] 1.1 RED: Write `tests/test_i18n.py` — test `t()` es lookup, en lookup, missing-key fallback to es, exhausted fallback returns raw key, interpolation `{latency}`, missing placeholder warning, None guild_id fallback
- [x] 1.2 GREEN: Create `bot/core/i18n.py` with `load_locales()`, `set_guild_language()`, `t()` — module-level dicts, dot-notation resolver, es fallback, `.format_map()` interpolation, `logging.warning` on miss
- [x] 1.3 REFACTOR: Verify `t()` signatures match design contract (`guild_id: str|int|None, key: str, **kwargs: object -> str`)
- [x] 1.4 Create `bot/locales/es.json` — all strings for Core, Utility, Ocio cogs + common embed labels
- [x] 1.5 Create `bot/locales/en.json` — English translations for same keys
- [x] 1.6 Modify `bot/bot.py` `setup_hook()` — call `load_locales(Path("bot/locales"))` before cog loading
- [x] 1.7 Modify `bot/services/guild_service.py` — call `set_guild_language()` in `get_config`, `save_config`, `on_guild_join`, startup backfill
- [x] 1.8 Modify `bot/utils/embeds.py` — add optional `guild_id` param to `error_embed`, `success_embed`, `info_embed`, `warning_embed`; wire `t()` for footer/default text
- [x] 1.9 Migrate `bot/cogs/core.py` — replace hardcoded strings in `ping`, `status`, `help` with `t()` calls
- [x] 1.10 Migrate `bot/cogs/utility.py` — replace hardcoded strings with `t()` calls
- [x] 1.11 Migrate `bot/cogs/ocio.py` — replace hardcoded strings with `t()` calls
- [x] 1.12 Add locale keys for Core/Utility/Ocio to `es.json` and `en.json`
- [x] 1.13 Run `uv run pytest` — all tests green

## Phase 2: Tickets Migration (PR 2)

- [x] 2.1 Add ticket-related locale keys to `es.json` and `en.json` (panel, category, subticket strings)
- [x] 2.2 Migrate `bot/cogs/tickets.py` — replace all hardcoded strings with `t()` calls
- [x] 2.3 Migrate `bot/services/ticket_service.py` — replace user-facing strings with `t()`
- [x] 2.4 Migrate `bot/services/transcript_service.py` — replace user-facing strings with `t()`
- [x] 2.5 RED: Test ticket commands return localized strings for es/en guilds
- [x] 2.6 GREEN + REFACTOR: Verify tests pass with `uv run pytest`

## Phase 3: Sentinel + Remaining Services (PR 3)

- [x] 3.1 Add sentinel/stellar/greetings locale keys to `es.json` and `en.json`
- [x] 3.2 Migrate `bot/cogs/sentinel.py` — replace hardcoded strings with `t()`
- [x] 3.3 Migrate `bot/cogs/stellar.py` — replace hardcoded strings with `t()`
- [x] 3.4 Migrate `bot/cogs/greetings.py` — replace hardcoded strings with `t()`
- [x] 3.5 Migrate `bot/services/economy_service.py`, `greeting_service.py`, `infraction_service.py`, `logging_service.py`, `image_service.py` — replace user-facing strings with `t()`
- [x] 3.6 RED: Test sentinel commands return localized strings; stellar economy strings localized
- [x] 3.7 GREEN + REFACTOR: Verify tests pass with `uv run pytest`

## Phase 4: Ephemeral + Permissions + Prefix (PR 4)

- [ ] 4.1 RED: Write tests for prefix callable returning `[config.prefix, ","]`; test `,ping` invokes ping
- [ ] 4.2 GREEN: Modify `bot/bot.py` `_build_prefix_callable()` — return `[config.prefix or "nb!", ","]`
- [ ] 4.3 RED: Write tests for `on_command_error` — slash errors ephemeral, prefix errors DM, DM failure → channel fallback
- [ ] 4.4 GREEN: Modify `bot/bot.py` `on_command_error` — slash: `interaction.response.send_message(ephemeral=True)`, prefix: `ctx.author.send()` with `discord.HTTPException` fallback to channel
- [ ] 4.5 Add `ephemeral=True` to admin slash responses in `tickets.py`: `ticket_panel`, `create_category`, `list_categories`, `delete_category`
- [ ] 4.6 Add `ephemeral=True` to `core.py`: `ping`, `status`, `help`
- [ ] 4.7 Add `ephemeral=True` to `sentinel.py`: `modlogs`
- [ ] 4.8 Add `@app_commands.default_permissions(administrator=True)` to ticket admin commands
- [ ] 4.9 Add `@app_commands.default_permissions(moderate_members=True)` to `status`, `modlogs`, `warn`, `unwarn`, `mute`, `unmute`, `kick`, `lock`, `unlock`
- [ ] 4.10 Add `@app_commands.default_permissions(ban_members=True)` to `ban`
- [ ] 4.11 Add prefix DM fallback for admin commands — `ctx.author.send()` with channel fallback
- [ ] 4.12 REFACTOR: Verify all 24 commands classified correctly per ephemeral-standard spec
- [ ] 4.13 Run `uv run pytest` — all tests green, full regression
