# Tasks: Phase 4 — Stellar (Economy)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1100 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Notes |
|------|------|----|-------|
| 1 | Migration, models, DB, EconomyService + tests | PR 1 | Base = tracker branch; ~450 lines |
| 2 | StellarCog commands + XP listener + bot wiring | PR 2 | Base = PR 1 branch; ~400 lines |
| 3 | ImageService rank card + font + /rank | PR 3 | Base = PR 2 branch; ~250 lines |

## Phase 1: Foundation (PR 1)

- [x] 1.1 Create `migrations/003_economy_config.sql` — `economy_config` table, `dailyStreak`/`lastDailyReset` columns, `idx_member_guild_xp` index
- [x] 1.2 Create `bot/models/economy_config.py` — `EconomyConfig` dataclass with `from_db_row`/`to_db_dict`
- [x] 1.3 Modify `bot/models/member.py` — add `daily_streak: int = 0`, `last_daily_reset: datetime | None = None`; update serialization
- [x] 1.4 Add DB methods to `bot/core/database.py`: `get_economy_config`, `upsert_economy_config`, `update_member_xp`, `update_member_coins`, `claim_daily`, `get_leaderboard`, `get_member_rank`
- [x] 1.5 Create `bot/services/economy_service.py` — `gain_xp`, `claim_daily`, `get_balance`, `get_leaderboard`, `get_rank_info`, `compute_level`, `xp_progress`; leaderboard cache `{guild_id}:leaderboard` 30s TTL + write-through invalidation
- [x] 1.6 Create `tests/test_economy_service.py` — pure-function tests for `compute_level`/`xp_progress`/streak; mock-DB tests for cooldown, streak reset, leaderboard ordering

## Phase 2: Commands + Listener (PR 2)

- [ ] 2.1 Create `bot/cogs/stellar.py` — `on_message` XP listener: guard bot/DM, call `gain_xp()`, detect level-up, auto-assign role from `level_role_map`, send level-up embed
- [ ] 2.2 Add `/daily` hybrid command — `claim_daily()`, success/cooldown embeds
- [ ] 2.3 Add `/coins [member]` hybrid command — `get_balance()`, display embed
- [ ] 2.4 Add `/leaderboard <xp|coins>` hybrid command — paginated top-10 embed, empty-state handling
- [ ] 2.5 Modify `bot/bot.py` — add `economy_service`/`image_service` to `__slots__`; init `EconomyService(db, cache)` in `setup_hook()`; load `bot.cogs.stellar`
- [ ] 2.6 Add `async def setup(bot)` in `bot/cogs/stellar.py`

## Phase 3: Rank Card (PR 3)

- [ ] 3.1 Add `Pillow` to `requirements.txt`; create `assets/fonts/`; commit Inter Regular font (SIL OFL)
- [ ] 3.2 Create `bot/services/image_service.py` — `generate_rank_card()` sync: dark gradient, circular avatar, username, level, XP bar, rank #; return `BytesIO` PNG; placeholder on missing avatar
- [ ] 3.3 Add `/rank [member]` hybrid command in `StellarCog` — `ctx.defer()`, `get_rank_info()`, `asyncio.to_thread(generate_rank_card, ...)`, send `discord.File`
- [ ] 3.4 Modify `bot/bot.py` — init `ImageService()` in `setup_hook()`; pass to `StellarCog`
- [ ] 3.5 Test: `generate_rank_card` returns valid PNG; `/rank` defers and sends file
