# Design: Phase 4 — Stellar (Economy)

## Technical Approach

Add a guild economy system on top of the existing Member table (which already has `xp`, `level`, `coins`, `lastDaily`, `lastXpGain` columns). A new `economy_config` table (user decision) stores per-guild tunable parameters. `EconomyService` handles all business logic; `ImageService` wraps Pillow for rank cards. `StellarCog` hosts both the `on_message` XP listener and 5 hybrid commands, following the `TicketsCog` pattern.

## Architecture Decisions

| Decision | Option | Tradeoff | Choice |
|----------|--------|----------|--------|
| Economy config storage | Dedicated `economy_config` table vs columns on `guild` | Clean separation + extensibility vs extra query | **Dedicated table** (user decision) |
| XP listener placement | Inside `StellarCog` vs separate `listeners/` file | Co-located with commands, matches `TicketsCog` pattern vs separation | **Inside StellarCog** |
| Level detection | Compute from XP every gain vs increment counter | Always consistent, O(log n) vs can desync | **Compute from XP** |
| XP cooldown storage | In-memory dict vs DB timestamp | Fast, no I/O vs resets on restart | **DB timestamp** (`lastXpGain`) — already in schema; avoids extra cache complexity |
| Daily streak | Track `dailyStreak` + `lastDailyReset` on Member | +10%/day, cap 7 days, UTC date compare | **New Member columns** |
| Leaderboard cache | 30s TTL with write-through invalidation | Avoids read storms, simple invalidation on XP gain | **Cache `{guild_id}:leaderboard`** |
| Rank card generation | Pillow sync + `asyncio.to_thread()` | CPU-bound, must not block loop | **Mandatory `to_thread()`** |

## Data Flow

### XP Gain (on_message)

```
Message ──→ StellarCog.on_message()
              │
              ├─ Guard: bot? DM? → return
              ├─ Read GuildConfig (cache-first via GuildService)
              ├─ EconomyService.gain_xp(guild_id, user_id)
              │     ├─ DB: get_member() → check lastXpGain cooldown
              │     ├─ DB: update_member_xp(xp + xp_per_message)
              │     ├─ Compute new level from total XP
              │     ├─ DB: update level if changed
              │     ├─ Invalidate {guild_id}:leaderboard cache
              │     └─ Return (new_xp, new_level, leveled_up)
              └─ If leveled_up:
                    ├─ Auto-assign role from economy_config.level_role_map
                    └─ Send level-up embed in channel
```

### Daily Claim

```
/daily ──→ StellarCog.daily()
             │
             ├─ EconomyService.claim_daily(guild_id, user_id)
             │     ├─ DB: get_member() → check lastDaily (24h cooldown)
             │     ├─ Compute streak: compare UTC date of lastDaily vs today
             │     │     ├─ Consecutive → streak + 1 (cap 7)
             │     │     └─ Broken → streak = 1
             │     ├─ Amount = daily_reward * (1 + 0.10 * (streak - 1))
             │     ├─ DB: update coins + set lastDaily + lastDailyReset + dailyStreak
             │     └─ Return (success, coins_awarded, streak)
             └─ Embed: success (green) or cooldown (yellow with time remaining)
```

### Rank Card

```
/rank [member] ──→ StellarCog.rank()
                     │
                     ├─ await ctx.defer()
                     ├─ EconomyService.get_rank_info(guild_id, user_id)
                     │     └─ Returns {xp, level, coins, rank, xp_progress}
                     ├─ avatar_bytes = await member.display_avatar.read()
                     ├─ buffer = await asyncio.to_thread(
                     │       image_service.generate_rank_card, ...)
                     └─ Send file=discord.File(buffer, "rank.png")
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `bot/models/economy_config.py` | Create | Dataclass mirroring `economy_config` table with `from_db_row` / `to_db_dict` |
| `bot/models/member.py` | Modify | Add `daily_streak: int = 0`, `last_daily_reset: datetime \| None = None` fields + update `from_db_row` / `to_db_dict` |
| `bot/core/database.py` | Modify | Add 6 methods: `get_economy_config`, `upsert_economy_config`, `update_member_xp`, `update_member_coins`, `claim_daily`, `get_leaderboard`, `get_member_rank` |
| `bot/services/economy_service.py` | Create | Business logic: `gain_xp`, `claim_daily`, `get_balance`, `get_leaderboard`, `get_rank_info`, `compute_level`, `xp_progress` |
| `bot/services/image_service.py` | Create | Pillow rank card: `generate_rank_card()` — sync, called via `asyncio.to_thread()` |
| `bot/cogs/stellar.py` | Create | `StellarCog`: `on_message` XP listener + `/rank`, `/leaderboard`, `/daily`, `/coins`, `/coins` hybrid commands |
| `bot/bot.py` | Modify | Add `economy_service`, `image_service` to `__slots__`; init in `setup_hook()`; load `bot.cogs.stellar` |
| `migrations/003_economy_config.sql` | Create | `economy_config` table + `dailyStreak`/`lastDailyReset` columns on Member |
| `requirements.txt` | Modify | Add `Pillow` |
| `assets/fonts/` | Create | Open-source font (Inter Regular) for rank card text |

## Interfaces / Contracts

### EconomyConfig model

```python
@dataclass
class EconomyConfig:
    guild_id: str                          # PK, FK → guild(id)
    daily_reward: int = 100
    xp_per_message: int = 10
    xp_cooldown_seconds: int = 60
    level_base_xp: int = 100
    level_multiplier: float = 1.5
    level_role_map: dict[str, str] = field(default_factory=dict)  # {level: role_id}
    level_up_channel_id: str | None = None
```

### EconomyService public API

```python
class EconomyService:
    async def gain_xp(self, guild_id: str, user_id: str) -> tuple[int, int, bool]:
        """Returns (new_xp, new_level, leveled_up). (0, 0, False) if on cooldown."""

    async def claim_daily(self, guild_id: str, user_id: str) -> tuple[bool, int, int]:
        """Returns (success, coins_awarded, current_streak)."""

    async def get_balance(self, guild_id: str, user_id: str) -> int: ...
    async def get_leaderboard(self, guild_id: str, limit: int = 10, offset: int = 0) -> list[dict]: ...
    async def get_rank_info(self, guild_id: str, user_id: str) -> dict | None: ...
```

### DB methods (new on Database class)

```python
async def get_economy_config(self, guild_id: str) -> dict | None: ...
async def upsert_economy_config(self, config: EconomyConfig) -> None: ...
async def update_member_xp(self, guild_id: str, user_id: str, xp_delta: int) -> dict: ...
async def update_member_coins(self, guild_id: str, user_id: str, coin_delta: int) -> dict: ...
async def claim_daily(self, guild_id: str, user_id: str, amount: int, streak: int) -> dict: ...
async def get_leaderboard(self, guild_id: str, sort_by: str = "xp", limit: int = 10, offset: int = 0) -> list[dict]: ...
async def get_member_rank(self, guild_id: str, user_id: str) -> int | None: ...
```

### Migration 003

```sql
CREATE TABLE IF NOT EXISTS economy_config (
    "guildId"           TEXT PRIMARY KEY REFERENCES guild(id) ON DELETE CASCADE,
    "dailyReward"       INTEGER NOT NULL DEFAULT 100,
    "xpPerMessage"      INTEGER NOT NULL DEFAULT 10,
    "xpCooldownSeconds" INTEGER NOT NULL DEFAULT 60,
    "levelBaseXp"       INTEGER NOT NULL DEFAULT 100,
    "levelMultiplier"   REAL NOT NULL DEFAULT 1.5,
    "levelRoleMap"      JSONB NOT NULL DEFAULT '{}',
    "levelUpChannelId"  TEXT
);

ALTER TABLE member ADD COLUMN "dailyStreak"    INTEGER NOT NULL DEFAULT 0;
ALTER TABLE member ADD COLUMN "lastDailyReset" TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_member_guild_xp ON member ("guildId", xp DESC);
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `compute_level()`, `xp_progress()`, streak calculation | Pure functions, no mocks |
| Unit | `EconomyService.gain_xp` cooldown logic | Mock DB, verify timestamp comparison |
| Unit | `EconomyService.claim_daily` streak reset | Mock DB, verify UTC date comparison |
| Unit | `ImageService.generate_rank_card` | Verify BytesIO output is valid PNG |
| Integration | DB methods with Supabase mock | Verify upsert, leaderboard ordering |

## Migration / Rollout

1. Run migration 003 against Supabase (additive — no destructive changes)
2. Add `Pillow` to `requirements.txt` and commit font to `assets/fonts/`
3. Deploy bot — `setup_hook()` initializes new services and loads `StellarCog`
4. Economy is active immediately; no feature flag needed

## Open Questions

- [ ] Which open-source font to commit? (Inter recommended — SIL OFL license)
- [ ] Should `level_role_map` use string keys (JSON object) or a separate `level_roles` table? JSONB is simpler for Phase 4.
- [ ] Leaderboard pagination: embed-based (like SentinelCog) or view buttons? Defer to implementation.
