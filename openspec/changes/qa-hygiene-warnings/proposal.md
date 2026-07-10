# Proposal: QA Hygiene Warnings

## Intent

Eliminate 11 pytest warnings, 2 ruff violations, and a startup fragility issue to restore zero-warning CI and resilient cog loading. Current state: 1268 tests pass, 85% coverage, mypy clean — but 11 warnings and 2 ruff errors degrade signal-to-noise in CI output and the bot crashes entirely if one cog fails to load.

## Scope

### In Scope
- try/except per `load_extension()` in `bot/bot.py` with ERROR log + continue
- Fix 5–6 AsyncMock never-awaited warnings across 5 test files
- Close `banana.webp` file handle in `bot/cogs/ocio.py` (ResourceWarning)
- Handle `TextInput.label` deprecation — suppress if full Label migration out of scope, document
- Fix 2 ruff residuals: I001 in `core.py`, SIM102 in `ticket_field_service.py`
- Optional CI `filterwarnings` tightening to lock gains

### Out of Scope
- Coverage campaigns, mypy wildcards, ticket_service split
- Dashboard, product features
- Full `discord.ui.Label` migration (tracked separately if needed)

## Capabilities

> Pure code-hygiene — no spec-level behavior changes.

### New Capabilities

None.

### Modified Capabilities

None.

## Approach

**3-task slice** to keep each PR under 400 lines:

1. **Task 1 — Ruff + Load Resilience** (~30 lines): Fix I001 (`core.py` lines 20–21 swap), SIM102 (`ticket_field_service.py` lines 91–95 collapse nested if), wrap each `load_extension()` in try/except in `bot/bot.py` lines 224–252.

2. **Task 2 — AsyncMock + ResourceWarning** (~80–100 lines): Fix tests in `test_tickets_cog.py`, `test_ticket_service.py`, `test_sentinel_i18n.py` (properly consume or suppress residual coroutines). Wrap `discord.File` in `ocio.py` with context manager or explicit close.

3. **Task 3 — TextInput.label + filterwarnings** (~20 lines): Suppress `DeprecationWarning` for `discord.ui.TextInput.label` in `pyproject.toml` (full `Label` migration deferred). Optionally add `-W error` gate after tasks 1–2 land.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/bot.py` (224–252) | Modified | try/except per load_extension |
| `bot/cogs/core.py` (20–21) | Modified | I001 import order fix |
| `bot/services/ticket_field_service.py` (91–95) | Modified | SIM102 collapse nested if |
| `bot/cogs/ocio.py` (83) | Modified | Close discord.File handle |
| `tests/test_tickets_cog.py` | Modified | AsyncMock warning fixes |
| `tests/test_ticket_service.py` | Modified | AsyncMock warning fixes |
| `tests/test_sentinel_i18n.py` | Modified | AsyncMock warning fixes |
| `tests/test_ticket_views.py` (373) | Modified | TextInput.label access suppression |
| `pyproject.toml` (54–61) | Modified | filterwarnings additions |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Load resilience hides broken cogs | Low | ERROR-level log per failure; operators must monitor |
| AsyncMock fixes require subtle mock ordering | Medium | Each warning has documented root cause in exploration |
| TextInput.label suppression delays migration | Low | Document debt; full Label migration is separate change |

## Rollback Plan

Each task is an independent PR. Revert the specific PR if issues arise. No schema changes or data migrations — all changes are code-only and fully reversible via `git revert`.

## Dependencies

None — all changes are internal to the bot codebase.

## Success Criteria

- [ ] `pytest` runs with 0 warnings (from 11)
- [ ] `ruff check bot/` passes with 0 errors (from 2)
- [ ] Bot starts successfully even when one cog fails to load
- [ ] CI remains green across all 3 task PRs
