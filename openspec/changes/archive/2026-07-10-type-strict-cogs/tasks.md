# Tasks: Type-Strict Cogs

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 350-450 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

`auto-chain` → proceed with slice 1, no gate. Stacked to main: each PR merges in order.

**Conventions:** `mypy` = `uv run mypy <file>` → zero errors; `pytest` = `uv run pytest <files>` → pass.

### Suggested Work Units

| Unit | Goal | PR | base |
|------|------|----|------|
| 1 | Config test RED + narrow pyproject override | PR 1 | main |
| 2 | sentinel+greetings: Context[Any], member narrowing, coalesce, ignores | PR 2 | main+PR1 |
| 3 | tickets+stellar: Context[Any], stale ignores, decorator ignores | PR 3 | main+PR2 |
| 4 | utility+ocio+core+setup: Context[Any], joined_at guard, decorator ignores | PR 4 | main+PR3 |

## Phase 1: Config Guard (RED → GREEN)

- [x] 1.1 RED — `tests/test_mypy_config.py` add `TestMypyCogsOverride`: assert `bot.cogs.*` override exists and `disable_error_code == ["untyped-decorator"]`; pytest → fails
- [x] 1.2 GREEN — narrow `pyproject.toml` `bot.cogs.*` override to `["untyped-decorator"]`; pytest → full suite green

## Phase 2: Sentinel + Greetings (62 errors)

- [x] 2.1 sentinel — `bot/cogs/sentinel.py`: `commands.Context` → `Context[Any]`; add `assert isinstance(ctx.author, discord.Member)` before each `log_moderation_action(...)`
- [x] 2.2 sentinel suppress — add `# type: ignore[arg-type]  # discord.py hybrid_command stub limitation` on affected decorators; mypy → zero
- [x] 2.3 greetings — `bot/cogs/greetings.py`: `Context[Any]`; coalesce `member_count` → `(ctx.guild.member_count or 0) if ctx.guild else 0`
- [x] 2.4 greetings suppress — remove 2 stale `# type: ignore[override]`; add stub `arg-type` ignores on decorators; mypy → zero
- [x] 2.5 VERIFY — pytest sentinel+greetings tests → pass

## Phase 3: Tickets + Stellar (43 errors)

- [x] 3.1 tickets — `bot/cogs/tickets.py`: `Context[Any]`; stub `arg-type` ignores on affected decorators; mypy → zero
- [x] 3.2 stellar — `bot/cogs/stellar.py`: `Context[Any]`; remove stale `# type: ignore[override]` on `daily`; stub ignores; mypy → zero
- [x] 3.3 VERIFY — pytest tickets+stellar tests → pass

## Phase 4: Utility + Ocio + Core + Setup (17 errors)

- [x] 4.1 utility — `bot/cogs/utility.py`: `Context[Any]`; guard `if target.joined_at is not None:` before `format_dt` in `userinfo`; stub ignores; mypy → zero
- [x] 4.2 ocio — `bot/cogs/ocio.py`: `Context[Any]`; stub `arg-type` ignore on `dados`; mypy → zero
- [x] 4.3 core — `bot/cogs/core.py`: stub `arg-type` ignores on affected decorators; mypy → zero
- [x] 4.4 setup — `bot/cogs/setup.py`: `Context[Any]`; stub `arg-type` ignore on `setup_command`; mypy → zero
- [x] 4.5 VERIFY — pytest utility+ocio+core+setup tests → pass

## Phase 5: Full Verification

- [x] 5.1 `uv run mypy bot/cogs/` → zero errors (only `untyped-decorator` suppressed)
- [x] 5.2 `uv run pytest` → full suite green, coverage ≥ 75%
- [x] 5.3 Grep `# type: ignore[override]` and unparameterized `commands.Context` in `bot/cogs/` → zero matches
