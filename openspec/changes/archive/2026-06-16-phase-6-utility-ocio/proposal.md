# Proposal: Phase 6 — Utility + Ocio Cogs

## Intent

Add utility and fun commands. Users need quick member/server info and casual interactions (dice, banana game). No existing cog covers these — standalone, no-service commands.

## Scope

### In Scope
- `UtilityCog` with `/avatar`, `/serverinfo`, `/userinfo` hybrid commands
- `OcioCog` with `/dados`, `/banana` hybrid commands
- Banana image asset (`assets/images/banana.png`)
- Unit tests for both cogs
- `load_extension()` calls in `bot/bot.py`

### Out of Scope
- Service layer (no DB, cache, or external API needed)
- Permission-gated variants of these commands
- Localization / multi-language embed text

## Capabilities

### New Capabilities
- `utility-commands`: Avatar display, server info summary, and user info lookup as hybrid commands
- `ocio-commands`: Dice roll with configurable sides and banana measurement game with image attachment

### Modified Capabilities
None

## Approach

Two separate cogs following the one-cog-per-module pattern. No service layer — embed construction and `random.randint()`. Use `info_embed()` for simple results, raw `discord.Embed(COLOR_INFO)` for multi-field layouts. Avatar via `display_avatar.url`. Roles truncated at 20. Dice: `app_commands.Range[2, 100]`, default 6. Banana attaches local `discord.File`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/cogs/utility.py` | New | UtilityCog — avatar, serverinfo, userinfo |
| `bot/cogs/ocio.py` | New | OcioCog — dados, banana |
| `bot/bot.py` | Modified | Add two `load_extension()` calls in `setup_hook()` |
| `assets/images/banana.png` | New | Static banana image for `/banana` |
| `tests/test_utility_cog.py` | New | Unit tests for utility commands |
| `tests/test_ocio_cog.py` | New | Unit tests for ocio commands |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Missing banana image asset | Low | Provide placeholder PNG; command degrades gracefully if file missing |
| `/serverinfo` in DM context | Low | Early return with error embed when `ctx.guild` is None |
| Large role lists in `/userinfo` | Medium | Truncate at 20 roles, append "and N more" |

## Rollback Plan

Remove both `load_extension()` lines from `bot/bot.py`, delete `bot/cogs/utility.py`, `bot/cogs/ocio.py`, `assets/images/banana.png`, and both test files. No DB or config changes to revert.

## Dependencies

- Banana image asset must be sourced or created before `/banana` can ship

## Success Criteria

- [ ] All five commands respond correctly via slash and prefix
- [ ] `/avatar` returns embed with thumbnail for self and mentioned member
- [ ] `/serverinfo` shows all guild fields; returns error in DMs
- [ ] `/userinfo` truncates roles at 20 with suffix
- [ ] `/dados` returns result within `[1, sides]` for sides in `[2, 100]`
- [ ] `/banana` returns embed with image attachment and measurement in `[2, 30]` cm
- [ ] All tests pass: `python -m pytest -v`
