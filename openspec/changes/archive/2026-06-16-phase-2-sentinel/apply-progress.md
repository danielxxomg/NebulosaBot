# Apply Progress: Phase 2 — Sentinel

**Status**: `success` (17/17 tasks complete across Phases 1-6)
**Date**: 2026-06-16

## Completed Tasks (Slice 1 — PR 1 Foundation)

### Phase 1: Time Parser
- [x] 1.1 `bot/utils/time.py` — `parse_duration(s: str) -> int`
- [x] 1.2 `tests/test_time.py` — 10 parametrized tests

### Phase 2: Database Methods
- [x] 2.1 `insert_infraction`, `get_infractions`, `get_active_warnings`, `deactivate_infraction` in `bot/core/database.py`
- [x] 2.2 `get_member`, `update_member_warnings` in `bot/core/database.py`

### Phase 3: InfractionService
- [x] 3.1 `bot/services/infraction_service.py` — `EscalationAction` dataclass + `InfractionService`
- [x] 3.2 `warn()` method — insert + increment warnings + check escalation
- [x] 3.3 `unwarn()`, `get_modlogs()` methods
- [x] 3.4 `check_escalation()` — count==3→MUTE, count==5→KICK

### Phase 4: Tests
- [x] 4.1 `tests/test_infraction_service.py` — 11 tests
- [x] 4.2 Escalation thresholds parametrized (2/3/4/5)
- [x] 4.3 Unwarn: with warnings + empty case

## Completed Tasks (Slice 2 — PR 2 Cog + Wiring)

### Phase 5: SentinelCog
- [x] 5.1 `bot/cogs/sentinel.py` created — `SentinelCog(commands.Cog)` with `_log_action()`, `_validate_target()`, `_handle_mod_error()` helpers and `_ModlogsPaginator` view.
- [x] 5.2 `/warn` + `/unwarn` hybrid commands with `@is_mod()`. Warn calls `InfractionService.warn()` → checks escalation → auto-mute (3 warnings) / auto-kick (5 warnings). Creates MUTE/KICK infractions for auto-escalation audit trail.
- [x] 5.3 `/mute` + `/unmute` hybrid commands with `@is_mod()`. Mute accepts optional `duration` string (default `"1h"`) parsed via `parse_duration()`. Creates MUTE infraction. Unmute calls `member.timeout(None)`.
- [x] 5.4 `/kick` (`@is_mod()`) + `/ban` (`@is_admin()`) hybrid commands. Both create infractions (KICK/BAN). Ban accepts optional `delete_days` (clamped 0–7, default 0).
- [x] 5.5 `/lock` + `/unlock` hybrid commands with `@is_mod()`. Optional `channel` arg defaults to `ctx.channel`. Sets `send_messages` permission overwrite on `guild.default_role`. Direct error handling (not via `_handle_mod_error` — channel target not a Member).
- [x] 5.6 `/modlogs` hybrid command with `@is_mod()`. Paginated embeds (5/page via `_ModlogsPaginator`), optional `type` and `after` filters. Shows type emoji, moderator mention, reason, date, revoked status.

### Phase 6: Wiring
- [x] 6.1 `bot/bot.py` — added `infraction_service` to `__slots__`, docstring, `__init__`, and `setup_hook()`. Instantiated `InfractionService(db=self.db)` after GuildService init.
- [x] 6.2 `bot/bot.py` — `await self.load_extension("bot.cogs.sentinel")` added after CoreCog load.

## Files Changed
| File | Action | Lines |
|------|--------|-------|
| `bot/utils/time.py` | Created (Slice 1) | 48 |
| `tests/test_time.py` | Created (Slice 1) | 40 |
| `bot/core/database.py` | Modified (Slice 1) | +170 |
| `bot/services/infraction_service.py` | Created (Slice 1) | 161 |
| `tests/test_infraction_service.py` | Created (Slice 1) | 228 |
| `bot/cogs/sentinel.py` | **Created (Slice 2)** | **901** |
| `bot/bot.py` | Modified (Slice 1) → **Modified (Slice 2)** | +16 |

## Test Results
- 47/47 tests pass (0 regressions)

## Deviations from Design
1. `parse_duration` returns `int` (not `int | None`) — returns 3600 for invalid input per orchestrator instructions, diverging from design.md which specified `int | None` return. (Slice 1)
2. DB method signatures simplified — `insert_infraction` takes individual params instead of `Infraction` object. (Slice 1)
3. Service method names: `warn()`, `unwarn()`, `get_modlogs()` instead of design's `create_infraction()`, `deactivate_last_warning()`, `get_infractions()`. (Slice 1)
4. Cog uses `bot.db.insert_infraction()` directly for non-WARN infractions (MUTE, KICK, BAN from direct commands and auto-escalation) — InfractionService only handles WARN lifecycle. (Slice 2)
5. Lock/unlock error handling done inline (not via `_handle_mod_error`) because the target is a channel, not a Member. (Slice 2)
6. `_log_action` uses the moderator as both `target` and `moderator` for lock/unlock log entries — channels aren't Members in the Discord model. (Slice 2)
7. Tasks.md numbering updated to reflect actual method names (`InfractionService.warn()`, not `create_infraction()`). (Slice 2)

## Issues Found
None.
