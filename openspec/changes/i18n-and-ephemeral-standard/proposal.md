# Proposal: i18n and Ephemeral Standard

## Intent

Hardcoded English despite `language` in GuildConfig. Admin commands pollute channels. Prefix errors leak visibly. Missing `@app_commands.default_permissions()`. No "," prefix.

## Scope

### In Scope
- `bot/core/i18n.py` + `bot/locales/es.json` + `bot/locales/en.json` — `t(guild_id, key, **kwargs) -> str`
- Migrate ~100+ strings across 7 cogs + 8 services + embeds.py
- Ephemeral standard: admin/personal=ephemeral, mod actions=permanent
- DM fallback for admin prefix commands
- `@app_commands.default_permissions()` on admin commands
- `/status` → `@is_mod()`, `on_command_error` → DM prefix errors
- "," global alternate prefix

### Out of Scope
- /setup wizard, ticket seeding, unique constraints, transcripts, close reason, confirmations

## Capabilities

### New Capabilities
- `i18n-system`: Locale loader, t(), dot-notation keys, es/en JSON, fallback chain
- `ephemeral-standard`: Classification for all 24 commands, prefix DM fallback

### Modified Capabilities
- `bot-core`: Prefix list, error handler DM, /status @is_mod()
- `ticket-commands`: @app_commands.default_permissions on 7 commands; ephemeral fixes
- `sentinel-commands`: /modlogs ephemeral; default_permissions on mod commands
- `core-commands`: /status ephemeral + @is_mod(); /ping ephemeral

## Approach

Chained PRs:
1. i18n core + locale files + embeds.py + Core/Utility/Ocio
2. Tickets cog + service migration
3. Sentinel + Stellar + Greetings + services
4. Ephemeral + permissions + error DM + "," prefix

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/core/i18n.py` | New | Locale loader + t() |
| `bot/locales/*.json` | New | es/en translations |
| `bot/utils/embeds.py` | Modified | Wire t() |
| `bot/cogs/*.py` (7) | Modified | Strings + ephemeral + perms |
| `bot/services/*.py` (8) | Modified | String migration |
| `bot/bot.py` | Modified | Prefix, error DM, i18n init |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Merge conflicts | High | Chained PRs |
| ephemeral=True ignored prefix | High | DM fallback |
| Missing locale keys | Med | Fallback es, log |
| Persistent view labels | Med | Generic labels |

## Rollback Plan

Each PR independently revertible. i18n→hardcoded. Ephemeral→remove. Prefix→single string.

## Dependencies

discord.py 2.7.1 (in use), GuildConfig.language (exists)

## Success Criteria

- [ ] t() correct per guild language + interpolation
- [ ] Zero hardcoded English in embeds
- [ ] Admin ephemeral (slash) or DM (prefix)
- [ ] Permission hints on admin commands
- [ ] Prefix errors DM'd
- [ ] ,ping works alongside nb!ping
- [ ] Tests pass

## Proposal Question Round

Resolved: 4 chained PRs, "," = global hardcoded, flat dot-notation, DM for polluted admin commands only.

Assumptions: t() sync (dict lookup). Generic button labels. es = fallback locale.
