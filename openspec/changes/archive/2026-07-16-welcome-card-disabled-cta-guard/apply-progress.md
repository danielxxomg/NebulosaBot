# Apply Progress: Guard Disabled Welcome Cards from CTA-Only Sends

## Status

- Mode: Strict TDD
- Work unit: Guard disabled welcome CTA sends
- Delivery: auto-forecast, single low-risk work unit
- Completed: 26/26 tasks, including the reopened task 1.15 correction
- Remaining: None

## Completed Tasks

- [x] 1.1–1.14 — Added guard-specific regression coverage in `tests/test_greeting_service.py`.
- [x] 1.15 — Added the old-row compatibility characterization covering omitted `onboardingChannelId`, preserved card-disabled defaults, and silent dispatch.
- [x] 2.1–2.4 — Added the welcome-only normalized text path and preserved card-enabled composition and CTA resolution.
- [x] 3.1–3.2 — Focused and full pytest verification passed.
- [x] 3.3 — Ruff and focused mypy are clean after the bounded typing cleanup.
- [x] 4.1 — Static RED captured exactly eight pre-edit mypy diagnostics.
- [x] 4.2 — Corrected the seven service diagnostics with annotations, safe channel narrowing, and accurate ignore cleanup.
- [x] 4.3 — Added the required generic arguments to `app_commands.Command` at `bot/core/i18n.py:294`.
- [x] 4.4 — Focused and full pytest verification passed without behavior changes.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written; approval case already passed | ✅ 47 passed | ➖ Existing guard coverage | ✅ Clean |
| 1.2 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written; approval case already passed | ✅ 47 passed | ➖ Existing guard coverage | ✅ Clean |
| 1.3 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written; failed as expected | ✅ 47 passed | ✅ None + resolvable CTA | ✅ Clean |
| 1.4 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written; failed as expected | ✅ 47 passed | ✅ None + whitespace cases | ✅ Clean |
| 1.5 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written; failed as expected | ✅ 47 passed | ✅ Empty + substituted whitespace | ✅ Clean |
| 1.6 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written; failed as expected | ✅ 47 passed | ✅ Existing formatter placeholder | ✅ Clean |
| 1.7 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written; failed as expected | ✅ 47 passed | ✅ Empty and CTA-channel variants | ✅ Clean |
| 1.8 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written; failed as expected | ✅ 47 passed | ✅ Invalid CTA | ✅ Clean |
| 1.9 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written; failed as expected | ✅ 47 passed | ✅ Missing CTA | ✅ Clean |
| 1.10 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written; failed as expected | ✅ 47 passed | ✅ Resolvable CTA | ✅ Clean |
| 1.11 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written; failed as expected | ✅ 47 passed | ✅ Invalid CTA | ✅ Clean |
| 1.12 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written; failed as expected | ✅ 47 passed | ✅ Locale + variables | ✅ Clean |
| 1.13 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written; approval case already passed | ✅ 47 passed | ✅ Text and empty card paths | ✅ Clean |
| 1.14 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written; approval case already passed | ✅ 47 passed | ✅ Text and empty card paths | ✅ Clean |
| 1.15 | `tests/test_greeting_service.py` | Unit | ✅ 47 passed before correction | ✅ Written first; immediate pass as a compatibility characterization; no production change expected | ✅ Targeted test passed; no production change required | ✅ Existing REQ-07 silent-guild scenario plus old-row/default path | ✅ Removed setup-only assertion; targeted test remained green |
| 2.1 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written before production edit | ✅ 47 passed | ✅ Empty, whitespace, and formatted text | ✅ Clean; no behavior change |
| 2.2 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written before production edit | ✅ 47 passed | ✅ Resolvable, invalid, and missing CTA | ✅ Clean; no behavior change |
| 2.3 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Written before production edit | ✅ 47 passed | ✅ Global guard, localization, existing config | ✅ Clean; no behavior change |
| 2.4 | `tests/test_greeting_service.py` | Unit | ✅ 32 passed (coverage gate exit) | ✅ Approval tests existed before edit | ✅ 47 passed | ✅ Card-enabled CTA-only and appended CTA | ✅ Clean; composition/resolver untouched |
| 3.1 | `tests/test_greeting_service.py` | Unit | ✅ 47 passed after implementation | ➖ Verification-only task | ✅ 47 passed with `--no-cov` | ✅ Full greeting service file | ✅ Clean |
| 3.2 | `tests/test_greeting_service.py` | Unit | ✅ 47 passed after implementation | ➖ Verification-only task | ✅ 1766 passed, 3 skipped | ✅ Full suite | ✅ Clean |
| 3.3 | `bot/services/greeting_service.py` | Static | ✅ Focused tests green | ➖ Verification-only task | ✅ `ruff` clean; `mypy` clean after bounded cleanup | ➖ Static verification | ✅ Clean |
| 4.1 | `uv run mypy bot/services/greeting_service.py` | Static | ✅ 47 focused tests passed | ✅ Pre-edit command captured exactly 8 diagnostics | ✅ Resolved by 4.2–4.3; no issues found | ➖ Static diagnostic inventory | ✅ Final command clean |
| 4.2 | `bot/services/greeting_service.py` | Static | ✅ 47 focused tests passed | ✅ Existing mypy RED before source edits | ✅ `uv run mypy bot/services/greeting_service.py` clean after seven bounded fixes | ➖ Structural typing boundary coverage; no new test file permitted | ✅ Clean; runtime tests green |
| 4.3 | `bot/core/i18n.py:294` | Static | ✅ 47 focused tests passed | ✅ Imported i18n diagnostic present in 8-error RED | ✅ `uv run mypy bot/services/greeting_service.py` clean after generic annotation | ➖ Purely structural one-line annotation | ✅ Clean; runtime tests green |
| 4.4 | `tests/test_greeting_service.py` + full suite | Unit | ✅ 47 focused tests passed | ➖ Verification-only task | ✅ 47 focused; 1766 full, 3 skipped | ✅ Focused guard and full regression coverage | ✅ Clean |

### RED Command

`uv run pytest tests/test_greeting_service.py -v --no-cov`

Result: **11 failed, 36 passed**. The failures were the expected disabled-card CTA resolution and whitespace/silence regressions. The implementation GREEN command `uv run pytest tests/test_greeting_service.py -v --no-cov` finished with **47 passed**. The continuation safety-net and final focused command also finished with **47 passed in 0.10s**. The default focused command ran 47 tests successfully but exited because the repository-wide coverage threshold cannot be met by a focused file run (`4.44% < 75%`).

## Work Unit Evidence

| Evidence | Result |
|----------|--------|
| Focused test command and exact result | `uv run pytest tests/test_greeting_service.py -v --no-cov` → 47 passed in 0.10s. Static: `uv run ruff check bot/services/greeting_service.py` → All checks passed; `uv run mypy bot/services/greeting_service.py` → Success: no issues found in 1 source file. Full: `uv run pytest` → 1766 passed, 3 skipped, 88.85% coverage (5499 statements, 75% threshold reached). |
| Runtime harness command/scenario and exact result | N/A — service-local Discord behavior is mocked; no runtime boundary. |
| Rollback boundary | Revert only the bounded typing hunks in `bot/services/greeting_service.py` and `bot/core/i18n.py:294`; retain the existing CTA guard, guard tests, and all unrelated dirty-worktree hunks. |

## Static Verification

- `uv run ruff check bot/services/greeting_service.py` → passed.
- Pre-edit `uv run mypy bot/services/greeting_service.py` → failed with exactly 8 diagnostics: 7 in `bot/services/greeting_service.py` and `bot/core/i18n.py:294` missing generic arguments.
- Final `uv run mypy bot/services/greeting_service.py` → `Success: no issues found in 1 source file`.
- The service cleanup is limited to `Any` annotation for renderer kwargs, `GuildChannel` → `Messageable` narrowing at existing dispatch send boundaries, and removal of now-inaccurate ignores. The i18n cleanup is limited to `app_commands.Command[Any, Any, Any]` at line 294.

## Deviation / Issue

- The spec/task shorthand names `{member_nick}`, but the existing formatter supports `{mention}`, `{user}`, and `{server}` only. The post-substitution whitespace regression test uses `{mention}` with an empty mention to exercise the same formatted-whitespace contract without expanding the existing placeholder API.

## Continuation Evidence

- Assigned scope was limited to tasks 3.3 and 4.1–4.4; no tests or unrelated worktree paths were edited.
- Strict TDD static RED was captured before production edits: `uv run mypy bot/services/greeting_service.py` reported exactly 8 diagnostics.
- GREEN preserved the prior 47-test guard safety net and produced clean Ruff/mypy results. The final full suite remained green at 1766 passed, 3 skipped.

## Correction Evidence — Task 1.15

The reopened correction adds only `TestDispatchWelcome::test_existing_guild_old_row_loads_without_write_or_notice`. Its DB fixture row intentionally omits `onboardingChannelId`; the service loads it with `onboarding_channel_id is None` and preserves `welcome_card_enabled is False`. Dispatch then proves no upsert, card generation, CTA resolution, channel send, or user-facing notice. The existing `test_existing_guild_silently_sends_nothing` scenario remains unchanged.

### Correction TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.15 correction | `tests/test_greeting_service.py` | Unit | ✅ 47 passed | ✅ Test written first; it passed immediately because the compatibility behavior was already correct | ✅ `uv run pytest tests/test_greeting_service.py::TestDispatchWelcome::test_existing_guild_old_row_loads_without_write_or_notice --no-cov -v` → 1 passed; no production GREEN change | ✅ Existing silent-guild scenario plus distinct old-row load/default assertions | ✅ Removed a setup-only assertion; targeted test remained 1 passed |

### Correction Test Summary

- **Tests written**: 1
- **Targeted test result**: 1 passed in 0.04s
- **Focused file result**: 48 passed in 0.13s
- **Full suite result**: 1559 passed, 3 skipped; 88.31% coverage
- **Production files changed**: None

## Correction Work Unit Evidence

| Evidence | Result |
|----------|--------|
| Focused test command and exact result | `uv run pytest tests/test_greeting_service.py::TestDispatchWelcome::test_existing_guild_old_row_loads_without_write_or_notice --no-cov -v` → 1 passed in 0.04s; `uv run pytest tests/test_greeting_service.py -v --no-cov` → 48 passed in 0.13s. |
| Runtime harness command/scenario and exact result | N/A — service-local Discord behavior is mocked; no external runtime boundary exists. The full `uv run pytest` suite passed 1559 tests with 3 skips. |
| Rollback boundary | Revert only the added test hunk in `tests/test_greeting_service.py` and the task/progress evidence for task 1.15; no production or unrelated worktree content is involved. |
