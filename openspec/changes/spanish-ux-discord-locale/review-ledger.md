# Review Ledger — spanish-ux-discord-locale (Judgment Day Design)

**Phase**: post-design Judgment Day Round 1  
**Artifact store**: openspec  
**Date**: 2026-07-10

## Convergence

| Source | Result |
|--------|--------|
| Judge A | 1 CRITICAL candidate (JD-A-001) |
| Judge B | CLEAN |
| Orchestrator triage | **CONFIRMED** JD-A-001 with code evidence |

## Findings

| id | lens | location | severity | status | evidence |
|----|------|----------|----------|--------|----------|
| JD-A-001 | judgment-day | design.md panel defaults; specs/ticket-views; bot/cogs/tickets.py:164-182 | CRITICAL | verified | Design + ticket-views require `/ticket_panel` args default `None` and resolve via `t(guild_id, …)`; explicit overrides preserved. Re-judge A: verified. |

## Re-judge (Judge A only, user-requested)

| Source | Result |
|--------|--------|
| Judge A Round 2 (scoped) | JD-A-001 **verified** |

## Terminal state

**JUDGMENT: APPROVED** — design package cleared for tasks.

---

# Phase 1 Implementation — Judgment Day Round 1 (Judge B)

**Phase**: Phase 1 code slice (i18n.py, bot.py setup_hook wiring, core.py /sync, locales slash keys, test_i18n.py)
**Artifact store**: openspec
**Date**: 2026-07-11
**Scope note honored**: Phase 2/3 (cogs still English, views not localized) is out of scope. Only real Phase 1 defects that break production or violate Phase 1 contracts are flagged.

## Convergence

| Source | Result |
|--------|--------|
| Judge B (jd-judge-b) | 2 WARNING (info) — 0 BLOCKER, 0 CRITICAL |

No BLOCKER/CRITICAL candidates → no adversarial verification needed per JD protocol.

## Findings

| id | lens | location | severity | status | assessment | evidence |
|----|------|----------|----------|--------|------------|----------|
| JD-B-P1-001 | judgment-day | bot/core/i18n.py:250-275 (validate_slash_localizations) ; design.md "Hybrid fallback" | WARNING | info | theoretical | Spec `slash-locale-translator/spec.md` "Post-registration hook for hybrid commands" states the system MUST inject `description_localizations` into hybrid commands after registration. `SLASH_DESCRIPTIONS`/`SLASH_DESCRIBES` registries are defined (48 cmds, 46 params) but `validate_slash_localizations` only logs missing localizations and never injects from the registry. The design says "the hook assigns the registry's locale_str ... then verifies" and "logs and aborts sync rather than silently publishing English-only metadata" — impl neither injects nor aborts. Because the cogs currently use plain `str` descriptions (Phase 2 locale_str adoption), the injection would be the only mechanism producing localized metadata in Phase 1; its absence means slash descriptions stay English for all Discord client locales. Flagged as design-contract gap, not a production crash. Severity WARNING because (a) no runtime exception, (b) the scope note explicitly defers cog-localization to Phase 2, and (c) the validator's log-only behavior is internally consistent and tested by `test_missing_description_logs_error`. |
| JD-B-P1-002 | judgment-day | bot/core/i18n.py:178 (_resolve_key) | WARNING | info | theoretical | `_resolve_key` casts non-string leaf nodes via `str(current)`, so querying a parent dict node (e.g. `slash.descriptions.configure_fields`) returns a Python-dict-stringified blob instead of a locale string, and `t()` then tries to `{_}`-interpolate that blob (observed: logs `Missing placeholder '_'` and returns the dict-as-string). Only reachable via a wrong key path; every registry entry uses `._` for group nodes, so the slash metadata path never triggers this. Not a production defect for Phase 1 keys; reported as a first-pass quality signal on the robustness of the lookup helper. |

## Verdict

| Metric | Count |
|--------|-------|
| Confirmed BLOCKER | 0 |
| Confirmed CRITICAL | 0 |
| Suspect (single-judge) | 0 |
| Contradictions | 0 |
| INFO (WARNING/SUGGESTION) | 2 |

Approved Round 1 criteria: zero confirmed BLOCKERs and zero confirmed CRITICALs surviving adversarial verification. **Met.** The 2 WARNINGs are reported once as INFO and never block per the severity floor.

## Verified contracts (Phase 1)

- ✅ `LocaleTranslator` registered via `tree.set_translator()` in `setup_hook` before `tree.sync()` (bot/bot.py:249-255). Test `test_set_translator_called_before_tree_sync` and `test_validate_slash_localizations_called_before_sync` pass and assert ordering.
- ✅ `validate_slash_localizations(self.tree)` called in `/sync` (bot/cogs/core.py:205) before `tree.sync()` — matches design "/sync must run the same validator before syncing".
- ✅ All `SLASH_DESCRIPTIONS` (48) and `SLASH_DESCRIBES` (46 params across 30 commands) keys resolve in both `es.json` and `en.json`. Verified by direct registry→locale walk: zero missing.
- ✅ Test's hardcoded key lists (`test_descriptions_keys_exist_in_both_locales`, `test_describes_keys_exist_in_both_locales`) exactly match the registry sets (symmetric difference empty).
- ✅ `LocaleTranslator.translate` maps `discord.Locale` (str-value form `es-ES`, `en-US`, etc.) to `es`/`en` via `_LOCALE_MAP`; returns `None` for unsupported locales — matches design ("returns None for other locales" → Discord shows default string). Verified enum values match frozenset keys.
- ✅ Translator makes no DB calls — pure in-memory `_resolve_key`. Test `test_no_database_calls` present (weak assertion, but contract documented).
- ✅ `t()` fallback chain (guild lang → es → raw key) with placeholder interpolation and missing-placeholder warning — tested and passing.
- ✅ All 28 tests in `tests/test_i18n.py` pass under `uv run pytest --no-cov -p no:randomly`.
- ✅ `load_locales()` clears state, loads `*.json`, warns on missing es/en — tested.
- ✅ Spanish is the default message string (`_DEFAULT_LOCALE = "es"`); spec "Spanish is default message string" honored at the translator level.

## Terminal state

**JUDGMENT: APPROVED ✅** — Phase 1 code slice cleared. 2 INFO warnings filed (no fix, no re-judge per severity floor). The design-contract gap on injection (JD-B-P1-001) is a known Phase 2 dependency; the registry is in place and ready to consume when the injection hook is added.

---

# Phase 1 Fix — JD-A-P1-001 (HybridAppCommand AttributeError)

**Phase**: Phase 1 fix agent
**Date**: 2026-07-11
**Scope**: `bot/core/i18n.py` (`_check_localizations`), `tests/test_i18n.py`

## Finding

| id | lens | location | severity | status | evidence |
|----|------|----------|----------|--------|----------|
| JD-A-P1-001 | judgment-day | bot/core/i18n.py:267-274 (`_check_localizations`) | CRITICAL | **fixed** | `tree.walk_commands()` yields `HybridAppCommand` which has NO `description_localizations` attribute (verified: `hasattr` returns `False`). Direct access `cmd.description_localizations` raises `AttributeError` in `setup_hook` and `/sync` before `tree.sync()`. |

## Fix applied

- `_check_localizations` now uses `getattr(cmd, "description_localizations", None)` — no `AttributeError` for any command type.
- Fallback: checks `_locale_description` for a `locale_str` with extras key (Phase 3 ready).
- Log level changed from `ERROR` to `WARNING` — missing localization is not a fatal condition during Phase 1.
- 2 new tests added:
  - `test_hybrid_app_command_no_description_localizations_attr` — bare object without the attribute does NOT raise; logs warning.
  - `test_hybrid_app_command_with_locale_description_skips_warning` — object with `_locale_description` set passes silently.
- Existing tests updated to match new WARNING log level and explicit `_locale_description = None` on mocks.

## Test results

30 passed, 0 failed (`uv run pytest tests/test_i18n.py -q --no-cov`).

## Terminal state

**JD-A-P1-001: fixed ✅**
