# Apply Progress — refactor-ticket-domain S2.1 Typed Surface

## Work Unit
S2.1 Typed Surface (PR1→main) — stacked-to-main, auto-chain.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/test_s2d1_context_typing_chars.py` | Unit | ✅ 1814 pass baseline | ✅ 4 FAIL (Context[Any] present) | ✅ 9 pass | ✅ decorator + inline is_mod probes | ✅ format |
| 1.2 | same + `bot/cogs/*` | Unit | ✅ mypy bot 0 | N/A (GREEN) | ✅ NebulosaContext in sentinel/utility | ✅ interaction preserved | ✅ Any scoped |
| 1.3 | 7 files (verify/views/embeds/help/sentinel/tickets) | Unit | ✅ 28 mypy errors | N/A | ✅ mypy bot tests 0 | ✅ guards + TYPE_CHECKING | ✅ ruff 0 |
| 1.4 | full suite | Unit+Typecheck | ✅ 1823 pass | N/A | ✅ ruff 0 mypy 0 pytest 1823 | N/A | ✅ py_compile |

## Work Unit Evidence

| Evidence | Value |
|----------|-------|
| Focused test cmd | `uv run mypy bot tests` → Success 150 files; `uv run pytest tests/test_s2d1_context_typing_chars.py --no-cov -q` → 9 passed; `uv run ruff check bot tests` → All checks passed |
| Runtime harness | N/A — typed surface, no runtime boundary (is_mod behavior unchanged, views retain inline gate). |
| Rollback boundary | `bot/cogs/sentinel.py`, `bot/cogs/utility.py`, `tests/test_s2d1_context_typing_chars.py`, `tests/test_{verify,views,embeds,help,sentinel,tickets}*.py` — revert restores Context[Any] + 28 errors |

## Implementation Details

- RED: `tests/test_s2d1_context_typing_chars.py` — 4 FAIL before impl (sentinel/utility still Context[Any]).
- GREEN sentinel.py: `from bot.core.context import NebulosaContext`, 11 signatures → NebulosaContext; retained `list[Any]` via `from typing import Any`.
- GREEN utility.py: `from bot.core.context import NebulosaContext`, 3 signatures → NebulosaContext; removed `Any` import.
- 28 fixes: verify (None guard + type-ignore), views (TYPE_CHECKING TicketIntakeModal + quoted tuples + field guard), embeds (Colour None guard), help (field None guard), sentinel_cog (None guard split), sentinel_behavior (user None assert), tickets_cog (unclaim app guard + return type).
- Triangulation: decorator dual-path (checks + app_command.checks) and inline fail-closed (DM/guild no-role) both probed; `bot/views/tickets.py` retains `is_mod_check`.

## Verification

- `uv run mypy bot tests` — 0 errors (was 28).
- `uv run ruff check bot tests` — 0.
- `uv run pytest -q` — 1823 passed, 3 skipped, 88.61%.
- `python -m py_compile bot/__main__.py` — OK.
- `uv run ruff format --check .` — clean.

## Constraints Respected

- No ticket_service/views monolith split, no DB/life verifier, no DDL.
- Permission logic unchanged — only typing and type narrowing.

## Next

S2.2 Guild DB (PR2→PR1) — 12 gaps cross-guild denial.

## Commit

`f3012b7` on `refactor-ticket-domain-s2d1` (1 work-unit commit). PR draft prepared for `gh pr create --base master` (not pushed per orchestrator gate).
