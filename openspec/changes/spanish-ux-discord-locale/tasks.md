# Tasks: Spanish UX + Discord Locale

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 600–850 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | auto-forecast |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | LocaleTranslator + locale keys + setup_hook wiring + tests | PR 1 | Foundation: translator class, JSON keys, bot.py integration, sync validation. ~250 lines. |
| 2 | View/paginator localization (confirm, paginator, ticket panel defaults) + tests | PR 2 | Runtime UI: guild_id threading, t() labels, panel None defaults. ~250 lines. Depends on PR 1 keys. |
| 3 | Cog decorators + error handler + manual docs + integration tests | PR 3 | All 8 cogs localized, bot-core error handler, MANUAL.md fix. ~250 lines. Depends on PR 1 translator. |

## Phase 1: Foundation — LocaleTranslator + Locale Keys

- [x] 1.1 RED: write `tests/test_i18n.py` tests for `LocaleTranslator` — Spanish client returns es string, English client returns en string, unknown locale returns Spanish default, no DB calls
- [x] 1.2 GREEN: add `LocaleTranslator(Translator)` in `bot/core/i18n.py` — translate() reads locale key from `string.extras`, maps Discord locale variants to `es`/`en`, returns in-memory string or `None`
- [x] 1.3 RED: write tests for `validate_slash_localizations()` — verifies all hybrid app commands have description_localizations for es/en
- [x] 1.4 GREEN: add `validate_slash_localizations()` in `bot/core/i18n.py` — iterates tree commands, checks/assigns localizations from registry
- [x] 1.5 Add slash metadata registry dict in `bot/core/i18n.py` — maps qualified command name + param to locale keys
- [x] 1.6 RED: write tests verifying `es.json` and `en.json` contain all `slash.descriptions.*` and `slash.describes.*` keys (49 descriptions + 30 describes)
- [x] 1.7 GREEN: add `slash.descriptions.*` keys to `bot/locales/es.json` and `bot/locales/en.json` for all 49 hybrid command descriptions
- [x] 1.8 GREEN: add `slash.describes.*` keys to both locale files for all 30 `@app_commands.describe` parameters
- [x] 1.9 RED: write `tests/test_i18n.py` tests for translator registration order — `set_translator()` called before `tree.sync()`, `validate_slash_localizations` called before sync
- [x] 1.10 GREEN: wire `set_translator(LocaleTranslator())` and `validate_slash_localizations()` in `bot/bot.py` `setup_hook()` before `tree.sync()`
- [x] 1.11 GREEN: wire same validation in `/sync` command handler before manual sync
- [x] 1.12 Run `uv run pytest tests/test_i18n.py tests/test_bot.py` — all pass

## Phase 2: Runtime UI — Views, Paginator, Ticket Panel

- [x] 2.1 RED: write `tests/test_confirm_view.py` tests — Spanish guild shows Spanish Confirm/Cancel labels, English guild shows English labels
- [x] 2.2 GREEN: add `guild_id` param to `ConfirmCancelView.__init__()` in `bot/views/confirmation.py`, resolve button labels via `t(guild_id, "buttons.confirm")` / `t(guild_id, "buttons.cancel")`
- [x] 2.3 RED: write `tests/test_paginator.py` tests — `EmbedPaginator` accepts `guild_id`, localizes Previous/Next/Stop labels, preserves timeout behavior
- [x] 2.4 GREEN: add `guild_id` param to `EmbedPaginator.__init__()` in `bot/utils/paginator.py`, resolve labels via `t()`
- [x] 2.5 Add missing runtime label keys (`buttons.confirm`, `buttons.cancel`, `paginator.previous`, `paginator.next`, `paginator.stop`, `tickets.panel.default_title`, `tickets.panel.default_description`, `errors.unexpected_title`, `errors.unexpected_message`) to both locale files
- [x] 2.6 RED: write tests for `/ticket_panel` — args default `None`, `deploy_ticket_panel` resolves defaults via `t()` when None, explicit overrides pass through
- [x] 2.7 GREEN: change `/ticket_panel` command signature in `bot/cogs/tickets.py` — `title: Optional[str] = None`, `description_text: Optional[str] = None`; update `deploy_ticket_panel` to resolve via `t(guild_id)` when None
- [x] 2.8 GREEN: update self-heal panel deploy in `bot/views/tickets.py` to pass `guild_id` for default resolution
- [x] 2.9 Run `uv run pytest tests/test_confirm_view.py tests/test_paginator.py tests/test_ticket_views.py tests/test_tickets_cog.py` — all pass

## Phase 3: Cog Localization + Error Handler + Docs

- [x] 3.1 RED: write tests verifying all 8 cog hybrid commands have `locale_str` descriptions with `key="slash.descriptions.*"` and `@app_commands.describe` params use `locale_str` with `key="slash.describes.*"`
- [x] 3.2 GREEN: update `bot/cogs/core.py` — replace description strings with `locale_str("...", key="slash.descriptions.*")` on all hybrid commands/groups/subcommands; update `@app_commands.describe` params
- [x] 3.3 GREEN: repeat 3.2 for `bot/cogs/sentinel.py`
- [x] 3.4 GREEN: repeat 3.2 for `bot/cogs/tickets.py`
- [x] 3.5 GREEN: repeat 3.2 for `bot/cogs/stellar.py`, `bot/cogs/utility.py`, `bot/cogs/ocio.py`, `bot/cogs/greetings.py`, `bot/cogs/setup.py`
- [x] 3.6 GREEN: update `bot/cogs/core.py` help command — pass `guild_id` to `EmbedPaginator`
- [x] 3.7 RED: write tests for `on_app_command_error` — Spanish guild error embed uses `t()`, English guild uses `t()`, guild_id extracted from interaction
- [x] 3.8 GREEN: update `on_app_command_error` in `bot/bot.py` — resolve guild_id from interaction, use `t(guild_id, "errors.unexpected_title")` and `t(guild_id, "errors.unexpected_message")`
- [x] 3.9 GREEN: fix `docs/MANUAL.md` — change default language reference from `en` to `es`, add note about client-localized slash descriptions
- [x] 3.10 Run `uv run pytest` — all tests pass, coverage ≥ 70%
