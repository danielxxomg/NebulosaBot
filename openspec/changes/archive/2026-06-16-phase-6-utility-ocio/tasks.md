# Tasks: Phase 6 — Utility + Ocio Cogs

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~430 (2 cogs + 2 test files + bot.py + asset) |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (UtilityCog + tests) → PR 2 (OcioCog + asset + bot.py wiring) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | UtilityCog with /avatar, /serverinfo, /userinfo + tests | PR 1 | base = feature/phase-6-utility-ocio; ~280 lines |
| 2 | OcioCog with /dados, /banana + banana asset + bot.py wiring + tests | PR 2 | base = PR 1 branch; depends on PR 1; ~150 lines |

## Phase 1: UtilityCog Implementation

- [x] 1.1 Create `bot/cogs/utility.py` with `UtilityCog(commands.Cog, name="Utility")`, `__slots__`, and `__init__(self, bot: NebulosaBot)`
- [x] 1.2 Add `@commands.hybrid_command(name="avatar")` — default to `ctx.author`, embed with `set_thumbnail(url=member.display_avatar.url)`, use `info_embed()`
- [x] 1.3 Add `@commands.hybrid_command(name="serverinfo")` — early return with `error_embed()` when `ctx.guild is None`; raw `discord.Embed(COLOR_INFO)` with fields: name, owner.mention, member_count, channel count, role count, boost count, created_at
- [x] 1.4 Add `@commands.hybrid_command(name="userinfo")` — default to `ctx.author`, raw `discord.Embed(COLOR_INFO)` with fields: name, id, roles (truncated at 20 with "and N more" suffix), joined_at, created_at
- [x] 1.5 Add `async def setup(bot)` at module level calling `await bot.add_cog(UtilityCog(bot))`

## Phase 2: OcioCog Implementation

- [x] 2.1 Create `assets/images/` directory and add `banana.png` placeholder image
- [x] 2.2 Create `bot/cogs/ocio.py` with `OcioCog(commands.Cog, name="Ocio")`, `__slots__`, and `__init__(self, bot: NebulosaBot)`
- [x] 2.3 Add `@commands.hybrid_command(name="dados")` with `sides: app_commands.Range[int, 2, 1000] = 6` — `random.randint(1, sides)`, reply with `info_embed()`
- [x] 2.4 Add `@commands.hybrid_command(name="banana")` — `random.randint(2, 30)` cm, `info_embed()` + `discord.File("assets/images/banana.png")`; handle `FileNotFoundError` with `error_embed()`
- [x] 2.5 Add `async def setup(bot)` at module level calling `await bot.add_cog(OcioCog(bot))`

## Phase 3: Bot Wiring

- [x] 3.1 In `bot/bot.py` `setup_hook()`, add `await self.load_extension("bot.cogs.utility")` + log after GreetingsCog load (line ~216)
- [x] 3.2 In `bot/bot.py` `setup_hook()`, add `await self.load_extension("bot.cogs.ocio")` + log after utility load

## Phase 4: Testing

- [x] 4.1 Create `tests/test_utility_cog.py` — fixtures: `mock_bot` (MagicMock spec=commands.Bot), `cog` (UtilityCog), `_make_context()` helper per `test_stellar_cog.py` pattern
- [x] 4.2 Test `/avatar` self (no arg → ctx.author thumbnail) and with target member
- [x] 4.3 Test `/serverinfo` guild context (verify all fields) and DM context (`ctx.guild = None` → error embed)
- [x] 4.4 Test `/userinfo` with ≤20 roles (all listed) and >20 roles (truncated at 20 + "and N more")
- [x] 4.5 Create `tests/test_ocio_cog.py` — same fixture pattern
- [x] 4.6 Test `/dados` default (sides=6), custom (sides=20, 1000), verify result in `[1, sides]`
- [x] 4.7 Test `/banana` normal (verify File attached, measurement in `[2, 30]`) and missing asset (mock `Path.exists()` → False → error embed)

## Phase 5: Verification

- [x] 5.1 Run `python -m pytest tests/test_utility_cog.py tests/test_ocio_cog.py -v` — all pass
- [x] 5.2 Run `python -m pytest -v` — full suite passes, no regressions
