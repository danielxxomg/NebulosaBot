# Exploration: Phase 2 — Sentinel (Moderation Module)

## Current State

Phase 1 (Foundation) is complete. The bot has a working skeleton with:

- **Bot lifecycle**: `NebulosaBot` with `setup_hook()`, hybrid prefix, cog loading, global error handlers
- **Infrastructure**: `Database` (Supabase wrapper with `get_guild`/`upsert_guild`), `TTLCache` (dict-based, per-guild TTL), `NebulosaContext` (custom context with service accessors)
- **Models**: `GuildConfig`, `Member`, `Infraction`, `Ticket` — all dataclasses with `from_db_row()` and `to_db_dict()` methods
- **Services**: `GuildService` (cache-first guild config CRUD)
- **Cogs**: `CoreCog` (ping, status, help, sync) — demonstrates hybrid command pattern
- **Utils**: `is_mod()` / `is_admin()` decorators in `checks.py`, embed helpers in `embeds.py`
- **Schema**: Migration 001 with all 5 tables including `infraction` and `member` (with `warnings` column)
- **Tests**: `conftest.py` with Discord mocks, tests for cache, guild_service, and checks

### What Already Exists for Moderation

| Component | Status | Location |
|-----------|--------|----------|
| `Infraction` dataclass | ✅ Complete — has `from_db_row()`, `to_db_dict()`, all fields | `bot/models/infraction.py` |
| `member.warnings` column | ✅ In DB schema and model | `migrations/001_initial_schema.sql`, `bot/models/member.py` |
| `GuildConfig.mod_role_id` | ✅ Exists, used by `is_mod()` | `bot/models/guild.py` |
| `GuildConfig.log_channel_id` | ✅ Exists, not yet used | `bot/models/guild.py` |
| `is_mod()` / `is_admin()` | ✅ Implemented and tested | `bot/utils/checks.py` |
| Embed helpers | ✅ `error_embed`, `success_embed`, `info_embed`, `warning_embed` | `bot/utils/embeds.py` |
| DB infraction methods | ❌ Not implemented — `Database` only has guild methods | `bot/core/database.py` |
| Infraction service | ❌ Does not exist | — |
| Sentinel cog | ❌ Does not exist | — |
| Mod action logging | ❌ Does not exist | — |

---

## Affected Areas

### New Files to Create
- `bot/services/infraction_service.py` — Infraction CRUD + auto-escalation logic
- `bot/cogs/sentinel.py` — Hybrid moderation commands
- `tests/test_infraction_service.py` — Unit tests for the service
- `tests/test_sentinel.py` — Unit tests for the cog (optional, cog tests are heavier)

### Existing Files to Modify
- `bot/core/database.py` — Add infraction query methods (`insert_infraction`, `get_infractions`, `count_active_warnings`, `deactivate_infraction`, `update_member_warnings`)
- `bot/bot.py` — Register `InfractionService` in `setup_hook()`, load `sentinel` cog
- `bot/models/__init__.py` — Export `Infraction` if not already
- `bot/services/__init__.py` — Export `InfractionService`

### Files Read-Only (no changes needed)
- `bot/models/infraction.py` — Already complete, no changes needed
- `bot/models/member.py` — Already has `warnings` field
- `bot/utils/checks.py` — `is_mod()` already works
- `bot/utils/embeds.py` — Existing helpers are sufficient
- `migrations/001_initial_schema.sql` — Schema already has all needed tables/columns

---

## Component Analysis

### 1. Infraction Service (`InfractionService`)

**Purpose**: Business logic for infraction CRUD, active warning counting, and auto-escalation.

**Public API needed**:
- `create_infraction(guild_id, target_id, moderator_id, type, reason, expires_at=None) -> Infraction`
- `get_infractions(guild_id, target_id) -> list[Infraction]`
- `count_active_warnings(guild_id, target_id) -> int`
- `deactivate_last_warning(guild_id, target_id) -> Infraction | None` (for unwarn)
- `check_escalation(guild_id, target_id, member: discord.Member) -> EscalationAction | None`

**Escalation result type**:
```python
@dataclass
class EscalationAction:
    action: str        # "MUTE" | "KICK"
    duration: int      # seconds (for MUTE), 0 for KICK
    threshold: int     # warning count that triggered it
```

**Cache strategy**: No caching for infractions in Phase 2. Moderation actions are low-frequency (a few per day per guild). The cost of a DB query per mod action is negligible. Cache invalidation complexity is not worth it here.

### 2. Auto-Escalation Logic

**Approach**: Hardcoded thresholds in `InfractionService`, called after `create_infraction()` when type is `WARN`.

```
WARN created → count active warnings for target
  if count >= 5 → auto-kick
  if count >= 3 → auto-mute 1h
  otherwise → no escalation
```

**Key design decision**: Escalation runs AFTER the infraction is persisted. If the Discord action (kick/mute) fails, the infraction record still exists. This is correct — the mod action was attempted, and the record is the audit trail.

**Escalation is idempotent per threshold**: If a user has exactly 3 warnings and gets a 4th, no new escalation fires (only fires AT 3 and AT 5). Implementation: check `count == threshold`, not `count >= threshold`.

### 3. Mute Implementation

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **`member.timeout()`** | Native discord.py, auto-expires, no role management, simple | Max 28 days, requires `moderate_members` permission | Low |
| **Role-based mute** | Works per-channel, persistent across re-joins | Requires managing a Muted role, permission overwrites on every channel, complex setup | High |

**Recommendation**: Use `member.timeout()`. It's the modern Discord approach, auto-expires (matches `expires_at` on Infraction), and requires zero guild setup. The 28-day limit is not a concern for Phase 2 (default mute is 1h).

**Implementation**: `await member.timeout(duration, reason=reason)` where `duration = timedelta(seconds=...)`. To unmute: `await member.timeout(None, reason=reason)`.

### 4. Lock/Unlock Channel

**Pattern**: Overwrite `send_messages` permission for `@everyone` (the default role).

```python
# Lock
await channel.set_permissions(guild.default_role, send_messages=False)

# Unlock — restore to default (None = inherit from category/server)
await channel.set_permissions(guild.default_role, send_messages=None)
```

**Edge case**: If the channel already had a custom `send_messages` overwrite before locking, unlocking with `None` will reset it. This is acceptable for Phase 2 — document the behavior. A future phase could save/restore original overwrites.

**Default channel**: If no channel argument is provided, use `ctx.channel` (the channel where the command was invoked).

### 5. Modlogs (`/modlogs <member>`)

**Query**: `SELECT * FROM infraction WHERE "guildId" = ? AND "targetId" = ? ORDER BY "createdAt" DESC`

**Pagination**: Use the `_HelpPaginator` pattern from `CoreCog` — a `discord.ui.View` with prev/next buttons. For Phase 2, show 5 infractions per page.

**Embed format**: Each infraction as a field with type emoji, reason, moderator, date, and active status.

### 6. Mod Action Logging

**Pattern**: After a successful mod action, send an embed to the guild's `logChannelId`.

```python
async def _log_action(self, ctx, action: str, target: discord.Member, reason: str, **extra):
    config = ctx.guild_config
    if not config or not config.log_channel_id or not config.log_enabled:
        return
    channel = ctx.guild.get_channel(int(config.log_channel_id))
    if channel is None:
        return
    embed = info_embed(f"🛡️ {action}", ...)
    await channel.send(embed=embed)
```

**Helper location**: Put this as a method on `SentinelCog` (private helper). If logging grows in Phase 5 (audit listener), extract to a shared utility.

### 7. Member.warnings — Source of Truth vs. Denormalized Counter

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **Derive from `COUNT(infractions)`** | Always accurate, single source of truth | Requires a DB query for every escalation check, slightly slower | Low |
| **Keep `Member.warnings` counter** | Fast lookup, already in schema, no extra query | Can drift if not updated atomically, needs increment/decrement logic | Low |

**Recommendation**: Use `Member.warnings` as the fast counter for escalation checks. It's already in the schema and model. The `InfractionService` updates it atomically alongside infraction CRUD:

- `create_infraction(WARN)` → INSERT infraction + `UPDATE member SET warnings = warnings + 1`
- `deactivate_last_warning()` → UPDATE infraction SET active=false + `UPDATE member SET warnings = warnings - 1`
- `count_active_warnings()` → `SELECT warnings FROM member WHERE guildId=? AND userId=?`

The `infraction` table remains the detailed audit trail. `member.warnings` is the quick counter.

**Risk mitigation**: If drift occurs (e.g., manual DB edit), add a `/sync_warnings` admin command in a future phase to recount from infractions.

---

## Database Methods Needed

New methods on `bot/core/database.py`:

```python
async def insert_infraction(self, infraction: Infraction) -> dict:
    """Insert a new infraction row. Returns the inserted row."""

async def get_infractions(self, guild_id: str, target_id: str) -> list[dict]:
    """Fetch all infractions for a member, ordered by createdAt DESC."""

async def count_active_warnings(self, guild_id: str, target_id: str) -> int:
    """Count active WARN infractions for a member."""

async def get_last_active_warning(self, guild_id: str, target_id: str) -> dict | None:
    """Fetch the most recent active WARN infraction (for unwarn)."""

async def deactivate_infraction(self, infraction_id: str) -> None:
    """Set active=false on an infraction by ID."""

async def get_member(self, guild_id: str, user_id: str) -> dict | None:
    """Fetch a member row."""

async def upsert_member(self, member: Member) -> None:
    """Insert or update a member row."""

async def update_member_warnings(self, guild_id: str, user_id: str, delta: int) -> None:
    """Increment/decrement the warnings counter atomically."""
```

**Note on `update_member_warnings`**: Supabase-py doesn't support atomic `INCREMENT` natively. Two options:
1. Read current value → compute new value → upsert (race condition risk, but low for mod actions)
2. Use Supabase RPC (Postgres function) for atomic increment

**Recommendation for Phase 2**: Option 1 (read-compute-upsert). Mod actions are not concurrent on the same user. Add RPC-based atomic increment if this becomes a problem.

---

## Sentinel Cog Command Map

| Command | Type | Permission | Discord API | Notes |
|---------|------|-----------|-------------|-------|
| `/warn <member> <reason>` | hybrid | `@is_mod()` | `InfractionService.create_infraction()` + escalation | Defers for escalation |
| `/unwarn <member>` | hybrid | `@is_mod()` | `InfractionService.deactivate_last_warning()` | Removes last active warn |
| `/mute <member> <duration> <reason>` | hybrid | `@is_mod()` | `member.timeout()` + `create_infraction(MUTE)` | Duration parsed from string |
| `/unmute <member>` | hybrid | `@is_mod()` | `member.timeout(None)` | Removes timeout |
| `/kick <member> <reason>` | hybrid | `@is_mod()` | `member.kick()` + `create_infraction(KICK)` | Member must be in guild |
| `/ban <member> <reason>` | hybrid | `@is_admin()` | `guild.ban()` + `create_infraction(BAN)` | Admin-only (destructive) |
| `/modlogs <member>` | hybrid | `@is_mod()` | `InfractionService.get_infractions()` | Paginated embed |
| `/lock [channel]` | hybrid | `@is_mod()` | `channel.set_permissions()` | Defaults to current channel |
| `/unlock [channel]` | hybrid | `@is_mod()` | `channel.set_permissions()` | Defaults to current channel |

**Duration parsing**: For `/mute`, accept a human-readable duration string (e.g., "1h", "30m", "1d"). Implement a small `parse_duration()` helper in `bot/utils/time.py` (new file).

**`/ban` is admin-only**: Bans are irreversible and destructive. Only `@is_admin()` should be able to ban, not just `@is_mod()`.

---

## Bot Registration Changes

In `bot/bot.py` `setup_hook()`:

```python
# After GuildService init:
self.infraction_service = InfractionService(db=self.db, cache=self.cache)

# Load sentinel cog:
await self.load_extension("bot.cogs.sentinel")
```

The `InfractionService` needs `db` and optionally `cache` (for future use). It does NOT need `mod_role_cache` — that's specific to `GuildService`.

---

## Recommendation

Proceed with the following implementation order:

1. **Database methods** — Add all infraction/member query methods to `Database`
2. **InfractionService** — Business logic, escalation, warning counter management
3. **Duration parser** — Small utility for mute duration strings
4. **SentinelCog** — All 9 hybrid commands with `@is_mod()` / `@is_admin()` guards
5. **Mod action logging** — Private helper on SentinelCog, sends to `logChannelId`
6. **Tests** — `test_infraction_service.py` covering CRUD, escalation, unwarn

**Key decisions**:
- `member.timeout()` for mute (not role-based)
- `Member.warnings` as fast counter (not derived from COUNT)
- Hardcoded escalation thresholds (3=mute 1h, 5=kick)
- No infraction caching (low-frequency operations)
- `/ban` is admin-only, everything else is mod-level

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| `member.timeout()` fails if bot lacks `moderate_members` permission | Mute/kick commands fail mid-flow | Check bot permissions before action, return clear error embed |
| `Member.warnings` drifts from actual active infraction count | Escalation fires at wrong threshold | Document the risk; add `/sync_warnings` admin command in future phase |
| Supabase read-compute-upsert race on `warnings` counter | Two simultaneous warns could lose one increment | Accept for Phase 2 (mod actions are sequential in practice); use RPC atomics later |
| `/lock` overwrites existing channel permissions | Unlocking resets custom `send_messages` overwrites | Document behavior; save/restore original overwrites in future phase |
| `on_app_command_error` doesn't handle `CheckFailure` from `@is_mod()` gracefully | Users see raw error instead of "permission denied" embed | Add `CheckFailure` handler in SentinelCog's `cog_app_command_error` or in global handler |
| `discord.Forbidden` when bot can't kick/ban (role hierarchy) | Command fails with unhandled exception | Catch `discord.Forbidden`, send "I don't have permission" embed |

---

## Ready for Proposal

**Yes.** The exploration is complete. All components are well-defined, the data model already supports the feature (no migration needed), and the implementation path is clear. The orchestrator should tell the user:

> "Phase 2 exploration is done. No new migration needed — the schema from Phase 1 already has everything. We'll build an `InfractionService` with auto-escalation (3 warns = mute 1h, 5 warns = kick), a `SentinelCog` with 9 hybrid commands, and mod action logging. Key decisions: `member.timeout()` for mute, `Member.warnings` as fast counter, `/ban` is admin-only. Ready to proceed to proposal?"
