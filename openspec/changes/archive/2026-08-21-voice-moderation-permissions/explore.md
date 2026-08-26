## Exploration: Voice Moderation Permissions

### Current State

The existing permission model is binary: `is_admin()` (dual-path: `commands.check` + `app_commands.check`) and `is_mod()` (after Cycle 2 fix, dual-path). `modRoleId` is a single guild-configured role — every moderation command (`/warn`, `/mute`, `/kick`, `/ban`, `/lock`, `/unlock`, `/unwarn`, `/unmute`, `/modlogs`) uses the same role. There is no per-permission granularity: a server cannot grant `/warn` to one role and `/ban` to another.

`infraction.expiresAt` is a nullable column that is **dead today** — only WARN/MUTE/KICK/BAN infractions are inserted, none with `expiresAt`. Bans are permanent; there is no tempban, no expiry loop, no warning decay. `Member.warnings` only ever increments (via `increment_member_warnings` RPC) or decrements on `/unwarn`/delete — never decays.

There is **no voice observatory**: `intents.voice_states` is not enabled in `bot/__main__.py`, no `on_voice_state_update` listener exists, and `LoggingService` has no `log_voice_event` method. Voice activity (join/leave/move/mute/deafen) is invisible to operators unless they watch Discord directly.

`GuildConfig` is cached at `{guild_id}:config` and invalidated via Supabase Realtime CDC on `guild` UPDATE. The cache is guild-scoped via `cache_key(guild_id, entity)` — no bare entity strings allowed (cross-guild leak guard).

### Affected Areas

#### Permission surface (binary `modRoleId` only)

**SentinelCog** (`bot/cogs/sentinel.py`): `warn`, `unwarn`, `mute`, `unmute`, `kick`, `ban` (`@is_admin`), `lock`, `unlock`, `modlogs` — 9 commands, all gated by the single `modRoleId` (except `/ban` which is admin-only).

**TicketsCog** (`bot/cogs/tickets.py`): 16 lifecycle commands gated by `@is_mod()`, `delete_category` gated by `@is_admin()`.

**GreetingsCog** (`bot/cogs/greetings.py`): 10 commands gated by body-check `_admin_guard()`.

#### Dead schema columns

- `infraction.expiresAt` (nullable, never written) — ripe for tempban
- No partial index on `WARN` decay or `BAN` expiry — hourly scans would seq-scan

#### Voice (entirely absent)

- `intents.voice_states = False` in `bot/__main__.py`
- No `bot/listeners/voice_listener.py`
- `LoggingService` has no `log_voice_event` method
- No voice i18n keys

### Root Cause Analysis

```python
# Today: single modRoleId gates everything
mod_role_id = guild_config.modRoleId
if user_has_role(author, mod_role_id):
    allow
```

A guild that wants `/warn` available to "Helpers" but `/ban` restricted to "Moderators" has no way to express this — both fall back to the same `modRoleId`. The matrix approach adds a JSONB column `permissionMatrix` keyed by permission name → list of role IDs, with `moderation.*` falling back to `modRoleId` when the key is absent (backward-compatible).

### Approaches

#### A1 — Permission matrix JSONB on guild (RECOMMENDED for permissions)

Add `guild.permissionMatrix JSONB DEFAULT '{}'` + `can(permission, ctx)` resolver. Order: DM→deny; admin→True; matrix key present→role intersect; `moderation.*` absent→fallback `modRoleId`; else deny.

- **Pros**: Granular per-permission control; `moderation.*` fallback preserves existing servers; admin implicit; deny-default; cross-guild isolation via `{guild_id}:config` cache; additive migration (no data loss).
- **Cons**: New column + 2 partial indexes; resolver adds ~45 lines to `checks.py`.
- **Effort**: **Medium** (migration + model + resolver + `/ban` re-gate + tests)

#### B1 — Tempban/unban loop (RECOMMENDED for tempban)

Reuse dead `infraction.expiresAt` column: `tempban()` inserts BAN with `expiresAt`, hourly loop scans `get_expired_tempbans` and unbans.

- **Pros**: Revives dead column; DB-sourced (restart-durable, no in-memory timer); partial index makes scan cheap.
- **Cons**: Column goes "live" — must audit `get_infractions` callers for NULL assumptions.
- **Effort**: **Medium** (DB scans + service + `/tempban`+`/unban` + loop)

#### C1 — 30d warning decay loop (RECOMMENDED for decay)

`decay_warnings()` deactivates 30d-old WARN rows + decrements `Member.warnings` (floored at 0). Same hourly loop as B1.

- **Pros**: Self-cleaning moderation history; `Member.warnings` reflects recent behavior; exact-equality escalation preserved (no re-fire at 2 after 3→1→2).
- **Cons**: Must verify `increment_member_warnings` RPC floors at 0 (Q1); service clamps as defense in depth.
- **Effort**: **Medium** (extends B1 loop)

#### D1 — `on_voice_state_update` listener (RECOMMENDED for voice)

Enable `intents.voice_states` + new `VoiceListener` cog + `log_voice_event` on `LoggingService`. Read-only (no kick/mute/move/DM). Per-member debounce to collapse rapid mute toggles.

- **Pros**: Subtle observatory; reuses `logEnabled`/`logChannelId`; guild-scoped; async-only; read-only by construction.
- **Cons**: Requires guild owner to enable Voice States intent in Discord Developer Portal (bot cannot detect missing grant — Q3); debounce adds state.
- **Effort**: **Medium** (~250 lines: intent + listener + log method + i18n + docs)

### Alternative considered and rejected

- **Permission registry/factory** (Approach B from earlier explore): single source of truth mapping command→level. Over-engineering for current scale; JSONB matrix is simpler and extensible.
- **Discord guild perms as defense-in-depth** (Approach C): require `kick_members`/`ban_members` in addition. Breaks role-only mod servers where the mod role has bot-level perms but not Discord-level.

### Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `increment_member_warnings` RPC does NOT floor at 0 | Med | RED test 2.6 forces the answer; service clamps `delta = min(delta, current)` so warnings never <0 |
| `expiresAt` previously assumed NULL for BAN | Med | Audit `get_infractions` callers in PR2 Phase 2; tempban makes column live |
| Voice States intent not granted in portal | High | Document in `__main__.py` + `MANUAL.md`; bot cannot detect (Q3) |
| Matrix key present + user lacks role → no fallback | Low | Intentional deny-default (spec) |
| Cross-guild matrix leak via shared cache key | Med | `cache_key(guild_id, entity)` only; test forbids bare `perm_matrix` |
| Debounce unbounded growth | Low | TTL eviction (`_evict_stale`) on every event |

### PR Split

Strict TDD per `test-driven-development` SKILL. Stacked-to-main, auto-chain. Total ~950 lines split mandatory (>400 budget):

```
main
 ├─📍PR1 A1 schema+matrix core (≤350) dep: none
 │   ├─PR2 B1+C1 tempban/decay+loop (≤350) dep: PR1
 │   ├─PR3 D1 voice observatory (≤250) dep: PR1
 │   └─PR4 opt matrix adoption (≤300) dep: PR1 [OPTIONAL]
```

PR1 is the root (migration + matrix + resolver + `/ban` re-gate). PR2 and PR3 are independent leaves stacked on PR1. PR4 is optional (matrix additive — `is_mod`/`is_admin` shims keep working if deferred).

### Open Questions (resolve before/as applies)

- **Q1**: `increment_member_warnings` RPC — does it floor `member.warnings` at 0 on negative delta? If not, `decay_warnings` MUST clamp in the service layer. RED test 2.6 forces this answer.
- **Q2**: Confirm no code path assumes `expiresAt IS NULL` for BAN before tempban makes the column live. Audit `get_infractions` callers in PR2 Phase 2.
- **Q3**: `intents.voice_states` portal toggle — bot cannot detect missing grant (documented only). Confirm guild owner action before PR3 ship.

### Ready for Proposal

Yes. Scope is clear, approaches A1+B1+C1+D1 are chosen, PR split is defined, risks and open questions are documented. Strict TDD will drive every behavior (RED→GREEN→REFACTOR). The orchestrator should proceed to proposal → design → specs → tasks → apply (chained PRs).
