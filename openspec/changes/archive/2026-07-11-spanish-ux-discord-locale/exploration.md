# Exploration: Spanish UX + Discord Locale

## Current State

### i18n System (`bot/core/i18n.py`)
- **Runtime translations**: Fully operational `t(guild_id, key, **kwargs)` with dot-notation keys, `es` fallback, and placeholder interpolation.
- **Locale files**: `bot/locales/es.json` (517 lines) and `bot/locales/en.json` (517 lines) — comprehensive coverage for all cogs, views, embeds, errors, and confirmation dialogs.
- **Default locale**: `es` (Spanish) — confirmed in code (`_DEFAULT_LOCALE = "es"`).
- **Guild wiring**: `GuildService` publishes `GuildConfig.language` to `i18n.set_guild_language()` on every config load/save/join/backfill.
- **Slash command metadata**: All `description=` and `@app_commands.describe(...)` strings are **hardcoded English** — NOT localized via `t()`. This is by design per the existing comment in sentinel.py: "Slash command descriptions are Discord UI metadata, not runtime responses. They remain in English; t() localizes runtime responses only."
- **discord.py Translator**: **NOT used anywhere**. Zero instances of `Translator`, `locale_str`, `set_translator`, or `name_localizations`/`description_localizations` in the codebase.

### Hardcoded English in UI Components

**Confirmation buttons** (`bot/views/confirmation.py`):
- `label="Confirm"` (line 78) — hardcoded English
- `label="Cancel"` (line 95) — hardcoded English

**Ticket panel buttons** (`bot/views/tickets.py`):
- `label="Open Ticket"` (line 364) — default, overridden at runtime via `t()` in `__init__` and callback
- `label="Claim"` (line 434) — default, overridden at runtime
- `label="Close"` (line 558) — default, overridden at runtime
- `label="Edit Category"` (line 650) — default, overridden at runtime
- Note: These buttons DO resolve labels via `t()` at interaction time, but the decorator defaults are English

**Paginator buttons** (`bot/utils/paginator.py`):
- `label="◀ Previous"` (line 65) — hardcoded English
- `label="Next ▶"` (line 83) — hardcoded English
- `label="⏹ Stop"` (line 100) — hardcoded English
- No `guild_id` context available — paginator doesn't know which guild it's serving

**Default ticket panel text** (`bot/views/tickets.py`):
- `DEFAULT_TICKET_PANEL_TITLE = "Support Tickets"` (line 31)
- `DEFAULT_TICKET_PANEL_DESCRIPTION = "Click the button below..."` (lines 32-35)
- Used by `/ticket_panel` command defaults AND startup self-heal

**Bot error handler** (`bot/bot.py`):
- `on_app_command_error`: `error_embed("Unexpected Error", str(error))` (line 357) — hardcoded English, no guild context

**Logging service** (`bot/services/logging_service.py`):
- All embed titles/field names hardcoded English: "🛡️ Moderation: {action}", "Target", "Moderator", "Reason", "Before", "After", "Author", "Content", "Added", "Removed", "Roles", etc.
- Footer text: `"Message ID: {id}"`, `"Member #{count}"`
- These are staff-facing audit logs, not user-facing — lower priority

### MANUAL.md Documentation Error
- Line 42: `language` parameter says `(por defecto: en)` — **WRONG**. Code default is `es`.
- Line 87: `language: en` — respuestas en inglés (por defecto si no se configura) — **WRONG**.

## Affected Areas

| File | Impact | What Needs to Change |
|------|--------|---------------------|
| `bot/cogs/*.py` (8 cogs) | 49 hardcoded `description=` strings | Add `description_localizations` via Translator or manual dict |
| `bot/cogs/*.py` | 30 `@app_commands.describe(...)` strings | Add `parameter_description` localizations |
| `bot/views/confirmation.py` | 2 hardcoded button labels | Localize Confirm/Cancel labels |
| `bot/utils/paginator.py` | 3 hardcoded button labels | Localize Previous/Next/Stop labels |
| `bot/views/tickets.py` | 4 default button labels + 2 panel defaults | Already resolved at runtime; defaults still English |
| `bot/bot.py` | 1 hardcoded error string | Use `t()` with resolved guild_id from interaction |
| `bot/services/logging_service.py` | ~20 hardcoded English strings | Staff-facing — lower priority, optional |
| `docs/MANUAL.md` | 2 incorrect default language claims | Fix to say `es` |
| `bot/locales/es.json` | Needs new keys for slash metadata | Add slash description keys |
| `bot/locales/en.json` | Needs new keys for slash metadata | Add slash description keys |

## Approaches

### Approach 1: discord.py Translator + `locale_str` (Full Localization)

Implement a custom `Translator` subclass registered via `bot.tree.set_translator()`. Use `locale_str` objects for all `description=`, `@app_commands.describe(...)`, and button labels. Discord shows localized strings based on the **user's client locale** (not guild config).

- **Pros**:
  - Discord-native: descriptions auto-localize per user client locale
  - `name_localizations` and `description_localizations` populated automatically in sync payload
  - Covers command descriptions, parameter descriptions, and choice names
  - One Translator class handles all 24+ commands
- **Cons**:
  - Translator is async — must be registered before `tree.sync()`
  - Hybrid commands: `@commands.hybrid_command(description=...)` accepts `str`, not `locale_str` — need to use `@app_commands.command(description=locale_str(...))` pattern or set localizations on the command object post-registration
  - Button labels in Views are NOT covered by Translator (different system) — need manual `t()` for those
  - Adds complexity: new Translator class, new locale keys for every slash description
  - discord.py Translator iterates ALL locales for every string — performance cost on sync
- **Effort**: **High** — requires Translator class, locale key additions for ~80 strings (describes + descriptions), testing the sync payload

### Approach 2: Manual `description_localizations` Dict on Commands

After command registration, walk `bot.tree` and set `cmd.extras` or manually inject `name_localizations`/`description_localizations` dicts from locale files. No Translator class needed.

- **Pros**:
  - Simpler than Translator — no async translation callbacks
  - Direct control over what gets localized
  - Can use existing `t()` keys or new dedicated keys
- **Cons**:
  - Fragile: must run after every `tree.sync()` and after every cog load
  - Hybrid commands don't expose `description_localizations` directly — must manipulate the underlying `app_commands.Command`
  - Still need new locale keys for all descriptions
  - Doesn't cover `@app_commands.describe(...)` parameter descriptions
- **Effort**: **Medium** — post-registration manipulation, new locale keys

### Approach 3: Spanish-First Defaults + Keep English Metadata (Minimal Change)

Change the **default `description=`** strings to Spanish. Keep command NAMES in English. For `@app_commands.describe(...)`, change parameter descriptions to Spanish. Add English `description_localizations` so English-client users see English. This matches the product decision: "Default message string for Discord should be Spanish-first."

For runtime UI: localize Confirm/Cancel buttons, paginator buttons, default panel text, and the bot error handler via `t()`.

- **Pros**:
  - Minimal new infrastructure — uses existing `t()` for runtime UI
  - Spanish-first defaults match the target audience (Hispanic servers)
  - English users still see English via `description_localizations`
  - No Translator class needed if we set localizations manually or use a lightweight post-sync hook
  - Fixes the hardcoded English UX gaps (buttons, paginator, error handler)
- **Cons**:
  - Still need a mechanism for `description_localizations` on hybrid commands
  - 49 command descriptions + 30 parameter descriptions = ~79 strings to change
  - Paginator needs guild_id threading
- **Effort**: **Medium** — change defaults to Spanish, add English localizations, fix runtime UI gaps

### Approach 4: Hybrid — Translator for Slash Metadata + `t()` for Runtime UI

Combine Approach 1 (Translator for slash command/parameter descriptions) with Approach 3 (fix runtime UI via `t()`). Translator handles Discord-localized metadata; `t()` handles guild-config-dependent runtime strings.

- **Pros**:
  - Best of both worlds: Discord-native locale for slash metadata, guild-config for runtime
  - Clean separation: Translator = Discord client locale; `t()` = guild language config
  - Covers all gaps: slash descriptions, parameter descriptions, buttons, paginator, errors
- **Cons**:
  - Most complex — Translator class + runtime UI fixes
  - Two localization systems to maintain (Translator locale keys + t() locale keys)
  - Translator keys must stay in sync with t() keys
- **Effort**: **High** — full Translator + all runtime fixes

## Recommendation

**Approach 3 (Spanish-First Defaults + Runtime UI Fixes)** is the pragmatic choice, with one enhancement: add a **lightweight post-sync hook** that walks the command tree and sets `description_localizations` for English from locale files.

Rationale:
1. The target audience is Hispanic servers — Spanish defaults make sense.
2. The Translator system is powerful but overkill for a bot with 24 commands and known locales (only `es`/`en`). The maintenance overhead of a full Translator class + separate locale keys doesn't justify itself.
3. The real UX pain is **runtime UI**: Confirm/Cancel buttons, paginator, default panel text, and the bot error handler. These are what users actually see and interact with.
4. For slash metadata, a post-sync hook that injects `description_localizations` from a flat dict in locale files is simpler than a full Translator.

### Implementation Sketch

1. **Locale files**: Add `slash.descriptions` and `slash.describes` sections to `es.json`/`en.json`.
2. **Command defaults**: Change all `description=` to Spanish strings.
3. **Post-sync hook**: In `setup_hook()`, after `tree.sync()`, walk commands and set `description_localizations` for English.
4. **Runtime UI fixes**:
   - `ConfirmCancelView`: accept `guild_id`, use `t()` for button labels
   - `EmbedPaginator`: accept `guild_id`, use `t()` for button labels (requires threading guild_id from callers)
   - `DEFAULT_TICKET_PANEL_TITLE/DESCRIPTION`: change to `t()` keys, pass guild_id in self-heal
   - `on_app_command_error`: resolve guild from interaction, use `t()`
5. **MANUAL.md**: Fix incorrect default language claims.

## Risks

- **Hybrid command `description=` accepts `str`**: Changing defaults to Spanish means prefix help (`/help`) shows Spanish descriptions for ALL users, not just Spanish-client users. This is acceptable per product decision (default Spanish-first) but English prefix users will see Spanish command descriptions in help.
- **Paginator guild_id threading**: `EmbedPaginator` is used by `CoreCog.help_command` and `SentinelCog.modlogs` — both have guild context available but the paginator doesn't currently receive it. Threading `guild_id` through requires changing the paginator constructor.
- **Self-heal panel re-deploy**: `_validate_single_panel` calls `deploy_ticket_panel` without guild_id-aware defaults. Need to pass guild_id so the re-deployed panel uses the correct language.
- **Test impact**: Existing `test_i18n.py`, `test_tickets_i18n.py`, `test_sentinel_i18n.py`, etc. test `t()` behavior — they should not break. Tests that assert specific English command descriptions WILL need updating.
- **Logging service**: Hardcoded English in `LoggingService` is staff-facing (audit logs). Lower priority but should be noted as known debt.

## Ready for Proposal

**Yes** — the exploration is complete. Key decisions needed from the user:

1. Confirm Approach 3 (Spanish-first defaults + runtime UI fixes) or choose another approach.
2. Confirm whether `LoggingService` audit log strings should be localized in this change or deferred.
3. Confirm whether the post-sync hook for `description_localizations` is acceptable vs. a full Translator.
