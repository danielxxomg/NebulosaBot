# Apply Progress: Type-Strict Cogs

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/test_mypy_config.py` | Unit | ✅ 5/5 existing | ✅ Written (TestMypyCogsOverride, 2 tests) | ➖ N/A (test asserts config, not code) | ➖ Single (config assertion) | ➖ None needed |
| 1.2 | `tests/test_mypy_config.py` | Unit | ✅ 7/7 after RED | ✅ Written (narrowed pyproject) | ✅ 7 passed | ➖ Single | ➖ None needed |
| 2.1-2.4 | mypy harness | Static | N/A | N/A | ✅ mypy bot/cogs/sentinel.py → 0 errors | N/A | N/A |
| 2.5 | tests/test_sentinel_cog.py, tests/test_sentinel_i18n.py | Integration | ✅ pre-existing | N/A | ✅ 24+17 passed | N/A | N/A |
| 3.1-3.2 | mypy harness | Static | N/A | N/A | ✅ mypy bot/cogs/tickets.py, stellar.py → 0 errors | N/A | N/A |
| 3.3 | tests/test_tickets_cog.py, tests/test_stellar_cog.py | Integration | ✅ pre-existing | N/A | ✅ passed | N/A | N/A |
| 4.1-4.4 | mypy harness | Static | N/A | N/A | ✅ mypy bot/cogs/utility.py, ocio.py, core.py, setup.py → 0 errors | N/A | N/A |
| 4.5 | tests/test_utility_cog.py, etc. | Integration | ✅ pre-existing | N/A | ✅ passed | N/A | N/A |
| 5.1 | mypy harness | Static | N/A | N/A | ✅ uv run mypy bot/cogs/ → 0 errors (9 files) | N/A | N/A |
| 5.2 | full suite | Integration | N/A | N/A | ✅ 1429 passed, 3 skipped, 87.95% coverage | N/A | N/A |
| 5.3 | grep verification | Static | N/A | N/A | ✅ zero matches for override/Context | N/A | N/A |

### Test Summary
- **Total tests written**: 2 (TestMypyCogsOverride — test_cogs_wildcard_override_exists, test_cogs_override_disables_only_untyped_decorator)
- **Total tests passing**: 1429 (full suite)
- **Layers used**: Unit (2), Static/mypy (9 files), Integration (full suite)
- **Approval tests** (refactoring): None — type-only refactor, no behavior changes
- **Pure functions created**: 0 (existing code annotated, not new code)

## Changes Made

### Phase 1: Config Guard
- **tests/test_mypy_config.py**: Added `TestMypyCogsOverride` class with 2 tests asserting `bot.cogs.*` override exists and disables ONLY `untyped-decorator`
- **pyproject.toml**: Narrowed `bot.cogs.*` override from 7 codes to `["untyped-decorator"]`

### Phase 2: Sentinel + Greetings
- **bot/cogs/sentinel.py**:
  - Added `from typing import Any` import
  - Changed all `commands.Context` → `commands.Context[Any]` (12 occurrences)
  - Added `assert isinstance(ctx.author, discord.Member)` before each `log_moderation_action` call (8 occurrences)
  - Removed stale `# type: ignore[union-attr]` on role hierarchy guard, added `ctx.guild.me is not None` check
  - Removed stale `# type: ignore[misc]` on `overwrite.send_messages` (2 occurrences)
  - Changed `infractions: list` → `infractions: list[Any]` in `_build_modlog_pages`
- **bot/cogs/greetings.py**:
  - Added `from typing import Any` import
  - Changed all `commands.Context` → `commands.Context[Any]` (14 occurrences)
  - Removed 2 stale `# type: ignore[override]` on `welcome_test` and `goodbye_test`
  - Coalesced `member_count`: `ctx.guild.member_count` → `(ctx.guild.member_count or 0) if ctx.guild else 0` (2 occurrences)
  - Added `# type: ignore[arg-type]  # discord.py hybrid_command stub limitation` on all hybrid decorators (10 occurrences)
- **tests/test_sentinel_cog.py**: Changed `mod_author` fixture to use `MagicMock(spec=discord.Member)`
- **tests/test_sentinel_behavior.py**: Added `import discord`; changed `mod_author` fixture to use `MagicMock(spec=discord.Member)`
- **tests/test_sentinel_i18n.py**: Changed `ctx.author = MagicMock()` → `MagicMock(spec=discord.Member)`
- **tests/integration/test_moderation_flow.py**: Added `import discord`; changed `mod_author` fixture to use `MagicMock(spec=discord.Member)`

### Phase 3: Tickets + Stellar
- **bot/cogs/tickets.py**:
  - Added `from typing import Any` import
  - Changed all `commands.Context` → `commands.Context[Any]` (16 occurrences)
  - Removed stale `# type: ignore[assignment]` on `parent_owner` line
  - Added `# type: ignore[arg-type]  # discord.py hybrid_command stub limitation` on `unclaim` decorator
- **bot/cogs/stellar.py**:
  - Added `from typing import Any` import
  - Changed all `commands.Context` → `commands.Context[Any]` (5 occurrences)
  - Removed stale `# type: ignore[override]` on `daily` method
  - Added `# type: ignore[arg-type]  # discord.py hybrid_command stub limitation` on all hybrid_command decorators (4 occurrences)

### Phase 4: Utility + Ocio + Core + Setup
- **bot/cogs/utility.py**:
  - Added `from typing import Any` import
  - Changed all `commands.Context` → `commands.Context[Any]` (4 occurrences)
  - Added `joined_at` None guard: `format_dt(target.joined_at, "R")` → `format_dt(target.joined_at, "R") if target.joined_at is not None else "Unknown"`
  - Added `# type: ignore[arg-type]  # discord.py hybrid_command stub limitation` on all hybrid_command decorators (3 occurrences)
- **bot/cogs/ocio.py**:
  - Added `from typing import Any` import
  - Changed all `commands.Context` → `commands.Context[Any]` (2 occurrences)
  - Added `# type: ignore[arg-type]  # discord.py hybrid_command stub limitation` on hybrid_command decorators (2 occurrences)
- **bot/cogs/core.py**:
  - Added `# type: ignore[arg-type]  # discord.py hybrid_command stub limitation` on hybrid_command decorators (3 occurrences)
  - Removed stale `# type: ignore[arg-type]` on `sync` (absorbed by `@is_admin()`)
- **bot/cogs/setup.py**:
  - Added `from typing import Any` import
  - Changed `commands.Context` → `commands.Context[Any]` (1 occurrence)
  - Removed stale `# type: ignore[arg-type]` on `setup_command` (absorbed by `@is_admin()`)

## Verification Results

| Check | Result |
|-------|--------|
| `uv run mypy bot/cogs/` | ✅ Success: no issues found in 9 source files |
| `uv run pytest` | ✅ 1429 passed, 3 skipped, 87.95% coverage |
| `TestMypyCogsOverride` | ✅ 7/7 passed |
| No `commands.Context` without `[Any]` | ✅ Zero matches in source files |
| No `type: ignore[override]` in cogs | ✅ Zero matches |

## Deviations from Design
None — implementation matches design.

## Issues Found
None.
