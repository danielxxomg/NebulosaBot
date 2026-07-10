# Design: QA Hygiene Warnings

## Technical Approach

Remove startup and QA noise at its source without changing bot features. `setup_hook()` will iterate a fixed extension sequence and isolate each load failure; warning-producing resources and mocks will be closed/configured correctly; the one deprecated `TextInput.label` test access will assert the serialized component payload instead. This implements the proposal while narrowing it to the current baseline: `uv run pytest` passes 1268 tests with 6 warnings, and `uv run ruff check bot/` reports only I001 and SIM102.

## Architecture Decisions

| Decision | Options / trade-off | Choice and rationale |
|---|---|---|
| Extension loading | Ten repeated `try` blocks preserve labels but duplicate logic; a list loop is concise; retrying adds unneeded startup complexity. | Use a module-level ordered tuple of extension paths and one loop. Catch `Exception`, call `logger.exception`, then continue. This matches the existing degraded-safe Realtime pattern and does not swallow cancellation (`CancelledError` is not an `Exception`). |
| Failure visibility | Fail-fast prevents partial operation; silently continuing hides broken commands. | Continue only after an ERROR log containing the extension name and traceback. Tree sync still runs for successfully loaded commands. No retry or health API is added in this hygiene change. |
| Warning remediation | Global `filterwarnings` makes CI quiet but masks regressions; root fixes may touch test setup. | Fix AsyncMock return values/await usage and close the file in `finally`; add no broad RuntimeWarning or ResourceWarning suppression. Replace the deprecated test property read with `to_component_dict()["label"]`; defer the full `discord.ui.Label` UI migration. |

## Data Flow

```text
setup_hook prerequisites
        |
        v
EXTENSIONS (ordered tuple) --> await load_extension(path)
        | success                    | exception
        v                            v
  info log + next path       exception log + next path
        \___________________________/
                    |
                    v
                tree.sync()
```

For `/banana`, create `discord.File` -> await `ctx.send(file=..., embed=...)` -> always `file.close()` in `finally` (it is not a context manager). Tests provide concrete `dict | None` return values for awaited database queries, so no implicit `AsyncMock` value is used as a mapping.

## File Changes

| File | Action | Description |
|---|---|---|
| `bot/bot.py` | Modify | Add ordered extension paths and a resilient load loop with success/error logging. |
| `tests/test_bot.py` | Modify | Add a startup test proving one failed extension does not prevent later loads or tree sync, and logs the failure. |
| `bot/cogs/core.py` | Modify | Sort `brand` before `checks` imports (I001). |
| `bot/services/ticket_field_service.py` | Modify | Collapse the placeholder validation condition (SIM102) without changing validation. |
| `bot/cogs/ocio.py` | Modify | Close `discord.File` in `finally` after the banana send attempt. |
| `tests/test_ocio_cog.py` | Modify | Assert file closure after both successful and failed sends. |
| `tests/test_ticket_service.py` | Modify | Configure denied note/subticket paths with concrete awaited query results; preserve audit assertions. |
| `tests/test_tickets_cog.py` | Modify | Correct AsyncMock setup only in warning-producing close/reopen paths. |
| `tests/test_sentinel_i18n.py` | Modify | Correct AsyncMock setup in the unwarn success path. |
| `tests/test_ticket_views.py` | Modify | Assert the custom input label through its serialized payload, avoiding deprecated `.label`. |

## Interfaces / Contracts

```python
EXTENSIONS: tuple[str, ...]

# Invariant: each path is attempted once, in order. A failure is logged at
# ERROR with traceback and does not prevent subsequent paths or tree sync.
```

No Discord command, database, cache, or dashboard interface changes.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Extension failure isolation; file closure; unchanged field validation and modal payload | Strict RED-GREEN: add/adjust focused tests first. Use an `AsyncMock` side effect that fails once, then assert later calls and `tree.sync`; assert `File.close()` in success and exception paths. |
| Unit | Every current never-awaited warning | Run focused reproductions with `PYTHONTRACEMALLOC=25 uv run pytest --no-cov ...`; replace implicit AsyncMock mapping results with explicit `dict | None`, never suppress RuntimeWarning. |
| Integration | Full bot test suite and warning gate | Run `uv run pytest`, then `uv run pytest -W error` after root fixes. Goal: zero warnings, 1268+ passing tests, and coverage remains at least 75%. |
| Static | Ruff scope | Run `uv run ruff check bot/`; expected zero errors. Existing non-`bot/` lint debt is out of scope. |
| E2E | Discord API | Not applicable; tests must continue using mocked Discord objects. |

## Migration / Rollout

No migration required. Deploy as one bot-only PR. Forecast is approximately 120–180 changed lines, below the 400-line preferred review slice; split/stack only if warning tracing reveals unrelated root causes that exceed it. Roll back by reverting the PR.

## Open Questions

None.
