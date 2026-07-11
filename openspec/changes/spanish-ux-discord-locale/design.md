# Design: Spanish UX + Discord Locale

## Technical Approach

Use two deliberately separate localization paths. `discord.app_commands.Translator` supplies slash command and parameter metadata according to each user's Discord client locale; the existing cache-backed `t(guild_id, key)` supplies runtime views and embeds according to the guild language. Spanish is the base metadata string and English is emitted as an `en` localization. Command names remain unchanged.

The installed discord.py 2.7.1 supports `locale_str` in `hybrid_command` and `app_commands.describe`; its generated `HybridAppCommand` retains those locale objects. This is the primary path, registered before `tree.sync()`.

## Architecture Decisions

| Option | Tradeoff | Decision |
|---|---|---|
| Translator for metadata; `t()` for runtime | Two consumers of the locale files | Chosen: client locale and guild locale are different inputs. |
| Translate command names | Would break stable English command identifiers | Rejected: names remain English; descriptions/parameters only localize. |
| Decorator `locale_str` | Hybrid decorators historically had typing/version friction | Chosen on 2.7.1; a pre-sync registry validator provides the fallback below. |

`i18n.py` will add a `LocaleTranslator` that reads a locale key carried in `locale_str.extras`, maps Discord Spanish variants to `es` and English variants to `en`, and returns `None` for other locales. It must not alter `t()` or guild-language state.

Each cog will declare Spanish `locale_str(message, key="slash.…")` values for its hybrid command/group/subcommand descriptions and `@app_commands.describe` parameters. Both JSON files receive identical `slash` key structure, with Spanish and English values.

**Hybrid fallback:** after all cogs are loaded but before `set_translator()` and every `tree.sync()`, validate a registry keyed by qualified command and parameter. If a hybrid-generated app command did not retain its locale object, the hook assigns the registry's `locale_str` to its underlying app-command description/parameter localization field, then verifies the translated payload. This is version-guarded compatibility code; failure to attach a required entry logs and aborts sync rather than silently publishing English-only metadata. On the supported version it is a no-op validation path.

## Data Flow

```
es.json / en.json
      │
      ├─ locale_str(key) → LocaleTranslator → tree.sync() → Discord client locale
      └─ t(guild_id, key) → views / embeds → guild configured language
```

`setup_hook()` loads locale JSON, loads cogs, validates metadata registration, awaits `tree.set_translator(LocaleTranslator())`, then syncs. The `/sync` command must run the same validator before syncing. Runtime callers pass the current guild ID to `ConfirmCancelView` and `EmbedPaginator`.

### Panel default resolution

`/ticket_panel` command arguments `title` and `description_text` MUST default to `None` (not English strings). When `None`, `deploy_ticket_panel` resolves the default via `t(guild_id, "tickets.panel.default_title")` and `t(guild_id, "tickets.panel.default_description")`. When the admin provides explicit values, those are passed through as-is. This ensures both admin-initiated and self-heal deploys use localized defaults without hardcoded English leaking through. The same pattern applies to any future command that accepts optional display text with a localized fallback.

## File Changes

| File | Action | Description |
|---|---|---|
| `bot/core/i18n.py` | Modify | Translator, locale-key lookup, metadata registry/validation. |
| `bot/bot.py` | Modify | Register translator before startup sync; validate manual sync; localize app errors. |
| `bot/cogs/{core,sentinel,tickets,stellar,utility,ocio,greetings,setup}.py` | Modify | Mark all slash descriptions and parameters with keyed Spanish `locale_str`; pass paginator guild ID. |
| `bot/views/confirmation.py` | Modify | Set Confirm/Cancel labels from existing `t()` keys during initialization. |
| `bot/utils/paginator.py` | Modify | Require/store guild ID and localize all navigation labels. |
| `bot/views/tickets.py` | Modify | Use locale keys/Spanish-first decorator defaults; resolve panel defaults per guild. |
| `bot/locales/{es,en}.json` | Modify | Add matching `slash` and missing runtime-label keys. |
| `docs/MANUAL.md` | Modify | State `es` is default and document client-localized slash descriptions. |
| `tests/test_{i18n,bot,confirm_view,paginator,manual}.py` and cog i18n tests | Modify | Cover payload, runtime labels, sync wiring, and documentation. |

## Interfaces / Contracts

```python
class LocaleTranslator(app_commands.Translator):
    async def translate(
        self, string: app_commands.locale_str, locale: discord.Locale,
        context: app_commands.TranslationContextTypes,
    ) -> str | None: ...

def validate_slash_localizations(tree: app_commands.CommandTree[...]) -> None: ...
```

`EmbedPaginator(pages, *, guild_id: str | int | None, ...)` preserves its navigation and custom-ID behavior. Panel `title` and `description_text` become optional overrides; `None` selects the guild-localized defaults. The `/ticket_panel` command signature MUST use `Optional[str] = None` for both `title` and `description_text`; passing hardcoded English defaults as argument defaults is forbidden — it defeats localization by always overriding the `t()` resolution path.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Translator key/locale mapping, fallback validator, view labels | Mock locale state and inspect app-command translated payloads. |
| Integration | Startup/manual sync ordering and every registry entry | Mock tree sync; assert translator is awaited before sync and metadata payload contains es/en descriptions only. |
| E2E | Discord rendering | Not automated; verify in Spanish and English Discord clients after deployment. |

## Migration / Rollout

No migration required. Re-sync commands after deploy; Discord propagation timing applies. Roll back by reverting the change or removing the translator registration.

## Open Questions

None.
