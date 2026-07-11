# Proposal: Spanish UX + Discord Locale

## Intent

NebulosaBot defaults to Spanish yet leaks English UX on Hispanic servers: slash descriptions, Confirm/Cancel, paginator buttons, default ticket panel copy, and the unexpected-error handler are hardcoded English. Slash metadata is not localized at all. `MANUAL.md` wrongly claims default `en`.

## Scope

### In Scope
- discord.py `Translator` + `locale_str`/`description_localizations` — slash descriptions/parameters follow user **Discord client locale** (es default, en via localizations).
- Command **names stay English**; only descriptions localize.
- Fix hardcoded English runtime UI via `t(guild_id, key)`: Confirm/Cancel, `EmbedPaginator`, panel defaults, `on_app_command_error`.
- Thread `guild_id` into `EmbedPaginator` and `ConfirmCancelView`.
- Self-heal panel deploy uses guild-language defaults.
- Fix `docs/MANUAL.md` default `en` → `es`.

### Out of Scope
- `LoggingService` staff audit log strings (staff-facing; later slice).
- Locales beyond `es`/`en`.

## Capabilities

### New Capabilities
- `slash-locale-translator`: discord.py `Translator` subclass + `locale_str`/`description_localizations` for hybrid command descriptions and `@app_commands.describe(...)` parameters, driven by locale files.

### Modified Capabilities
- `i18n-system`: Add slash-metadata locale keys to `es.json`/`en.json`; `t()` contract unchanged.
- `confirm-dialog`: `ConfirmCancelView` resolves button labels via `t(guild_id, key)`.
- `ticket-views`: Panel defaults become `t()` keys; decorator defaults Spanish-first; self-heal passes guild_id.
- `core-commands`: `/help` paginator localizes navigation buttons per guild.
- `utility-commands`: `EmbedPaginator` accepts `guild_id`, localizes Previous/Next/Stop via `t()`.
- `bot-core`: `on_app_command_error` resolves guild, uses `t()`.
- `docs-manual`: Fix default-language references `en` → `es`.

## Approach

Hybrid (locked Approach 4): `Translator` for slash metadata (client locale); `t()` for runtime UI (guild language). For hybrid_command friction (`description=` accepts `str` not `locale_str`), use a post-registration hook injecting `description_localizations` before `tree.sync()`. Fallback path documented in design.

## Affected Areas

- `bot/core/i18n.py` — Translator class, slash locale key plumbing
- `bot/bot.py` — `set_translator()`, error handler localization
- `bot/cogs/*.py` (8) — 49 descriptions + 30 describes localize
- `bot/views/confirmation.py` — `t()` labels, guild_id param
- `bot/views/tickets.py` — panel defaults via `t()`, Spanish-first defaults
- `bot/utils/paginator.py` — guild_id param, `t()` labels
- `bot/locales/{es,en}.json` — slash.description / slash.describe keys
- `docs/MANUAL.md` — fix default `en` → `es`

## Risks

- **hybrid_command + `locale_str` friction** (Med) — post-registration hook fallback; document in design.
- **Paginator guild_id threading breaks callers** (Low) — both callers have guild context.
- **Tests asserting English descriptions break** (Med) — update; strict TDD writes new locale tests first.
- **Prefix help shows Spanish to all** (Low) — accepted per Spanish-first decision.

## Rollback Plan

Revert the branch. No DB migrations — code/locale/docs only. `t()` contract unchanged. Remove `Translator` from `setup_hook` to restore prior slash metadata.

## Dependencies

- discord.py v2.x `Translator` API (already installed).

## Success Criteria

- [ ] Slash descriptions render in user's Discord client locale (es/en).
- [ ] Confirm/Cancel, paginator, panel defaults, error embed render in guild language via `t()`.
- [ ] Command names stay English.
- [ ] `MANUAL.md` default says `es`.
- [ ] Budget risk: Medium (8 cogs + views + locales + docs).
