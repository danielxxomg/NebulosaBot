## Exploration: qa-hygiene-warnings

### Current State

Baseline: 1268 tests pass, 85% coverage, mypy clean, 2 ruff errors, 11 pytest warnings.

The bot has accumulated hygiene debt across several areas:
- **Cog loading**: `bot/bot.py` `setup_hook()` loads 10 extensions sequentially with no error isolation — one failure kills the entire startup.
- **Pytest warnings**: 11 warnings emitted during a full test run (5-6 AsyncMock never-awaited, 2 ResourceWarning for unclosed `banana.webp`, 1 DeprecationWarning for `TextInput.label`).
- **Ruff residuals**: 2 violations remain — import ordering (I001) in `core.py` and a collapsible nested if (SIM102) in `ticket_field_service.py`.
- **CI filterwarnings**: `pyproject.toml` has 3 existing entries but doesn't cover the remaining warnings.

### Affected Areas

- `bot/bot.py` lines 224–252 — 10 sequential `load_extension()` calls with no try/except. One broken cog crashes `setup_hook()` and prevents the bot from starting.
- `bot/cogs/core.py` lines 20–21 — Import order violation (I001): `bot.utils.checks` before `bot.utils.brand` (alphabetically reversed).
- `bot/services/ticket_field_service.py` lines 91–95 — Nested `if` inside `if placeholder is not None:` (SIM102): only contains the inner `if`, can be collapsed.
- `bot/views/tickets.py` lines 234–264 — `TextInput(label=...)` constructor and `.label` property access. Deprecated since discord.py 2.6 in favor of `discord.ui.Label`.
- `bot/cogs/ocio.py` line 83 — `discord.File()` opens a file handle that is never closed in test contexts (mocked `ctx.send`).
- `tests/test_ticket_views.py` line 373 — Accesses `text_inputs[2].label` triggering DeprecationWarning.
- `tests/test_tickets_cog.py` — `TestReopenByTicketRef::test_reopen_wrong_guild_denied` (2 warnings), `TestCloseEdgeCases::test_close_no_ticket` (1 warning).
- `tests/test_ticket_service.py` — `test_create_ticket_without_custom_fields` (1 warning), `test_claim_ticket_updates_status` (1 warning).
- `tests/test_sentinel_i18n.py` — `TestUnwarnI18n::test_unwarn_success_es` (3 warnings).
- `pyproject.toml` lines 54–61 — Existing `filterwarnings` entries.

### Approaches

#### 1. Cog/Listener Load Resilience

**Approach A — try/except per extension with logging** — Wrap each `load_extension()` call in try/except, log the failure, and continue loading remaining extensions.

- Pros: Simple, minimal code change, each cog failure is isolated, bot starts even with broken cogs.
- Cons: Bot runs with missing cogs (commands unavailable) — operators must monitor logs.
- Effort: Low

**Approach B — Loader list with retry/fallback** — Define extensions in a list, iterate with try/except, optionally retry failed extensions once.

- Pros: Data-driven (easy to add/remove cogs), retry logic handles transient failures.
- Cons: More code, retry adds complexity for a rare problem.
- Effort: Medium

#### 2. Pytest Warnings — AsyncMock Never Awaited

**Root cause analysis**: The warnings come from tests where `AsyncMock` is assigned to mock attributes but the code path that would `await` them is either (a) not reached because the test takes an early-exit branch, or (b) the mock is re-assigned before the coroutine is consumed.

Affected tests and root causes:

| Test | Root Cause |
|------|-----------|
| `test_tickets_cog.py::TestReopenByTicketRef::test_reopen_wrong_guild_denied` | `mock_db.get_ticket` returns a row but the code path returns early after guild mismatch — the `get_ticket` coroutine from a previous `side_effect` entry is not consumed |
| `test_tickets_cog.py::TestCloseEdgeCases::test_close_no_ticket` | `mock_db.get_ticket_by_channel` returns `None`, code sends error embed and returns — the mock's internal coroutine tracking leaves an unconsumed entry |
| `test_ticket_service.py::test_create_ticket_without_custom_fields` | `mock_db.get_max_ticket_number` return value is set but the mock call generates an unconsumed coroutine |
| `test_ticket_service.py::test_claim_ticket_updates_status` | `mock_db.get_ticket.side_effect` has 2 entries but only 1 is consumed in the error path |
| `test_sentinel_i18n.py::TestUnwarnI18n::test_unwarn_success_es` | Multiple `AsyncMock` assignments (`get_active_warnings`, `deactivate_infraction`, `update_member_warnings`) — some are called via the service but the mock tracking leaves residual coroutines |

**Approach A — Fix each test individually** — For each warning, adjust the test to properly consume or suppress the AsyncMock coroutine (e.g., use `await` on the mock call, or use `spec=` to control mock behavior).

- Pros: Fixes root cause, no warning suppression needed.
- Effort: Medium (5-6 test files to touch)

**Approach B — Suppress via filterwarnings** — Add `"ignore::RuntimeWarning:unittest.mock"` to pyproject.toml.

- Pros: Instant, no code changes.
- Cons: Masks real issues, doesn't fix root cause.
- Effort: Low

#### 3. Pytest Warnings — ResourceWarning (banana.webp)

**Root cause**: `bot/cogs/ocio.py:83` creates `discord.File(str(_BANANA_IMAGE_PATH), filename="banana.webp")` which opens a file handle. In tests, `ctx.send` is mocked so the file is never sent/closed.

**Approach A — Close file in production code** — Use `async with` or explicit `file.close()` after `ctx.send()`. `discord.File` supports context manager protocol.

- Pros: Fixes the resource leak in production AND tests.
- Cons: Need to verify `discord.File` context manager behavior.
- Effort: Low

**Approach B — Suppress in tests only** — Add `"ignore::ResourceWarning"` filter for test runs.

- Pros: Instant.
- Cons: Masks the real resource leak.
- Effort: Low

#### 4. Pytest Warnings — DeprecationWarning (TextInput.label)

**Root cause**: `discord.ui.TextInput.label` property is deprecated since discord.py 2.6. The production code in `bot/views/tickets.py` passes `label=` to the `TextInput` constructor (line 235, 244, 257), and `test_ticket_views.py:373` accesses `.label` on a TextInput.

**Approach A — Migrate to `discord.ui.Label`** — Replace `TextInput(label=...)` with the new `Label(text=..., component=text_input)` pattern. This is the intended migration path.

- Pros: Future-proof, removes deprecation.
- Cons: Significant API change, affects modal construction in `bot/views/tickets.py` and assertions in `test_ticket_views.py`. Need to verify `Label` works with `Modal.add_item()`.
- Effort: Medium-High

**Approach B — Suppress the deprecation warning** — Add `"ignore::DeprecationWarning:discord.ui"` to filterwarnings.

- Pros: Instant, no code changes.
- Cons: Delays inevitable migration, warning may become error in future discord.py.
- Effort: Low

**Approach C — Suppress only in tests, track migration separately** — Add test-only suppression and file a debt ticket for Label migration.

- Pros: Clean CI now, migration tracked.
- Cons: Still need to do the migration eventually.
- Effort: Low

#### 5. Ruff Residuals

**I001 in `bot/cogs/core.py`** — Swap lines 20–21: `bot.utils.brand` before `bot.utils.checks`.

- Pros: One-line swap.
- Effort: Trivial

**SIM102 in `bot/services/ticket_field_service.py`** — Collapse nested `if` at lines 91–95:
```python
# Before:
if placeholder is not None:
    if not isinstance(placeholder, str) or len(placeholder) > _MAX_PLACEHOLDER_LEN:
        raise ValueError(...)

# After:
if placeholder is not None and (not isinstance(placeholder, str) or len(placeholder) > _MAX_PLACEHOLDER_LEN):
    raise ValueError(...)
```

- Pros: Satisfies ruff, still readable.
- Effort: Trivial

#### 6. CI Filterwarnings (optional)

**Approach A — Add targeted suppression entries** — Add specific `filterwarnings` entries for the known warnings while root-cause fixes are in progress.

- Pros: Clean CI output immediately.
- Cons: Must remember to remove when root causes are fixed.
- Effort: Low

**Approach B — Use `-W error` in CI** — Treat all warnings as errors to prevent regression.

- Pros: Enforces zero-warning discipline.
- Cons: Breaks CI until all warnings are fixed (chicken-and-egg).
- Effort: Low (after root causes are fixed)

### Recommendation

**Slice the work into 3 tasks** to keep each PR under the 400-line review budget:

1. **Task 1 — Ruff + Load Resilience** (~30 lines): Fix I001 in `core.py`, SIM102 in `ticket_field_service.py`, wrap `load_extension()` calls in try/except in `bot.py`.

2. **Task 2 — AsyncMock + ResourceWarning fixes** (~80-100 lines): Fix the 5-6 test files with AsyncMock never-awaited warnings, close the `discord.File` handle in `ocio.py`.

3. **Task 3 — TextInput.label + filterwarnings** (~20 lines): Suppress the DeprecationWarning in `pyproject.toml` filterwarnings (defer full Label migration to a separate change), optionally add `-W error` gate after tasks 1-2 are complete.

This keeps each PR focused, reviewable, and independently verifiable.

### Risks

- **TextInput.label migration**: Full migration to `discord.ui.Label` is a bigger change than the scope allows. The Label API wraps a component differently — need to verify modals still work. Suppressing the warning and tracking migration separately is safer for this cycle.
- **Load resilience hides failures**: If operators don't monitor logs, a broken cog could go unnoticed. The implementation MUST log at ERROR level and the bot SHOULD expose a health metric for loaded cog count.
- **AsyncMock fixes may be subtle**: Some warnings come from mock internals (coverage bytecode scanning interacting with AsyncMock). The root cause in tests may require careful analysis of mock call ordering.

### Ready for Proposal

Yes — all four scope items are well-understood with concrete file locations, root causes, and fix approaches. The recommended 3-task slice keeps each PR under 150 lines changed. The orchestrator should tell the user:

> Investigation complete. Found 4 hygiene issues with clear root causes:
> 1. **Load resilience**: 10 sequential `load_extension()` calls with no error isolation in `bot.py`
> 2. **11 pytest warnings**: 5-6 AsyncMock never-awaited (5 test files), 2 ResourceWarning (unclosed `banana.webp`), 1 DeprecationWarning (`TextInput.label`)
> 3. **2 ruff errors**: import ordering in `core.py`, nested if in `ticket_field_service.py`
> 4. **CI filterwarnings**: 3 existing entries, no coverage for remaining warnings
>
> Recommended 3-task slice: (1) ruff + load resilience, (2) AsyncMock + ResourceWarning, (3) TextInput suppression + filterwarnings. Ready for proposal.
