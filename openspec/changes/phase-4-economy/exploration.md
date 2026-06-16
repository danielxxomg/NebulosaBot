## Exploration: Phase 4 — Stellar (Economy)

### Current State

Phases 1–3 are complete. The bot has:

- **Member model** (`bot/models/member.py`): Already has `xp`, `level`, `coins`, `last_daily`, `last_xp_gain` fields — migration 001 created these columns.
- **GuildConfig model** (`bot/models/guild.py`): Has NO economy configuration fields (no `dailyReward`, `xpPerMessage`, `xpCooldownSeconds`, `levelBaseXP`, `levelMultiplier`).
- **Database** (`bot/core/database.py`): Has `get_member()` and `update_member_warnings()` but NO economy-specific query methods (no leaderboard query, no XP update, no coin update, no daily claim update).
- **Services**: `GuildService`, `InfractionService`, `TicketService`, `TranscriptService` — no `EconomyService` or `ImageService`.
- **Cogs**: `CoreCog`, `SentinelCog`, `TicketsCog` — no `StellarCog`.
- **on_message pattern**: `TicketsCog.on_message()` demonstrates the listener pattern with O(1) early-return via cached channel set.
- **Cache**: `TTLCache` with guild-scoped keys (`{guild_id}:config`), 5-min TTL.
- **Pillow**: NOT in `requirements.txt`. No `assets/` directory exists (no fonts, no backgrounds).

### Affected Areas

- `bot/models/guild.py` — Must add economy config fields OR create a new `EconomyConfig` model
- `bot/models/member.py` — Already has economy columns; may need helper methods (e.g., `xp_for_next_level()`)
- `bot/core/database.py` — Needs new methods: `get_leaderboard()`, `update_member_economy()`, `get_member_economy()`
- `bot/services/economy_service.py` — **NEW**: XP gain, daily claim, level calculation, cooldown checks
- `bot/services/image_service.py` — **NEW**: Pillow rank card generation (blocking I/O → `asyncio.to_thread()`)
- `bot/cogs/stellar.py` — **NEW**: Hybrid commands `/rank`, `/leaderboard`, `/daily`, `/coins`
- `bot/bot.py` — Must initialise `EconomyService` and `ImageService` in `setup_hook()`, load `StellarCog`
- `bot/cogs/stellar.py` (listener) — `on_message` XP gain with cooldown, level-up notification
- `migrations/003_economy_config.sql` — **NEW**: Add economy config columns to `guild` table (or new table)
- `requirements.txt` — Must add `Pillow`
- `assets/fonts/` — **NEW**: Font file(s) for rank card text
- `assets/backgrounds/` — **NEW**: Default rank card background image

---

### Approaches

#### 1. Economy Config Storage

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **A: Add columns to `guild` table** | Simple, one row per guild, no new table, matches existing pattern (logEnabled, welcomeEnabled) | Guild table gets wider; economy config is conceptually separate from core config | Low |
| **B: New `economy_config` table** | Clean separation, easier to extend independently | Extra table, extra query, extra model, FK to guild adds complexity for a 1:1 relationship | Medium |

**Recommendation: Approach A** — Add columns to `guild` table. The existing `GuildConfig` model already holds per-guild toggles (`logEnabled`, `welcomeEnabled`). Economy config is the same pattern: per-guild tunable values with sensible defaults. A separate table for a 1:1 relationship is over-engineering at this scale.

New `GuildConfig` fields:
```python
daily_reward: int = 100
xp_per_message: int = 10
xp_cooldown_seconds: int = 60
level_base_xp: int = 100
level_multiplier: float = 1.5
```

Migration 003:
```sql
ALTER TABLE guild ADD COLUMN "dailyReward" INTEGER NOT NULL DEFAULT 100;
ALTER TABLE guild ADD COLUMN "xpPerMessage" INTEGER NOT NULL DEFAULT 10;
ALTER TABLE guild ADD COLUMN "xpCooldownSeconds" INTEGER NOT NULL DEFAULT 60;
ALTER TABLE guild ADD COLUMN "levelBaseXp" INTEGER NOT NULL DEFAULT 100;
ALTER TABLE guild ADD COLUMN "levelMultiplier" REAL NOT NULL DEFAULT 1.5;
```

---

#### 2. XP Listener Placement

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **A: Listener inside `StellarCog`** | Co-located with economy commands, single cog for all economy logic, same pattern as `TicketsCog.on_message()` | StellarCog gets bigger; listener + commands in one file | Low |
| **B: Separate `listeners/xp_listener.py`** | Clean separation; listener is not a command | Breaks the existing pattern (TicketsCog has its own listener); adds a new architectural concept; requires extra cog or raw listener registration | Medium |

**Recommendation: Approach A** — Put the `on_message` listener inside `StellarCog`. This matches the established pattern (`TicketsCog` has its own `on_message` for ticket activity). The XP listener is tightly coupled to `EconomyService` which lives on the same cog. Keep it simple.

---

#### 3. Level Formula & Level-Up Detection

**User decision**: `level = floor` where `base * multiplier^level <= total_xp`
Default: `100 * 1.5^level`

Two approaches for detecting level-up:

| Approach | Pros | Cons | Complexity |
|----------|------|------|------------|
| **A: Compute level from XP on every gain** | Level is always consistent with XP; no stale level in DB; `level` column is a cache | Slightly more CPU per message (log computation is trivial) | Low |
| **B: Increment level counter on threshold cross** | Explicit level-up event; easy to hook notifications | Level can desync from XP if XP is ever modified externally; needs careful edge-case handling | Medium |

**Recommendation: Approach A** — Compute level from total XP each time. The formula is `O(log(xp))` which is negligible. After XP gain, compute new level, compare to stored level. If different → level-up. This guarantees consistency and makes the `level` column a pure cache of the formula result.

Level computation:
```python
def compute_level(total_xp: int, base: int = 100, multiplier: float = 1.5) -> int:
    """Return the level for a given total XP amount."""
    level = 0
    xp_needed = base
    while total_xp >= xp_needed:
        total_xp -= xp_needed
        level += 1
        xp_needed = int(base * (multiplier ** level))
    return level

def xp_for_next_level(level: int, base: int = 100, multiplier: float = 1.5) -> int:
    """Return the XP required to reach the next level from the start of *level*."""
    return int(base * (multiplier ** level))

def xp_progress(total_xp: int, base: int = 100, multiplier: float = 1.5) -> tuple[int, int, int]:
    """Return (current_level, xp_into_current_level, xp_needed_for_next_level)."""
    level = 0
    remaining = total_xp
    while True:
        needed = int(base * (multiplier ** level))
        if remaining < needed:
            return level, remaining, needed
        remaining -= needed
        level += 1
```

---

#### 4. Database Methods Needed

New methods for `Database` class:

```python
async def get_leaderboard(self, guild_id: str, limit: int = 10, offset: int = 0) -> list[dict]:
    """Top members by XP for a guild. Ordered by xp DESC."""

async def update_member_xp(self, guild_id: str, user_id: str, xp_delta: int) -> dict:
    """Increment XP and lastXpGain. Returns updated row. Creates row if missing."""

async def update_member_coins(self, guild_id: str, user_id: str, coin_delta: int) -> dict:
    """Increment coins. Returns updated row. Creates row if missing."""

async def claim_daily(self, guild_id: str, user_id: str, amount: int) -> dict:
    """Set lastDaily to now and increment coins by amount. Returns updated row."""

async def get_member_rank(self, guild_id: str, user_id: str) -> int | None:
    """Return 1-based rank of user by XP within guild. None if member has no row."""
```

**Upsert pattern**: `update_member_xp` and `update_member_coins` must handle the case where the member row doesn't exist yet (first interaction). Follow the `update_member_warnings()` pattern: read → if exists, update → if not, upsert initial row.

**Leaderboard query**: Use Supabase `.select("userId, xp, level").eq("guildId", guild_id).order("xp", desc=True).range(offset, offset + limit - 1)`. Add an index on `(guildId, xp DESC)` for performance at scale.

---

#### 5. EconomyService Design

```python
class EconomyService:
    """Business logic for XP, coins, levels, and daily claims."""

    __slots__ = ("_db", "_cache")

    def __init__(self, db: Database, cache: TTLCache) -> None: ...

    async def gain_xp(self, guild_id: str, user_id: str) -> tuple[int, int, bool]:
        """Award XP for a message. Returns (new_xp, new_level, leveled_up).
        Checks cooldown via GuildConfig.xp_cooldown_seconds and Member.last_xp_gain.
        Returns (0, 0, False) if on cooldown."""

    async def claim_daily(self, guild_id: str, user_id: str) -> tuple[bool, int]:
        """Claim daily reward. Returns (success, coins_awarded).
        Checks 24h cooldown via Member.last_daily."""

    async def get_balance(self, guild_id: str, user_id: str) -> int:
        """Return coin balance for a member."""

    async def get_leaderboard(self, guild_id: str, limit: int = 10, offset: int = 0) -> list[dict]:
        """Return top members by XP with rank, userId, xp, level."""

    async def get_rank_info(self, guild_id: str, user_id: str) -> dict | None:
        """Return {xp, level, coins, rank, xp_progress} for a member."""
```

**Cooldown check strategy**: Read `Member.last_xp_gain` from DB (or cache), compare to `datetime.now(timezone.utc)`. If `now - last_xp_gain < xp_cooldown_seconds`, return early. No need for a separate cooldown cache — the DB timestamp is the source of truth and the read is cheap (single-row select by composite PK).

**Cache strategy for EconomyService**:
- **Do NOT cache individual member XP/coins** — these change on every message; cache would be stale immediately.
- **DO cache leaderboard** with short TTL (30–60 seconds) — leaderboard is read-heavy (/leaderboard command) and write-through invalidation on XP gain is simple.
- Cache key: `{guild_id}:leaderboard`

---

#### 6. ImageService Design (Rank Card)

```python
class ImageService:
    """Pillow-based image generation for rank cards."""

    __slots__ = ("_font_path", "_bg_path")

    def __init__(self, font_path: str, bg_path: str) -> None: ...

    def generate_rank_card(
        self,
        *,
        username: str,
        avatar_bytes: bytes,
        level: int,
        current_xp: int,
        xp_for_next: int,
        rank: int,
        total_members: int,
    ) -> io.BytesIO:
        """Generate a rank card image. Runs synchronously — call via asyncio.to_thread()."""
```

**Rank card layout** (934×282 px, inspired by ProBot/Carl-bot style):
- Left: Circular avatar (128×128)
- Center: Username, level badge, XP progress bar (filled proportional to `current_xp / xp_for_next`)
- Right: Rank number (e.g., "#3")
- Background: Dark gradient or loaded image from `assets/backgrounds/`
- Font: `assets/fonts/` — a clean sans-serif (e.g., Inter, Montserrat, or similar)

**Blocking I/O**: Pillow operations are CPU-bound. MUST wrap in `asyncio.to_thread()`:
```python
buffer = await asyncio.to_thread(
    self.bot.image_service.generate_rank_card,
    username=str(member.display_name),
    avatar_bytes=avatar_bytes,
    ...
)
file = discord.File(buffer, "rank.png")
```

**Avatar fetching**: `member.display_avatar.read()` returns bytes. Pass directly to ImageService — no need to save to disk.

---

#### 7. StellarCog Commands

```python
class StellarCog(commands.Cog, name="Stellar"):
    """Economy commands and XP listener."""

    # on_message listener — XP gain per message
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # Guard: ignore bots, DMs
        # Call economy_service.gain_xp()
        # If leveled_up → send level-up embed in channel

    # /rank [member] — Show rank card image
    @commands.hybrid_command(name="rank")
    async def rank(self, ctx: NebulosaContext, member: discord.Member | None = None) -> None:
        # Default to ctx.author if member is None
        # Defer (image gen takes time)
        # Fetch avatar bytes, rank info
        # Generate image via asyncio.to_thread()
        # Send as discord.File

    # /leaderboard — Top 10 by XP (paginated embed)
    @commands.hybrid_command(name="leaderboard")
    async def leaderboard(self, ctx: NebulosaContext) -> None:
        # Fetch top 10 from economy_service
        # Build embed with rank, username, level, XP
        # Paginate if > 10 entries (reuse paginator pattern from SentinelCog)

    # /daily — Claim daily coins
    @commands.hybrid_command(name="daily")
    async def daily(self, ctx: NebulosaContext) -> None:
        # Call economy_service.claim_daily()
        # Success → green embed with coins awarded
        # On cooldown → yellow embed with time remaining

    # /coins [member] — Show coin balance
    @commands.hybrid_command(name="coins")
    async def coins(self, ctx: NebulosaContext, member: discord.Member | None = None) -> None:
        # Fetch balance from economy_service
        # Send info embed
```

---

#### 8. Level-Up Notification

When `gain_xp()` returns `leveled_up=True`, the `on_message` listener sends an embed in the channel:

```python
embed = success_embed(
    "Level Up!",
    f"{message.author.mention} has reached **Level {new_level}**!"
)
await message.channel.send(embed=embed)
```

**Consideration**: Should this be configurable per guild (enable/disable)? For Phase 4, keep it always-on. Add a toggle in a later phase when the dashboard config is built.

---

### Recommendation Summary

1. **Add economy config columns to `guild` table** (Approach A) — simpler, matches existing pattern
2. **XP listener inside `StellarCog`** (Approach A) — matches `TicketsCog` pattern
3. **Compute level from XP on every gain** (Approach A) — guarantees consistency
4. **Do NOT cache individual member XP** — cache leaderboard only (30–60s TTL)
5. **Add 5 new DB methods** — `get_leaderboard`, `update_member_xp`, `update_member_coins`, `claim_daily`, `get_member_rank`
6. **ImageService with `asyncio.to_thread()`** — mandatory for Pillow
7. **Add Pillow to requirements.txt** and create `assets/fonts/` + `assets/backgrounds/`

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| `on_message` fires on EVERY message in every guild | High DB write load at scale | XP cooldown (default 60s) limits writes to 1 per minute per user. At 100 guilds × 100 active users = ~100 writes/min — manageable |
| Pillow blocks event loop if not wrapped | Bot freezes on `/rank` | Mandatory `asyncio.to_thread()` — document in code review rules |
| No font file in repo | Rank card crashes on startup | Must commit a font file to `assets/fonts/` — use an open-source font (Inter, Roboto) |
| Member row doesn't exist on first XP gain | DB error | `update_member_xp` must upsert (follow `update_member_warnings` pattern) |
| Leaderboard cache stale after XP gain | Users see outdated ranks | Invalidate `{guild_id}:leaderboard` on every XP gain (write-through) |
| Level-up notification spam in busy channels | Annoying UX | Cooldown already limits XP gain to 1/min/user, so level-ups are naturally rare |
| Supabase has no FK enforcement on Member → Guild | Orphan member rows | Application-level validation in EconomyService (check guild exists before creating member row) |

### Ready for Proposal

**Yes.** The exploration is complete. The orchestrator should tell the user:

> "Phase 4 exploration is done. We'll add 5 economy config columns to the `guild` table, create `EconomyService` + `ImageService`, build `StellarCog` with 4 hybrid commands (`/rank`, `/leaderboard`, `/daily`, `/coins`) and an `on_message` XP listener. The `Member` model already has the needed columns. We need to add Pillow to dependencies and create `assets/fonts/` + `assets/backgrounds/` directories. Ready to proceed to proposal?"
