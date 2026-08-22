# Design: Voice Moderation Permissions

## Overview

Extend NebulosaBot's moderation layer with a granular per-guild permission matrix, tempban/unban with 30-day warning decay, and a read-only voice observatory. The permission resolver (`can`/`can_check`/`can_member`) centralizes authorization in `bot/utils/checks.py`, riding the existing `{guild_id}:config` cache with Supabase Realtime CDC invalidation. Migration 024 is additive (`permissionMatrix JSONB DEFAULT '{}'` + two partial indexes for decay/expiry scans). The hourly loop in `SentinelCog` is DB-sourced for restart durability — no in-memory timers. The voice listener is strictly read-only: it observes and logs, never kicks/mutes/moves/DMs.

```text
Dashboard write ─→ guild.permissionMatrix ─→ Realtime CDC ─→ invalidate_guild(G)
                                                                        │
can("moderation.ban", ctx) ←── reads matrix from {G}:config cache ←──────┘
  │ DM→deny; admin→True; matrix key present→role intersect;
  │ moderation.* absent→modRoleId fallback; else deny

@tasks.loop(hours=1)
  ├─ decay_warnings()   → get_expired_warns(G) → deactivate + Member.warnings-- (floor 0)
  └─ tempban expiry     → get_expired_tempbans(G) → unban() + deactivate
  (before_loop: wait_until_ready; cog_unload: cancel)

on_voice_state_update(member, before, after)
  ├─ skip bots / both-None
  ├─ _evict_stale (TTL debounce {G}:{member})
  ├─ _classify_transition (join/leave/move/mute/deafen)
  └─ log_voice_event(G, member, transition, before, after) → logChannelId (brand INFO)
  (read-only: no kick/mute/move/DM/channel.send)
```

## Architecture Decisions

| Area | Choice | Alternatives / Tradeoff | Rationale |
|---|---|---|---|
| Matrix storage | JSONB column on `guild` | Separate `guild_permission` table; registry/factory | One column, one read, rides existing config cache + CDC; JSONB queryable for future dashboard editor. |
| `moderation.*` fallback | When matrix key absent, fall back to `modRoleId` | Strict matrix-only (no fallback) | Backward-compatible — existing single-role servers keep working; deny-default only when key present and user lacks role. |
| Admin handling | `ctx.author.guild_permissions.administrator` → implicit True | Matrix must also list admin role | Admins should never be locked out; matches `is_admin()` semantics. |
| Cache strategy | Matrix rides existing `{guild_id}:config` | New `perm_matrix` cache key | No new cache key (cross-guild leak guard); CDC on `guild` already evicts config incl. matrix. |
| Tempban storage | Reuse dead `infraction.expiresAt` column | New `tempban_expires_at` column | Column exists and is nullable; BAN type + non-null `expiresAt` = tempban; partial index makes scan cheap. |
| Decay floor | Service clamps `delta = min(delta, current)` + RPC 009 `GREATEST(warnings, 0)` | Trust RPC only | Defense in depth — service never lets warnings go negative even if RPC changes. |
| Escalation | Exact-equality (`count == threshold`) | `>=` threshold | Fires once per crossing; no re-fire after decay (3→1→2 does NOT re-fire MUTE at 2). |
| Loop source | DB-sourced (scan on each iteration) | In-memory timer per tempban | Restart-durable — tempban survives bot restart; no lost timers. |
| Voice listener | Read-only `on_voice_state_update` | Active moderation (auto-mute) | "Subtle observatory" intent — observe and log, never act. |
| Debounce | Per-member `{guild_id}:{member_id}` TTL dict | Global rate limit | Collapses rapid mute/deafen toggles to ≤1 log; guild-scoped prevents cross-guild interference. |

## Module Structure

### `bot/utils/checks.py` (PR1)

- `PERMISSIONS: frozenset[str]` — 7 permissions: `moderation.warn/mute/kick/ban`, `tickets.manage`, `economy.manage`, `greeting.manage`.
- `_get_guild_service() -> Any` — lazy resolver (test override via `_override` attr; runtime None fallback → deny).
- `_can_core(member, guild_id, permission, config) -> bool` — shared decision logic: DM→deny; admin→True; matrix key present→role intersect; `moderation.*` absent→`modRoleId` fallback; else deny.
- `async def can(permission, ctx) -> bool` — context form (resolves member + guild_id + config from ctx).
- `async def can_member(permission, member, guild_id) -> bool` — listener form (mirrors `can` for non-ctx callers).
- `def can_check(permission)` — decorator mirroring `is_admin()` shape: `commands.check(_prefix)(app_commands.check(_app)(func))`, exposes `.predicate`/`.prefix_predicate`.
- `_is_mod_via_matrix` + `is_mod` shim — `is_mod` now honors `moderation.*` matrix keys; external outcomes unchanged (admin pass, modRoleId pass, deny-default).

### `bot/services/infraction_service.py` (PR2)

- `async def tempban(guild_id, target_id, moderator_id, reason, expires_at) -> Infraction` — insert BAN with `expires_at`; caller (`SentinelCog`) does `member.ban()` + logging.
- `async def unban(guild_id, target_id) -> Infraction | None` — deactivate active BAN; idempotent (None when no active BAN); caller lifts Discord ban.
- `async def decay_warnings(guild_id) -> int` — for each expired WARN: deactivate + `update_member_warnings(delta=-1)` floored at 0 (read current, only decrement if >0). Returns count decayed.
- `check_escalation` unchanged — exact-equality preserved; decay does not trigger re-escalation.

### `bot/core/db/infraction_db.py` (PR2)

- `async def get_expired_warns(guild_id) -> list[Row]` — `type='WARN' AND active AND "createdAt" < NOW() - 30d`; explicit cols; guild-scoped; uses `idx_infraction_warn_decay`.
- `async def get_expired_tempbans(guild_id) -> list[Row]` — `type='BAN' AND active AND "expiresAt" <= NOW() AND "expiresAt" IS NOT NULL`; explicit cols; guild-scoped; uses `idx_infraction_tempban_expiry`.

### `bot/cogs/sentinel.py` (PR1 + PR2)

- PR1: `/ban` `@is_admin()` → `@can_check("moderation.ban")` (preserve `ConfirmCancelView` + `default_permissions(ban_members=True)`).
- PR2: `/tempban @user <duration> <reason>` hybrid — `@can_check("moderation.ban")`, `@default_permissions(ban_members=True)`, `ConfirmCancelView` ephemeral, `parse_duration_optional` guard (None → ephemeral error, no ban), Confirm → `tempban()` + `member.ban()` + permanent action embed. `/unban @user_id` hybrid — `@can_check("moderation.ban")`, active BAN → deactivate + lift + permanent confirm; no active BAN → ephemeral info (idempotent); denied → ephemeral error.
- PR2: `@tasks.loop(hours=1) decay_expiry_loop` — runs `decay_warnings()` for each guild THEN tempban-expiry scan (`get_expired_tempbans` → `unban` + deactivate). `@before_loop` awaits `bot.wait_until_ready()`. `async cog_unload()` cancels loop. Logs via `LoggingService` with brand tokens (no hex).

### `bot/listeners/voice_listener.py` (PR3)

- `VoiceListener(commands.Cog)` with `@commands.Cog.listener() async def on_voice_state_update(member, before, after)`.
- Skip bots + both-None (no channel change).
- `_debounce: dict[str, float]` keyed `f"{guild_id}:{member_id}"` with `_DEBOUNCE_TTL = 2.0`; `_evict_stale()` runs on every event (no unbounded growth).
- `_classify_transition(before, after) -> str | None` — join (before.channel None, after set), leave (before set, after None), move (both set, different), mute/deafen (self_mute/self_deaf diff), else None.
- Config gate via `GuildService.get_config(guild_id)` — `logEnabled` False → silent skip; `logChannelId` null → silent skip.
- Route via `LoggingService.log_voice_event(guild_id, member, transition, before, after)`.
- Read-only: no kick/mute/move/DM/channel.send (enforced by `commands.Cog.listener` + async).

### `bot/services/logging_service.py` (PR3)

- `async def log_voice_event(guild_id, member, transition, before, after)` — resolve log channel via `{guild_id}:config` cache (fallback DB); `_should_log` (logEnabled + logChannelId); embed with `brand.LOG_COLOR` (INFO); transition titles (join/leave/move/mute/deafen) via i18n; channel context; `_send_log` routing; no blocking I/O (async-only).

### `bot/utils/time.py` (PR2)

- `def parse_duration_optional(text) -> int | None` — reuses `_UNIT_TO_SECONDS` / `_DURATION_RE`; returns None on no regex match (NOT 3600); docstring states `timeparse.py` is a separate domain (DB timestamp → datetime, economy).

## Migration 024

```sql
ALTER TABLE guild ADD COLUMN IF NOT EXISTS "permissionMatrix" JSONB NOT NULL DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS idx_infraction_warn_decay ON infraction ("createdAt")
  WHERE type = 'WARN' AND active = true;
CREATE INDEX IF NOT EXISTS idx_infraction_tempban_expiry ON infraction ("expiresAt")
  WHERE type = 'BAN' AND active = true AND "expiresAt" IS NOT NULL;
```

Additive + idempotent (`IF NOT EXISTS` ×3). Existing guild rows get `'{}'::jsonb`. Validate `schema_migrations` before apply (024 not already recorded). Rollback: `DROP INDEX` ×2 + `DROP COLUMN "permissionMatrix"`. Dependencies: 001 (guild, infraction) + 023 (RLS).

## Test Strategy (TDD)

Strict TDD per `test-driven-development` SKILL — RED first (write failing test, watch fail), GREEN (minimal code), REFACTOR (stay green).

- **PR1**: `test_migrations.py` (024 structure/idempotency/partial indexes), `test_guild_service.py` (round-trip + unknown keys + cache ride + bare-key leak guard), `test_checks.py` (can 4.1-4.9, can_check dual, can_member mirror, is_mod shim), `test_sentinel_cog.py` (`/ban` re-gate).
- **PR2**: `test_pr2_expired_scans_red.py` (get_expired_warns/tempbans), `test_pr2_service_red.py` (tempban/unban/decay/floor/escalation/async), `test_pr2_time_optional_red.py` (parse_duration_optional), `test_pr2_sentinel_red.py` (/tempban+/unban+loop).
- **PR3**: `test_pr3_intent_red.py` (intents + portal docs), `test_pr3_logging_red.py` (log_voice_event), `test_pr3_voice_listener_red.py` (5 transitions + config-gate + read-only + debounce).
- **PR4**: `test_pr4_tickets_red.py` (16× can_check), `test_pr4_greetings_red.py` (_admin_guard → can).

## File-by-file Changes

| File | Action | Description |
|---|---|---|
| `migrations/024_permission_matrix_indexes.sql` | Create | Additive JSONB + 2 partial indexes (IF NOT EXISTS). |
| `bot/models/guild.py` | Modify | `permission_matrix` field + camelCase round-trip. |
| `bot/utils/checks.py` | Modify | `PERMISSIONS` + `can`/`can_check`/`can_member` + `is_mod` shim. |
| `bot/utils/time.py` | Modify | `parse_duration_optional` (separate from timeparse.py). |
| `bot/core/db/infraction_db.py` | Modify | `get_expired_warns`/`get_expired_tempbans`. |
| `bot/services/infraction_service.py` | Modify | `tempban`/`unban`/`decay_warnings`. |
| `bot/services/logging_service.py` | Modify | `log_voice_event`. |
| `bot/cogs/sentinel.py` | Modify | `/ban` re-gate, `/tempban`+`/unban`, hourly loop. |
| `bot/cogs/tickets.py` | Modify (PR4) | 16× `@can_check("tickets.manage")`. |
| `bot/cogs/greetings.py` | Modify (PR4) | `_admin_guard` → `can`. |
| `bot/__main__.py` | Modify | `intents.voice_states=True` + portal comment. |
| `bot/listeners/voice_listener.py` | Create | `VoiceListener` cog + debounce. |
| `bot/locales/{en,es}.json` | Modify | tempban/unban/voice keys. |
| `docs/MANUAL.md` | Modify | `/tempban` `/unban` + voice section. |

## Risks

- **High**: Voice States intent not granted in portal — mitigated by docs in `__main__.py` + `MANUAL.md`; bot cannot detect (Q3).
- **Medium**: `increment_member_warnings` RPC floor — service clamps as defense in depth (Q1 resolved: RPC 009 uses `GREATEST`).
- **Medium**: `expiresAt` NULL assumption in `get_infractions` callers — audited in PR2 Phase 2 (Q2 resolved: no caller assumes NULL).
- **Low**: Cross-guild matrix leak — `cache_key(guild_id, entity)` only; test forbids bare key.

## Open Questions Resolved

- **Q1 RPC floor**: RPC 009 `increment_member_warnings` uses `GREATEST(warnings + delta, 0)` — floors at 0. Service also clamps `delta = min(delta, current)` as defense in depth. Resolved by RED test 2.6.
- **Q2 expiresAt NULL audit**: `get_infractions` callers audited in PR2 Phase 2 — no code path assumes `expiresAt IS NULL` for BAN. Column goes live with tempban.
- **Q3 Voice States portal**: Documented in `bot/__main__.py` (prerequisite comment) + `docs/MANUAL.md` (MUST enable Voice States in Discord Developer Portal). Bot cannot detect missing grant — owner action required.
