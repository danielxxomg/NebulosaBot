# Proposal: Voice Moderation Permissions

## Intent

Turn Sentinel into a subtle voice observatory and complete the moderation permissions story: add a granular per-guild permission matrix, tempban/unban with 30-day warning decay, and a read-only voice listener. Guilds gain fine-grained control over seven moderation/staff permissions via a JSONB matrix on `guild`, with `moderation.*` falling back to the existing single `modRoleId`. Voice activity is observed and logged, never acted on.

## Scope

### In Scope

- **A1 — Permission matrix core**: `guild.permissionMatrix JSONB DEFAULT '{}'` + `GuildConfig.permission_matrix` + `can()`/`can_check()`/`can_member()` resolver in `bot/utils/checks.py` (admin implicit, matrix role grant, `moderation.*` fallback to `modRoleId`, deny-default, cross-guild isolation). Re-gate `/ban` from `@is_admin()` to `@can_check("moderation.ban")` (preserve `ConfirmCancelView` + `default_permissions(ban_members=True)`). Migration 024 additive + idempotent (`IF NOT EXISTS`) with two partial indexes (`idx_infraction_warn_decay`, `idx_infraction_tempban_expiry`).
- **B1 — Tempban + unban**: `InfractionService.tempban()` (insert BAN with `expiresAt`) + `unban()` (idempotent deactivate + lift Discord ban). SentinelCog `/tempban` + `/unban` hybrid commands gated by `@can_check("moderation.ban")` with `ConfirmCancelView`. `parse_duration_optional()` in `bot/utils/time.py` (separate domain from `timeparse.py`).
- **C1 — 30d decay + hourly loop**: `InfractionService.decay_warnings()` deactivates 30-day-old WARN rows and decrements `Member.warnings` floored at 0. `@tasks.loop(hours=1)` in `SentinelCog` runs decay then tempban-expiry scan, `before_loop wait_until_ready`, `cog_unload` cancel, DB-sourced restart durability.
- **D1 — Voice observatory**: `intents.voice_states=True` + new `bot/listeners/voice_listener.py` (`VoiceListener` cog) + `LoggingService.log_voice_event` (join/leave/move/mute/deafen), guild-scoped, async-only, read-only. Per-member `{guild_id}:{member_id}` debounce with TTL eviction. i18n keys + portal docs.
- **Optional PR4 matrix adoption**: `tickets.manage` (16 lifecycle decorators), `greeting.manage` (`_admin_guard`), `economy.manage` assessed N/A (dashboard-only).

### Out of Scope

- Permission registry/factory (Approach B from explore) — future hardening
- Discord guild perms as defense-in-depth (Approach C) — compatibility risk for role-only mod servers
- Dashboard matrix editor UI — separate change
- Acting on voice events (kick/mute/move) — listener is strictly read-only

## Capabilities

### New Capabilities
- `voice-observatory`: read-only voice state observation → log channel

### Modified Capabilities
- `permission-model`: add `can()`/`can_check()`/`can_member()` resolver + 7-permission matrix + admin implicit + `moderation.*` fallback + deny-default + cross-guild isolation; `is_mod` shim honors matrix keys; `/ban` re-gated to `@can_check("moderation.ban")`
- `guild-config`: add `permissionMatrix` JSONB column with `'{}'::jsonb` default; round-trip preserves matrix + other fields; unknown keys tolerated; matrix rides existing config cache (no new cache key)
- `infraction-service`: add `tempban`/`unban`/`decay_warnings`; expired scan DB queries; floor at 0; escalation stays correct after decay; restart durability via DB source of truth
- `sentinel-commands`: add `/tempban` + `/unban` hybrid commands with ephemeral confirm + permanent action; hourly decay→expiry loop with `before_loop`/`cog_unload`
- `ephemeral-standard`: tempban confirmation is ephemeral, action is permanent; unban confirmation is permanent/idempotent info

## Approach

- **A1**: Migration 024 (additive JSONB + 2 partial indexes) → `GuildConfig.permission_matrix` field + camelCase round-trip → `can()`/`can_check()`/`can_member()` resolver (DM→deny, admin→True, matrix key present→role intersect, `moderation.*` absent→modRoleId fallback, else deny) → `is_mod` shim honors matrix → `/ban` decorator swap.
- **B1+C1**: `get_expired_warns`/`get_expired_tempbans` DB scans (explicit cols, guild-scoped) → `InfractionService.tempban/unban/decay_warnings` (floor 0, exact-equality escalation preserved) → `parse_duration_optional` (reuses `_UNIT_TO_SECONDS`, None on no-match) → `/tempban`+`/unban` hybrid → `@tasks.loop(hours=1)` decay→expiry.
- **D1**: `intents.voice_states=True` + portal docs → `log_voice_event` (brand INFO, guild-scoped, async-only) → `VoiceListener` cog with `on_voice_state_update` (skip bots/both-None, debounce `{guild_id}:{member_id}` TTL, `_evict_stale`, `_classify_transition`, read-only).
- **PR4 opt**: swap `tickets.py` 16 `@is_mod()` → `@can_check("tickets.manage")` (preserve `delete_category @is_admin`); rewrite `greetings._admin_guard` to `await can("greeting.manage")`; economy N/A.

## Affected Areas

| Area | Impact |
|------|--------|
| `migrations/024_*.sql` | New (additive JSONB + 2 partial indexes) |
| `bot/models/guild.py` | Modified (`permission_matrix` field + camelCase) |
| `bot/utils/checks.py` | Modified (`PERMISSIONS`, `can`/`can_check`/`can_member`, `is_mod` shim) |
| `bot/utils/time.py` | Modified (`parse_duration_optional`) |
| `bot/core/db/infraction_db.py` | Modified (`get_expired_warns`/`get_expired_tempbans`) |
| `bot/services/infraction_service.py` | Modified (`tempban`/`unban`/`decay_warnings`) |
| `bot/services/logging_service.py` | Modified (`log_voice_event`) |
| `bot/cogs/sentinel.py` | Modified (`/ban` re-gate, `/tempban`+`/unban`, hourly loop) |
| `bot/cogs/tickets.py` | Modified (16 `@can_check("tickets.manage")`) |
| `bot/cogs/greetings.py` | Modified (`_admin_guard` → `can`) |
| `bot/__main__.py` | Modified (`intents.voice_states=True`) |
| `bot/listeners/voice_listener.py` | New |
| `bot/locales/{en,es}.json` | Modified (tempban/unban/voice keys) |
| `docs/MANUAL.md` | Modified |

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `increment_member_warnings` RPC floors below 0 | Med | Service clamps delta (`min(delta, current)`); RPC 009 uses `GREATEST(warnings, 0)` — defense in depth |
| `expiresAt` previously dead for BAN | Med | Audit `get_infractions` callers in PR2 Phase 2; column goes live with tempban, no NULL assumption |
| Voice States intent not granted in portal | High | Documented in `__main__.py` + `MANUAL.md`; bot cannot detect missing grant |
| Matrix key present + user lacks role → no fallback | Low | Intentional deny-default (spec); documented |
| Cross-guild matrix leak | Med | `cache_key(guild_id, entity)` only; test forbids bare `perm_matrix` key |

## Rollback Plan

Migration: `DROP INDEX IF EXISTS idx_infraction_warn_decay; DROP INDEX IF EXISTS idx_infraction_tempban_expiry; ALTER TABLE guild DROP COLUMN IF EXISTS "permissionMatrix"`. Revert `guild.py` `permission_matrix`, `checks.py` `can*`/`PERMISSIONS`/`is_mod` shim, `sentinel.py` `/ban`→`@is_admin`. PR2: cancel loop, remove `/tempban`/`/unban` + `get_expired_*` + `tempban/unban/decay_warnings` + `parse_duration_optional`; `expiresAt` rows remain harmless. PR3: remove `intents.voice_states` + `voice_listener` + `log_voice_event` + voice i18n. PR4: revert 16 decorators + `_admin_guard`. Matrix additive — `is_mod`/`is_admin` shims keep working if PR4 deferred.

## Dependencies

- Migration 024 additive on `guild` + `infraction` (deps 001, 023 RLS)
- RPC 009 `increment_member_warnings` floors via `GREATEST` (service clamps as defense in depth)
- Existing `{guild_id}:config` cache (matrix rides it — no new cache key)
- `intents.voice_states` portal grant by guild owner (documented only)

## Success Criteria

- [ ] 7 permissions resolvable via `can()` (admin implicit, matrix grant, `moderation.*` fallback, deny-default, DM deny, cross-guild isolation)
- [ ] `/ban` re-gated to `@can_check("moderation.ban")` with `ConfirmCancelView` preserved
- [ ] `/tempban @user 24h spam` inserts BAN with `expiresAt` + bans member
- [ ] `/unban @user` deactivates BAN + lifts Discord ban (idempotent)
- [ ] `decay_warnings()` deactivates 30d WARNs, floors `Member.warnings` at 0
- [ ] Hourly loop runs decay→expiry; `before_loop`/`cog_unload`; DB-sourced restart durability
- [ ] `intents.voice_states=True`; VoiceListener logs join/leave/move/mute/deafen, read-only, guild-scoped, debounced
- [ ] Migration 024 live (schema_migrations 024/024); partial indexes present
- [ ] `uv run pytest --cov=bot --cov-fail-under=75` passes (≥2342 tests, ≥84.80% pre-PR4)
- [ ] ruff/ty/tach green on every slice

## Chained-PR Plan

```
main
 ├─📍PR1 A1 schema+matrix core (≤350) dep: none
 │   ├─PR2 B1+C1 tempban/decay+loop (≤350) dep: PR1
 │   ├─PR3 D1 voice observatory (≤250) dep: PR1
 │   └─PR4 opt matrix adoption (≤300) dep: PR1 [OPTIONAL]
```

Stacked-to-main, auto-chain. Total ~950 production lines split mandatory (>400 budget); each slice ≤60-min review. Strict TDD (RED→GREEN→REFACTOR) per `test-driven-development` SKILL — no production code before a failing test.
