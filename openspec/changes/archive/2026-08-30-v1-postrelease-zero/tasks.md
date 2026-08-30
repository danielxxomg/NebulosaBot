# Tasks: v1-postrelease-zero — Restore v1.0.0 Gates and Slash-Only Truth

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 950–1100 (S0 350–500, S1 600–750) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | S0→main → S1→S0 (2 PRs <1500) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 0 | Proxy verify gate | gate | `sdd-verify-validate --requirements 35 --scenarios 93` | `uv run ty check; uv run pytest --cov-fail-under=80` vs gen9 f5ba5f… | `verify-report.md` deletable; no archive mutation |
| 1 | S0 ty0+prek+ruff+cov≥80 | PR1→main | `uv run ty check` RED80→0; `pytest --cov-fail-under=80` RED79.78→≥80 | `uvx prek run --all-files`; `uv run ruff check bot tests` | Revert PR1; `pyproject.toml`+`bot/cogs/*`+`language.py`+`coverage test` |
| 2 | S1 slash-only 12 specs 27→0 | PR2→S0 | `pytest test_zero_hybrid_guard.py test_comma_timer_invariant.py` | `grep hybrid_command bot/cogs`→0; AST 0 | Revert PR2; `checks.py`+`sentinel.py:3`+`bot.py:91`+`specs/*` |

## Phase 0: Hard Gate [D6]

- [x] 0.1 RED: `sdd-verify-validate --requirements 35 --scenarios 93` on `archive/2026-08-26-clean-1-0` gen9 f5ba5f… — FAIL (ty80/cov79.78).
- [x] 0.2 GREEN: create `verify-report.md` 35/93+ty/ruff/prek/pytest evidence; no archive mutation, no reset.
- [x] 0.3 Invariants: `migrations`=29 no DDL; `TicketsCog.on_message` diff 0; blocks apply.

## Phase 1: S0 Gates [D1-D3,D7]

- [x] 1.1 RED: `uv run ty check` 80, `uv run pytest --cov --cov-fail-under=80` 79.78% FAIL, `uvx prek run --all-files` fail — capture.
- [x] 1.2 GREEN deletes: delete 60 `type: ignore` in `core.py:39,69,84,246,268,330`, `stellar.py:54,77-78,137-138,188,259-260`, `sentinel.py:93,103,108,861-905,937-981`, `utility.py:48,50-51,92,94,97,165,194,232,234`, `ocio.py:40,69,80,85,98,107,123,131,136,146,153`, `tickets.py:76,79`+tests `527,576` `87` `44,140` `76`.
- [x] 1.3 GREEN narrow 14+4: `isinstance`/`hasattr`/guarded `guild.id`, `Group.callback` hasattr, `Interaction.send`→`response.send_message`, `len(Sized)`; keep `error-on-warning=true` 10 `warn` (D1/D2).
- [x] 1.4 Verify `pyproject.toml`+`prek.toml` ty hook `uv run ty check bot/ tests/` intact; no new ignores (S1.7).
- [x] 1.5 RED→GREEN cov: add `tests/test_setup_modules_coverage.py` for `language.py:71-121` `handle`/`render` ≥22 lines (D3); fallback `welcome.py`/`log.py`.
- [x] 1.6 S0 gates: `uv run ty check` 0, `uv run ruff check bot tests` 0, `uvx prek run --all-files` green, `uv run pytest --cov --cov-fail-under=80`≥80, `tests/test_comma_timer_invariant.py` green, no `on_message` diff.

## Phase 2: S1 Truth [D4,D5,D7]

- [x] 2.1 RED: `grep hybrid_command openspec/specs`→27 `bot/cogs`→2 AST decorators≠0 — FAIL (captured 8 RED tests before fix; deltas 12 already written, bot/cogs AST 0 but docstrings at checks.py:229,361 and sentinel:3/bot:91 retained as RED).
- [x] 2.2 Specs economy/utility: `economy-commands` (/rank,/leaderboard,/daily,/coins) + `utility-commands` (/avatar,/serverinfo,/userinfo) →slash-only (verified via `tests/test_s1_verify_deltas.py` 7/7).
- [x] 2.3 Specs sentinel/ticket/unclaim/setup: `sentinel-commands` (/warn..unban `@can_check`+`UnbanTarget`), `ticket-commands` (/ticket_panel,/create_category,/delete_category), `unclaim-command` (`check_can_unclaim`), `setup-wizard` (/setup zero-params) — all 12 deltas exist 63-159 lines, `bot-core` untouched.
- [x] 2.4 Specs perm/slash/help/i18n/docs/guild: `permission-model` (7 keys `can_member`), `slash-locale-translator` (`locale_str`), `qa-help-builder`, `i18n-system`, `docs-manual` (Comandos Slash), `guild-config` (data-only `cache_key` `IF NOT EXISTS`) — verified deltas slash-only, `bot-core` untouched.
- [x] 2.5 Hygiene: `bot/utils/checks.py:229,361` hybrid→`app_commands.command` (D4); `bot/cogs/sentinel.py:3` `bot/bot.py:91` hybrid→slash (plus `bot.py:165` comment, `checks.py` header; `bot/core/i18n.py` excluded per D4).
- [x] 2.6 Guard: `tests/test_zero_hybrid_guard.py` 8-file→repo-wide AST `bot/cogs/**/*.py` hybrid 0 (D5); `grep` bot0 specs0 except `bot-core`+`,` survivor docstrings and `close-confirmation` (now 2 tests, AST+substring, bot hybrid_command 0).

## Phase 3: Verification

- [x] 3.1 `uv run ty check`0 `uv run ruff check bot tests`0 `uvx prek run --all-files` green `uv run pytest --cov --cov-fail-under=80`≥80 AST `hybrid_command`0 `grep hybrid_command specs | grep -v bot-core`0 `tests/test_comma_timer_invariant.py`+`test_zero_hybrid_guard.py` green 29 migrations `verify-report.md` exists.
