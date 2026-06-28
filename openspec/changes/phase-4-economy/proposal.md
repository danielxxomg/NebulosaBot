# Proposal: Phase 4 — Stellar (Economy)

## Intent

Add a guild economy system: XP gain on messages, daily coin claims with streak bonuses, level progression with auto-role assignment, rank cards, and leaderboards. Drives member engagement and gives guilds a progression loop.

## Scope

### In Scope
- `economy_config` table with per-guild tunable economy parameters
- `EconomyService`: XP gain with cooldown, daily claim with streak, coins balance, level calculation, leaderboard queries
- `on_message` XP listener in `StellarCog` with per-user per-guild cooldown
- `/rank`, `/leaderboard xp`, `/leaderboard coins`, `/daily`, `/coins` hybrid commands
- Rank card image generation (Pillow, dark gradient, avatar, XP bar, level, rank #)
- Level-up: auto-assign role from config + embed notification in configured channel
- Migration 003: `economy_config` table + `daily_streak`/`last_daily_reset` on Member
- Member model additions: `daily_streak`, `last_daily_reset`

### Out of Scope
- Custom rank card backgrounds (deferred)
- Economy config via web dashboard (deferred)
- Coin shop / spending mechanics (deferred)
- Level-up notification toggle (always-on for now)

## Capabilities

### New Capabilities
- `economy-service`: XP gain with cooldown, daily claim with streak bonus (+10%/day, cap 7 days), coins balance, level formula (`base * multiplier^level`), leaderboard queries (XP and coins)
- `xp-listener`: `on_message` XP gain with per-user per-guild cooldown, level-up detection (compute from XP), auto-role assignment, embed notification
- `rank-card`: Pillow image generation — dark gradient background, circular avatar, username, level badge, XP progress bar, rank number. Runs via `asyncio.to_thread()`
- `economy-commands`: `/rank [member]`, `/leaderboard <xp|coins>`, `/daily`, `/coins [member]` — all hybrid commands in `StellarCog`

### Modified Capabilities
- `initial-schema`: Migration 003 adds `economy_config` table and `daily_streak`/`last_daily_reset` columns to Member

## Approach

- **Dedicated `economy_config` table** (user decision) — clean separation from core guild config, extensible for future economy features
- **Level computed from total XP** on every gain — `O(log(xp))`, guarantees consistency
- **Streak daily bonus**: base 100, +10% per consecutive day, cap at day 7 (160). Broken streak resets to day 1
- **Leaderboard cache**: 30–60s TTL, write-through invalidation on XP/coin gain. Individual member data NOT cached
- **ImageService**: synchronous Pillow, wrapped in `asyncio.to_thread()`. Add Pillow to `requirements.txt`, create `assets/fonts/` + `assets/backgrounds/`

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/models/member.py` | Modified | Add `daily_streak`, `last_daily_reset` fields |
| `bot/models/economy_config.py` | New | Dataclass mirroring `economy_config` table |
| `bot/core/database.py` | Modified | Add economy query methods (leaderboard, XP/coin update, daily claim, rank) |
| `bot/services/economy_service.py` | New | Business logic: XP, coins, levels, daily, leaderboard |
| `bot/services/image_service.py` | New | Pillow rank card generation |
| `bot/cogs/stellar.py` | New | Hybrid commands + `on_message` XP listener |
| `bot/bot.py` | Modified | Init `EconomyService`, `ImageService`, load `StellarCog` |
| `migrations/003_economy_config.sql` | New | Create `economy_config` table, add Member columns |
| `requirements.txt` | Modified | Add `Pillow` |
| `assets/fonts/`, `assets/backgrounds/` | New | Font file + default background for rank card |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `on_message` DB write load at scale | Medium | 60s cooldown per user limits writes; leaderboard cache avoids read storms |
| Pillow blocks event loop | Low | Mandatory `asyncio.to_thread()` — enforced in code review |
| Missing font file crashes `/rank` | Low | Commit open-source font (Inter/Roboto) to `assets/fonts/` |
| First-time member has no row | Medium | Upsert pattern (follow `update_member_warnings`) |
| Streak reset edge case (timezone) | Low | Compare UTC dates; document behavior |

## Rollback Plan

1. Drop `economy_config` table and remove Member columns via reverse migration
2. Remove `StellarCog` from bot extension list — commands and listener stop loading
3. Economy services are unused if cog is unloaded — no data corruption
4. Existing XP/coins data in Member table is additive — safe to leave or clean

## Dependencies

- Pillow (new dependency)
- Open-source font file (Inter or Roboto) committed to `assets/fonts/`
- Migration 001 and 002 already applied

## Success Criteria

- [ ] `/daily` awards coins with streak bonus, resets on missed day
- [ ] `/rank` generates and sends a rank card image within 3s
- [ ] `/leaderboard xp` and `/leaderboard coins` show correct top 10 with pagination
- [ ] XP gain fires on message with cooldown, level-up triggers role assign + embed
- [ ] All commands work as hybrid (prefix + slash)
- [ ] Migration 003 applies cleanly on existing database
