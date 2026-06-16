# Design: Phase 2 — Sentinel (Moderation)

## Technical Approach

Extend the Phase 1 skeleton with a moderation layer: `InfractionService` for business logic, `SentinelCog` for 9 hybrid commands, and `bot/utils/time.py` for duration parsing. No new migrations — the existing schema already has `infraction` and `member` tables with all required columns. Follows the established service/cog/DB split.

## Architecture Decisions

| # | Decision | Options | Tradeoff | Choice |
|---|----------|---------|----------|--------|
| 1 | Mute mechanism | `member.timeout()` vs role-based mute | timeout: native, auto-expires, 28d max / role: persistent, complex setup | **`member.timeout()`** — zero guild setup, auto-expires natively |
| 2 | Warning counter | Derive `COUNT(infractions)` vs `Member.warnings` | COUNT: always accurate, extra query / Denorm: fast, can drift | **`Member.warnings`** — already in schema, mod actions are sequential so drift risk is negligible |
| 3 | Escalation trigger | Before vs after persist | Before: no orphan record / After: audit trail even if Discord action fails | **After persist** — infraction record is the audit trail regardless of Discord API outcome |
| 4 | Escalation idempotency | `count >= threshold` vs `count == threshold` | >=: fires every time / ==: fires once per threshold | **`count == threshold`** — prevents repeated mute/kick on every subsequent warn |
| 5 | Lock mechanism | Permission overwrite vs channel slowmode | Overwrite: true lock / slowmode: just throttled | **`set_permissions(@everyone, send_messages=False)`** — clear lock/unlock semantics |
| 6 | `/ban` permission | `@is_mod()` vs `@is_admin()` | mod: consistent with other cmds / admin: bans are irreversible | **`@is_admin()`** — destructive action requires highest non-owner permission |
| 7 | Infraction caching | TTL cache vs no cache | Cache: faster reads / No cache: simpler, mod actions are low-frequency | **No cache** — a few mod actions per day don't justify invalidation complexity |
| 8 | `warnings` atomicity | Supabase RPC vs read-compute-upsert | RPC: truly atomic / RCU: race condition, simpler | **Read-compute-upsert** — mod actions are never concurrent on the same user; RPC if it becomes a problem |

## Data Flow

### Warn + Auto-Escalation Sequence

```
User runs /warn <member> <reason>
         │
         ▼
   SentinelCog.warn()
   @is_mod() check
         │
         ▼
   InfractionService.create_infraction(WARN)
         │
         ├──→ Database.insert_infraction()
         ├──→ Database.update_member_warnings(+1)
         │
         ▼
   InfractionService.check_escalation(guild_id, target_id)
         │
         ├── count == 3 → member.timeout(1h) + create_infraction(MUTE)
         ├── count == 5 → member.kick() + create_infraction(KICK)
         └── else → no action
         │
         ▼
   _log_action() → logChannelId embed
   ctx.send() → success/error embed + DM escalation notice
```

### Lock/Unlock Flow

```
/modlock [channel]
         │
         ▼
   SentinelCog.lock()
   @is_mod() check
         │
         ▼
   channel = arg or ctx.channel
   channel.set_permissions(guild.default_role, send_messages=False)
         │
         ▼
   _log_action() → success embed in channel
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `bot/services/infraction_service.py` | Create | CRUD, warning counter sync, auto-escalation logic |
| `bot/cogs/sentinel.py` | Create | 9 hybrid commands with permission guards and mod logging |
| `bot/utils/time.py` | Create | Regex-based duration parser ("1h30m" → seconds) |
| `tests/test_infraction_service.py` | Create | Unit tests for service: CRUD, escalation, unwarn |
| `bot/core/database.py` | Modify | Add 8 infraction/member query methods |
| `bot/bot.py` | Modify | Register `InfractionService`, load `sentinel` cog |

## Interfaces / Contracts

### EscalationAction

```python
@dataclass
class EscalationAction:
    action: str       # "MUTE" | "KICK"
    duration: int     # seconds (for MUTE), 0 for KICK
    threshold: int    # warning count that triggered it
```

### InfractionService Public API

```python
class InfractionService:
    async def create_infraction(self, guild_id: str, target_id: str,
        moderator_id: str, type: str, reason: str,
        expires_at: datetime | None = None) -> Infraction

    async def get_infractions(self, guild_id: str,
        target_id: str) -> list[Infraction]

    async def count_active_warnings(self, guild_id: str,
        target_id: str) -> int

    async def deactivate_last_warning(self, guild_id: str,
        target_id: str) -> Infraction | None

    async def check_escalation(self, guild_id: str, target_id: str,
        member: discord.Member) -> EscalationAction | None
```

### Database Methods Added

```python
async def insert_infraction(self, infraction: Infraction) -> dict
async def get_infractions(self, guild_id: str, target_id: str) -> list[dict]
async def count_active_warnings(self, guild_id: str, target_id: str) -> int
async def get_last_active_warning(self, guild_id: str, target_id: str) -> dict | None
async def deactivate_infraction(self, infraction_id: str) -> None
async def get_member(self, guild_id: str, user_id: str) -> dict | None
async def upsert_member(self, member: Member) -> None
async def update_member_warnings(self, guild_id: str, user_id: str, delta: int) -> None
```

### Duration Parser

```python
def parse_duration(text: str) -> int | None
    # "1h" → 3600, "30m" → 1800, "1h30m" → 5400, "2d" → 172800
    # Returns None if unparseable
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | `InfractionService` CRUD | Mock `Database` methods, verify infraction creation, warning increment/decrement |
| Unit | Auto-escalation | Mock DB + `discord.Member`, assert timeout at 3, kick at 5, nothing at 2/4 |
| Unit | `parse_duration()` | Pure function — test valid inputs, edge cases, invalid strings |
| Unit | `unwarn` flow | Verify `deactivate_last_warning` decrements warnings, returns None when no active warns |
| Integration | DB query methods | Test against real Supabase (optional, requires test DB) |

## Migration / Rollout

No migration required. The `infraction` and `member` tables with all needed columns already exist from migration 001.

## Open Questions

- [ ] Should `/modlogs` filters (type, after) be slash-command options or paginator buttons?
