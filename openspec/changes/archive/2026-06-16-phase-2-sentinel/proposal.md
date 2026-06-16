# Proposal: Phase 2 — Sentinel (Moderation)

## Intent

Add a moderation suite — warnings with auto-escalation, mute/kick/ban, channel lock, modlogs, and action logging — using the existing Phase 1 schema. No migration needed.

## Scope

### In Scope
- `InfractionService` — CRUD, warning counter, auto-escalation
- `SentinelCog` — 9 hybrid commands (warn, unwarn, mute, unmute, kick, ban, modlogs, lock, unlock)
- `bot/utils/time.py` — Duration parser ("1h", "30m", "2d")
- Mod action logging to `logChannelId`
- DB query methods on existing `Database`
- Unit tests for `InfractionService`

### Out of Scope
- Auto-moderation (anti-spam, raid) — Phase 5
- Configurable escalation — hardcoded for now
- Infraction caching — low-frequency

## Capabilities

### New Capabilities
- `infraction-service`: CRUD, warning count via `Member.warnings`, auto-escalation (3 warns → mute 1h, 5 warns → kick)
- `sentinel-commands`: 9 hybrid commands with `@is_mod()` / `@is_admin()` guards
- `time-parsing`: Duration string → seconds
- `mod-logging`: Action embeds to `logChannelId`

### Modified Capabilities
- `permission-model`: `@is_admin()` guard for `/ban`

## Approach

- **Mute**: `member.timeout()` — native, auto-expires, zero setup
- **Warnings**: `Member.warnings` denormalized counter, updated with infraction CRUD
- **Escalation**: `count == 3` → mute 1h, `count == 5` → kick, checked after WARN persist
- **Lock**: Overwrite `send_messages` for `@everyone`, defaults to `ctx.channel`
- **No caching** for infractions

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/services/infraction_service.py` | New | CRUD + escalation |
| `bot/cogs/sentinel.py` | New | 9 hybrid commands |
| `bot/utils/time.py` | New | Duration parser |
| `bot/core/database.py` | Modified | 8 query methods |
| `bot/bot.py` | Modified | Register service, load cog |
| `tests/test_infraction_service.py` | New | Service tests |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Missing `moderate_members` perm | Low | Check perms, error embed |
| `warnings` counter drift | Low | Future sync command |
| `discord.Forbidden` on kick/ban | Med | Catch, send error embed |

## Rollback Plan

Remove `SentinelCog` from `load_extension()` and `InfractionService` registration. No migration to revert.

## Dependencies

- Phase 1 complete
- discord.py v2.x with `member.timeout()`

## Success Criteria

- [ ] All 9 commands work with correct permission guards
- [ ] Auto-escalation at 3 warns (mute) and 5 warns (kick)
- [ ] Mod actions logged to `logChannelId`
- [ ] `InfractionService` tests pass
- [ ] Zero new migrations

## Decisions (from Proposal Question Round)

| Question | Answer |
|----------|--------|
| Default mute | 1h default if no duration specified |
| Ban deletion | Optional `delete_days` (0–7), default 0 |
| Modlogs | Paginated (5/page) + filters (type, after date) |
| Escalation notification | Public in channel + DM to user |
| Lock scope | Optional channel argument, defaults to current |
