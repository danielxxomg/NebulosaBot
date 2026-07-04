# Verification Report: greeting-card-toggle

## Verdict

**PASS WITH WARNINGS** — ready to archive after acknowledging the non-blocking verification-command warnings below.

## Completeness

| Dimension | Result | Evidence |
|---|---:|---|
| Spec coverage | ✅ 7/7 scenarios covered | `tests/test_greeting_service.py` card-toggle tests all pass |
| Design conformance | ✅ Pass | Toggle branches at `bot/services/greeting_service.py:118` and `:167`, after channel-not-found guards and before avatar/card generation |
| Task conformance | ✅ 1.1-5.5 complete | `tasks.md` 1.1-5.4 checked; commit `37e821d` exists for 5.5 despite stale unchecked artifact line |
| AGENTS.md conformance | ✅ Pass | No `print`, no bare `except:`, Pillow/card generation remains inside `asyncio.to_thread`, cache keys include `guild_id`, public methods typed |
| Regression | ✅ Pass | Full suite green: 438 passed |

## Test Results

| Command | Result | Count / Notes |
|---|---:|---|
| `uv run pytest` | ✅ Pass | 438 passed in 13.21s; total coverage 77.46%, gate 70% |
| `uv run pytest tests/test_greeting_service.py -v` | ⚠️ Tests pass, command exits non-zero | 21 passed, then coverage failure because project `addopts` measures whole `bot` coverage on a single-file run: total 6.81% < 70% |
| `uv run pytest tests/test_greeting_service.py -v --no-cov` | ✅ Pass | 21 passed in 0.13s; focused test behavior confirmed without global coverage gate |
| `COVERAGE_FILE=/tmp/opencode/nebulosabot_greeting_toggle.coverage uv run pytest --cov=bot --cov-report=term-missing` | ✅ Pass | 438 passed in 12.02s; total coverage 77.46%, `bot/services/greeting_service.py` 90% |

Note: a concurrent coverage run once hit `coverage.exceptions.DataError: no such table: other_db.file` while combining `.coverage`; rerunning with an isolated `COVERAGE_FILE` produced a clean pass. This is a verification-environment artifact, not a code failure.

## Lint / Type / Coverage

| Check | Result | Evidence |
|---|---:|---|
| `make lint` | ✅ Pass | Ruff check passed; Ruff format check: 17 files already formatted |
| `make type` | ✅ Pass | Mypy success on scoped target: 6 source files |
| Coverage gate | ✅ Pass | 77.46% >= 70%; changed implementation file `greeting_service.py` 90% |

## Spec Coverage Matrix

| Spec scenario | Covering test | Runtime assertion evidence | Status |
|---|---|---|---:|
| Welcome card sent when toggle enabled | `TestDispatchWelcome::test_card_enabled_sends_welcome_card` (`tests/test_greeting_service.py:296`) | `generate_greeting_card.assert_called_once()`, `channel.send.assert_called_once()`, `"file" in channel.send.call_args.kwargs` | ✅ Covered |
| Welcome text-only when toggle disabled and message set | `TestDispatchWelcome::test_card_disabled_with_message_sends_text_only` (`tests/test_greeting_service.py:315`) | `generate_greeting_card.assert_not_called()`, no `file`, content includes `<@333>` and `TestServer` | ✅ Covered |
| Welcome nothing when toggle disabled and no message | `TestDispatchWelcome::test_card_disabled_without_message_sends_nothing` (`tests/test_greeting_service.py:338`) | `generate_greeting_card.assert_not_called()`, `channel.send.assert_not_called()` with `welcomeMessage=None` | ✅ Covered |
| Goodbye card sent when toggle enabled | `TestDispatchGoodbye::test_card_enabled_sends_goodbye_card` (`tests/test_greeting_service.py:456`) | `generate_greeting_card.assert_called_once()`, `channel.send.assert_called_once()`, `"file" in channel.send.call_args.kwargs` | ✅ Covered |
| Goodbye text-only when toggle disabled and message set | `TestDispatchGoodbye::test_card_disabled_with_message_sends_text_only` (`tests/test_greeting_service.py:475`) | `generate_greeting_card.assert_not_called()`, no `file`, content includes `<@444>` | ✅ Covered |
| Goodbye nothing when toggle disabled and no message | `TestDispatchGoodbye::test_card_disabled_without_message_sends_nothing` (`tests/test_greeting_service.py:497`) | `generate_greeting_card.assert_not_called()`, `channel.send.assert_not_called()` with `goodbyeMessage=None` | ✅ Covered |
| Top-level greeting guard still applies | `TestDispatchWelcome::test_disabled_skips_before_card_toggle` (`tests/test_greeting_service.py:361`) and goodbye mirror (`:520`) | top-level disabled config causes no card generation and no send despite card toggle defaulting true | ✅ Covered |

## Design Conformance

| Design requirement | Evidence | Status |
|---|---|---:|
| Insert welcome branch after `channel is None` guard and before `avatar_url` | Guard returns at `bot/services/greeting_service.py:111-116`; card toggle branch at `:118-122`; `avatar_url` starts at `:124` | ✅ Pass |
| Insert goodbye branch after `channel is None` guard and before `avatar_url` | Guard returns at `bot/services/greeting_service.py:160-165`; card toggle branch at `:167-171`; `avatar_url` starts at `:173` | ✅ Pass |
| Shared helper exists | `_send_text_only_if_message()` at `bot/services/greeting_service.py:216-226` | ✅ Pass |
| Card-enabled path preserved | `git diff 37e821d^ 37e821d -- bot/services/greeting_service.py` shows only inserted branches/helper; existing `asyncio.to_thread(...generate_greeting_card...)`, file creation, formatting, send, logging remain unchanged | ✅ Pass |
| Text-only sends no file | Helper calls `await channel.send(content=content)` only | ✅ Pass |

## TDD Compliance

| Check | Result | Details |
|---|---:|---|
| TDD evidence reported | ✅ | `apply-progress` obs 559 includes `## TDD Cycle Evidence` |
| Test file exists | ✅ | `tests/test_greeting_service.py` exists and contains 7 new behavior/regression tests |
| GREEN confirmed | ✅ | Focused file: 21 passed with `--no-cov`; full suite: 438 passed |
| Triangulation adequate | ✅ | Enabled, disabled+message, disabled+no-message, and top-level guard scenarios covered |
| RED evidence | ⚠️ Partial | Apply-progress honestly reports enabled/card characterization tests passed immediately because the enabled path was pre-existing; disabled scenarios were real RED |
| Safety net | ✅ | Full suite and focused tests pass after implementation |

## Test Layer Distribution

| Layer | Tests | Files | Tools |
|---|---:|---:|---|
| Unit | 7 new / 21 total in file | 1 | pytest + pytest-asyncio, mocked Discord objects |
| Integration | 0 for this change | 0 | Existing integration suite passes |
| E2E | 0 | 0 | Not applicable |

## Changed File Coverage

| File | Line % | Branch % | Uncovered Lines | Rating |
|---|---:|---:|---|---|
| `bot/services/greeting_service.py` | 90% | n/a | 112-116, 161-165, 212-213, 233-235 | ✅ Excellent |
| `tests/test_greeting_service.py` | n/a | n/a | Test file not included in `--cov=bot` | n/a |

## Assertion Quality

**Assertion quality**: ✅ New card-toggle assertions verify real behavior. No tautologies, ghost loops, smoke-only assertions, or assertion-without-production-call patterns found in the new tests.

## AGENTS.md Conformance

| Rule | Evidence | Status |
|---|---|---:|
| Use logging, never `print()` | `greeting_service.py` uses `logger`; no `print()` in changed code | ✅ Pass |
| No blocking I/O in event loop / Pillow via `asyncio.to_thread()` | Card generation remains in `asyncio.to_thread` at `bot/services/greeting_service.py:125` and `:174` | ✅ Pass |
| Cogs thin / services own business logic | Change only touches service and tests | ✅ Pass |
| Cache-first reads | `get_config()` checks cache, DB fallback, then populates cache | ✅ Pass |
| Guild-scoped keys | `CACHE_KEY_TEMPLATE = "{guild_id}:greeting_config"` | ✅ Pass |
| Type hints on public functions | Public methods have typed params and returns | ✅ Pass |
| No bare `except:` | `_resolve_avatar_url` catches `Exception`, not bare `except:` | ✅ Pass |

## Findings

### CRITICAL

None.

### WARNING

1. `tests/test_greeting_service.py` / `pyproject.toml:53` — The exact focused command requested, `uv run pytest tests/test_greeting_service.py -v`, exits non-zero because project addopts enforce whole-`bot` coverage on a single-file test run. Test behavior itself is green: 21 passed, and `--no-cov` gives a clean focused run.
2. `openspec/changes/greeting-card-toggle/tasks.md:72` — Task 5.5 remains unchecked in the artifact, but commit `37e821d` exists and includes the implementation, tests, and planning artifacts. This is stale task metadata, not missing work.
3. `openspec/changes/greeting-card-toggle/tasks.md:31`, `:49`, `:58` — RED-phase wording says all selected tests fail, but apply-progress correctly records partial RED / characterization tests for pre-existing enabled and top-level guard behavior. Strict TDD evidence is honest, but task prose is over-specific.

### SUGGESTION

1. `tests/test_greeting_service.py:338`, `:497` — Add explicit empty-string (`""`) no-send tests later; current tests cover `None`, and the implementation also treats `""` as no message.
2. `tests/test_greeting_service.py:475` — Goodbye text-only test asserts mention substitution; it could also assert no literal placeholder remains or add `{server}` coverage if the goodbye template later includes it.

## Recommendation

**Ready to archive**. No spec/design/task/code blockers found. Treat the focused-command coverage behavior and stale task checkbox as non-blocking warnings.
