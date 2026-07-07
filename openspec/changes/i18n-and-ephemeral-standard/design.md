# Design: i18n and Ephemeral Standard

## Technical Approach

Add a synchronous i18n layer backed by startup-loaded JSON locale dictionaries and an in-memory guild-language map maintained by `GuildService`. Migrate cogs/services to call `t(guild_id, key, **kwargs)` before building existing `discord.Embed` responses. Standardize hybrid command visibility with `ctx.send(..., ephemeral=...)` for slash invocations, and explicit DM fallback for prefix-only admin/error responses because prefix messages cannot be truly ephemeral.

## Architecture Decisions

| Topic | Choice | Tradeoff / rationale |
|------|--------|----------------------|
| i18n architecture | `bot/core/i18n.py` module with module-level locale cache and guild-language map | Sync lookup satisfies spec; `GuildService` already owns cache-first `GuildConfig.language`. |
| Locale format | Nested JSON in `bot/locales/es.json` and `en.json`, addressed by dot keys | Human-editable and matches `commands.ping.response` spec without flattening files. |
| `t()` signature | `t(guild_id: str | int | None, key: str, **kwargs: object) -> str` | Keeps command code small; `None`/missing language falls back to Spanish. |
| Ephemeral strategy | Admin/personal slash responses use `ephemeral=True`; mod actions/fun stay public | Matches proposal and existing `StellarCog.daily/coins/rank` pattern, but leaderboard/daily visibility must be corrected per spec. |
| DM fallback | Prefix admin responses and `NebulosaBot.on_command_error` try `ctx.author.send(embed=...)`, then channel fallback | Discord prefix commands have no ephemeral channel response; fallback is minimal visible error. |
| Prefix list | `_build_prefix_callable().get_prefix()` returns `[config.prefix or "nb!", ","]` | discord.py supports multiple prefixes via list return from command prefix callable. |
| `default_permissions` | Add `@app_commands.default_permissions(...)` beside existing `@is_mod()` / `@is_admin()` | Decorator is a Discord UI hint, not authorization; checks remain source of truth. |
| Migration strategy | Replace strings by slice, not all at once | Reduces conflicts across 7 cogs and 8 services. |

## Data Flow

```text
setup_hook ──→ i18n.load_locales(bot/locales)
GuildService.get_config/save_config/on_guild_join/ensure_guild_exists
        └──→ i18n.set_guild_language(guild_id, GuildConfig.language)

t(guild_id, key, **kwargs)
  └─ guild_id → language map → locale dict → key lookup
       → fallback es → interpolation → string | raw key
```

Missing files/keys/placeholders log warnings and never raise into command handlers.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `bot/core/i18n.py` | Create | `load_locales`, `set_guild_language`, `t`, fallback/interpolation helpers. |
| `bot/locales/es.json`, `bot/locales/en.json` | Create | Spanish fallback and English locale strings for commands, errors, embeds, logs, cards. |
| `bot/bot.py` | Modify | Call `load_locales()` in `setup_hook`; change `_build_prefix_callable().get_prefix()` to return configured prefix plus `,`; update `on_command_error` DM fallback. |
| `bot/services/guild_service.py` | Modify | Publish `GuildConfig.language` to i18n map after `get_config`, `save_config`, `on_guild_join`, and startup backfill. |
| `bot/utils/embeds.py` | Modify | Keep `error_embed`, `success_embed`, `info_embed`, `warning_embed`; localize footer/default common strings via optional `guild_id` or caller-provided translated text. |
| `bot/cogs/core.py` | Modify | Localize `ping`, `status`, `help`, `sync`; make `/ping` and `/status` ephemeral; add `@is_mod()` and `default_permissions(moderate_members=True)` to `status`; keep `sync` admin. |
| `bot/cogs/tickets.py` | Modify | Localize panel/views/category/subticket strings; admin commands ephemeral; add `default_permissions(administrator=True)` for configured admin commands. |
| `bot/cogs/sentinel.py` | Modify | Localize moderation/modlogs strings; keep warn/unwarn/mute/unmute/kick/ban/lock/unlock public; make `modlogs` ephemeral; add permission hints. |
| `bot/cogs/stellar.py`, `greetings.py`, `utility.py`, `ocio.py` | Modify | Localize user-facing strings; preserve current command roles; correct fun/personal visibility per spec. |
| `bot/services/{economy,greeting,infraction,logging,ticket,transcript,image}_service.py` | Modify | Migrate user-facing generated strings only; preserve business logic and async/threading boundaries. |

## Interfaces / Contracts

```python
load_locales(locales_dir: Path | None = None) -> None
set_guild_language(guild_id: str | int, language: str) -> None
t(guild_id: str | int | None, key: str, **kwargs: object) -> str
```

Locale JSON uses nested objects:

```json
{"commands": {"ping": {"response": "Pong! {latency} ms"}}}
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `t()` Spanish, English, missing key fallback, raw-key fallback, interpolation, missing placeholder warning | New `tests/test_i18n.py`. |
| Unit | prefix callable returns `[config.prefix, ","]` and fallback list | Extend `tests/test_bot.py`. |
| Unit | app-command errors ephemeral; prefix errors DM then channel fallback | Mock `Interaction`, `Context.author.send`, `discord.HTTPException`. |
| Unit | slash visibility and `default_permissions` on Core/Tickets/Sentinel commands | Extend cog tests by inspecting `ctx.send` kwargs and command metadata. |
| Integration | migrated command paths still build embeds and services remain cache-first | Existing `uv run pytest` suite. |

## Migration / Rollout

No database migration required. Deliver as 4 chained PRs:
1. i18n core + locale files + `embeds.py` + Core/Utility/Ocio.
2. Tickets cog + ticket/transcript service migration.
3. Sentinel + Stellar + Greetings + remaining services.
4. Ephemeral standard, `default_permissions`, prefix error DM, and `,` prefix.

## Open Questions

- None.
