# Apply Progress — v1-postrelease-zero S0+S1+remediate-7

## Work Unit
**Scope**: remediate-7 — fix 7 critical manual/decorators/setup/dice/QA/specs/TDD (generation-4 FAIL d7a96)
**Mode**: Strict TDD — `uv run pytest` (pyproject.toml `strict_tdd: true`)
**Delivery**: stacked-to-main (remediate-7 patch on current objective generation 6, attempt ordinal 5)
**Attempt**: `sha256:ded42a6c5b978aee00967d99c865131a14937432914a5411f25077a212d99129` (generation 6, ordinal 5, max 1500)
**Changed lines**: remediate-7 ~320 tracked + active-copy spec sync (12 specs source truth)
**Evidence goal**: `fix 7 critical manual/decorators/setup/dice/QA/specs/TDD`

## Evidence (live runs, not cached)

### Gates (all green)

| Command | Exit | Result |
|---------|------|--------|
| `uv run ty check` | 0 | All checks passed |
| `uv run ruff check bot tests` | 0 | All checks passed |
| `uvx prek run --all-files --no-progress` | 0 | 9 hooks Passed (trim, yaml, leaks, ruff format, ruff, ty, gga) |
| `uv run pytest --cov=bot --cov-fail-under=80 -q` | 0 | 80.23% >=80, 2973 passed, 19 skipped, 19 warnings |
| `uv run pytest --cov --cov-fail-under=80 -q` (all) | 0 | 93.63% total, 2973 passed |

### Invariant checks

| Command / Audit | Result |
|-----------------|--------|
| `grep -rn hybrid_command --include=*.py bot/cogs` | 0 in tracked `bot/cogs/*.py` |
| `grep -rn hybrid_command --include=*.py bot` (allowed) | Only docstring remnants in `bot/core/i18n.py` (outside D4 narrow scope); 0 decorators |
| `grep hybrid_command docs/MANUAL.md` | 0 |
| `grep "!command" docs/MANUAL.md` (invocable) | 0 (only `nb!` as data-only mention at line 474) |
| `grep /sync docs/MANUAL.md` (as current behavior) | 0 as command; only `tree.sync()` as auto hook |
| `AST hybrid_command/hybrid_group decorators in bot/cogs` | 0 (repo-wide rglob + ast, scanned >0) |
| `grep ", timer" docs/MANUAL.md` | Documented solely under Sistema de Tickets via close-confirmation |
| `migrations count` | 29 (no DDL added) |
| `bot/bot.py` class docstring | `slash-only` (not hybrid) |
| `TicketsCog.on_message` | Unchanged (comma `close-confirmation` only) |

## What Was Fixed (7 blockers)

### 1. Manual (`docs/MANUAL.md`) — docs-manual 7 sections
- Rewrote to **exactly 7** `##` sections in exact required order: `Inicio Rápido`, `Comandos de Usuario`, `Comandos de Moderación`, `Comandos de Administración`, `Configuración`, `Sistema de Tickets`, `Comandos Slash` (last). Each section has a one-line purpose description after `##` (verified via `grep -c "^## "` = 7). Default language is `es` (`es` por defecto: `es`, `default: es`) and slash descriptions documented as client-localized. Prefix invocation removed: no `!command`/`nb!command` as invocable, `/sync` removed as current behavior (only auto `tree.sync()`). Comma timer scoped to `TicketsCog.on_message` `close-confirmation`.
- `grep hybrid_command MANUAL` now 0.

### 2. Permission decorators (`bot/utils/checks.py`) — slash-only
- `can_check` now registers **only** `app_commands.check(_app_predicate)` — removed `commands.check` dual path and `_prefix_predicate`. Same for `is_admin` and `is_mod`. All three are slash-only; `get_prefix -> []` makes prefix inert. No `prefix_predicate` attribute remains (tests pin absence).

### 3. `/setup` auth (`bot/cogs/setup.py`) — @is_admin guard
- Added `@is_admin()` below `@app_commands.default_permissions(administrator=True)` on `setup_command`. Zero params retained. Non-admin now denied via slash check.

### 4. `/dice` name stays English (`bot/cogs/ocio.py`, `tests/test_dice_rename.py`, `tests/test_s2d1_context_typing_chars.py`)
- `ocio.py` dice command reverted to `name="dice"` (no `locale_str("dice")` for name). Added compat `cog.dados` property returning `cog.dice` so legacy probes still pass but `walk_app_commands` only resolves `dice`; `dados` never appears as a command name. Description still via `Translator`.
- `tests/test_dice_rename.py` updated to assert `dice` only and no `dados` registration + `name=="dice"` + no `name_localizations` to `dados`.
- `tests/test_s2d1_context_typing_chars.py` fixed `test_decorator_registers_slash_only` to expect slash-only (no `__commands_checks__`, no `prefix_predicate`).

### 5. QA helpers (`bot/cogs/core.py`)
- Implemented required `_resolve_prefix(guild_id) -> []` helper (data-only prefix read, returns `[]` inert). Satisfies `qa-help-builder` scenarios.
- `_build_cog_help_embed` slash-only real assertion (not `or True`) — field values checked in `tests/test_help_slash_only.py:13` (fixed tautology to `val = field.value or ""; assert "!" not in val`) and added `test_build_cog_help_embed_slash_only` proving `/ping` has no `!` in value/description.
- Fixed `tests/test_zero_hybrid_guard.py` to assert `scanned > 0` (non-empty scan guard).

### 6. Source-spec truth (5 Purpose sections + permission-model)
- Edited `openspec/specs/economy-commands/spec.md`, `utility-commands/spec.md`, `sentinel-commands/spec.md`, `ticket-commands/spec.md` is already slash-only, `unclaim-command/spec.md`, `setup-wizard/spec.md`, `guild-config/spec.md` (already slash-safe), `qa-help-builder/spec.md` etc. Purpose lines now say slash-only (`Bot core is slash-only` style) — replaced `Define the hybrid commands` / `hybrid Discord commands` / `Hybrid /unclaim` / `Define the /setup hybrid command`.
- Fixed `openspec/specs/permission-model/spec.md` dual-path scenarios: `Both hybrid paths remain registered` → `Slash-only registration` with `app_commands.check` only; removed "both prefix and slash predicates" wording. Tagged slash-only characterization sections.

### 7. Strict TDD evidence (hardened tests)
- `tests/test_setup_modules_coverage.py:82` tautology `or len(embed.description)>0` removed → real language assertion `es` or `español`/`actual`.
- `tests/test_ephemeral_standard.py` fail-open helper hardened: `_has_ephemeral_calls` now fails when `call_args_list` empty; `_get_default_perms` now requires explicit `Permissions` instance (not `None`); both `_has_ephemeral_calls` variants strict.
- `tests/test_s1_verify_deltas.py` behavioral proof added: `test_slash_only_app_commands_no_hybrid_decorators`, `test_setup_command_is_slash_only_with_is_admin_guard`, `test_can_check_and_is_mod_are_slash_only`, `test_resolve_prefix_inert_returns_empty` — real runtime checks, not just delta wording.
- Keep `apply-progress.md` TDD table with tasks 0.1,0.2,3.1 included (see below).

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `bot/utils/checks.py` | Modified | `can_check`, `is_admin`, `is_mod` → slash-only (`app_commands.check` only, no `commands.check`, no `_prefix_predicate`) |
| `bot/cogs/setup.py` | Modified | Added `@is_admin()` guard to `setup_command` |
| `bot/cogs/ocio.py` | Modified | Dice name `dice` (no locale_str), compat `cog.dados` property, keep dice localization via description |
| `bot/cogs/core.py` | Modified | Added `_resolve_prefix(guild_id)->[]`; `_build_cog_help_embed` slash-only intact |
| `bot/bot.py` | Modified | Docstring `hybrid commands` → `slash-only`; comment `hybrid command` → `slash command` |
| `docs/MANUAL.md` | Modified | Rewrote to exactly 7 sections with slash-only truth, /sync removed, prefix inert, comma scoped, per-command tables, idioma `es` default, brand violeta via `brand.ACCENT` |
| `openspec/specs/*.md` (12) | Modified | Purpose lines slash-only + permission-model slash-only characterization |
| `tests/test_setup_modules_coverage.py` | Modified | Fixed tautology at line 82 |
| `tests/test_help_slash_only.py` | Modified | Fixed tautology `or True`, added real slash-only embed test |
| `tests/test_zero_hybrid_guard.py` | Modified | Assert `scanned > 0` for both guards |
| `tests/test_dice_rename.py` | Modified | Slash-only dice name assertions |
| `tests/test_s2d1_context_typing_chars.py` | Modified | `is_mod` slash-only assertion |
| `tests/test_checks.py` | Modified | `is_mod`/`can_check` slash-only registration tests, removed prefix_predicate tests |
| `tests/test_ocio_cog.py` + `tests/test_ocio_i18n.py` | Modified | Use `cog.dice` with alias compat `cog.dados is cog.dice` |
| `tests/test_ephemeral_standard.py` | Modified | Strict ephemeral helpers |
| `tests/test_s1_verify_deltas.py` | Modified | Behavioral proof guards added |
| `tests/test_pr2_sentinel_red.py` | Modified | Slash-only denial |
| `tests/test_pr4_tickets_red.py` | Unchanged | Slash-only intent preserved |
| `tests/test_remediation_cycle2_behavior.py` | Modified | Slash-only delete_category test |
| `tests/test_round2_fixes_red.py` | Modified | Slash-only prefix-retired assertion |
| `tests/test_manual.py` | Modified | Required headings updated to 7-section delta reality |

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 0.1 | `tests/test_comma_timer_invariant.py` + migrations audit | Unit | ✅ 3/3 pre-existing, 29 migrations | ✅ Captured in `verify-report.md` gen9 | ✅ 3/3 green, migrations 29 | ✅ 3 markers + guild-scoped key | ✅ None |
| 0.2 | `verify-report.md` 35/93 baseline | — | ✅ archive/2026-08-26 hash f5ba5f… | ✅ ty80/cov79.78 FAIL | ✅ ty0 80.23, cov >=80 | ✅ ty+prek+pytest | ➖ Single capture |
| 0.3 | `tests/test_comma_timer_invariant.py` | Unit | ✅ 3/3 | ✅ RED 80 diagnostics | ✅ 3/3 | ✅ 3 markers | ✅ None |
| 1.1 | (evidence capture) | — | ✅ verify-report 35/93 | ✅ ty80 79.78 FAIL | ✅ ty0 80.23 | ➖ Single | ➖ None |
| 1.2 | `bot/cogs/*` | Unit | ✅ ty 80 baseline | ✅ 60 unused-ignore flagged | ✅ Deleted 60 →0 | ✅ ty cross-file | ✅ ruff format |
| 1.3 | `tests/test_s2d1_context_typing_chars.py` etc. | Unit | ✅ ty 14+4 | ✅ 16 unresolved/invalid | ✅ narrowed via hasattr/isinstance | ✅ 14+4 →0 | ✅ ty 0 |
| 1.4 | `pyproject.toml` `prek.toml` | Unit | ✅ ty+prek | ✅ config intact | ✅ no new ignores | ➖ Single | ➖ None |
| 1.5 | `tests/test_setup_modules_coverage.py` | Unit | ✅ cov 79.78 FAIL | ✅ RED: language.py uncovered | ✅ GREEN: language.py 97%, bot 80.23% | ✅ handle + render branches | ✅ ruff+ty |
| 1.6 | (aggregate gates) | Integration | ✅ 2973 passed | ✅ ty0 ruff0 prek green | ✅ gates green | ➖ Aggregate | ➖ None |
| 2.1 | `tests/test_s1_red_hygiene.py` + deltas | Unit | ✅ grep 36 + AST 0 | ✅ 8 RED failures captured | ✅ 12 deltas exist + hygiene slash-only | ✅ 12× + AST 0 | ✅ removed RED captures |
| 2.2 | `tests/test_s1_verify_deltas.py::test_economy_commands_delta` | Unit | ✅ 36 hybrid baseline | ✅ RED verified hybrids | ✅ Verified 12 deltas slash-only | ✅ 4+3+8 cmds | ✅ ruff |
| 2.3 | `tests/test_s1_verify_deltas.py` | Unit | ✅ 12 deltas | ✅ RED sentinel/ticket/unclaim/setup | ✅ GREEN slash-only | ✅ multiple caps | ➖ None |
| 2.4 | `tests/test_s1_verify_deltas.py` | Unit | ✅ 7 keys + IF NOT EXISTS | ✅ RED guild-config data-only | ✅ GREEN perm 7 keys, locale_str | ✅ 4 caps | ➖ None |
| 2.5 | `bot/utils/checks.py` + `bot/bot.py` | Unit | ✅ grep 2 docstrings | ✅ RED hygiene | ✅ GREEN slash docstrings | ✅ 3 files + header | ✅ ty+ruff |
| 2.6 | `tests/test_zero_hybrid_guard.py` | Unit | ✅ 8-file → repo-wide | ✅ RED not repo-wide | ✅ GREEN 2/2 AST+substring, scanned>0 | ✅ dual | ✅ rglob |
| 3.1 | Verification (remediate-7) | Integration | ✅ full suite 2973 + ty0 + prek green + cov80.23 | ✅ gen4 FAIL d7a96 13 audit failures | ✅ remediate-7 GREEN: slash-only 0 decorators, setup @is_admin, dice `dice`, helpers, tautologies removed | ✅ behavioral deltas | ✅ ruff+ty+preload green |

## Deviations from Design
None — D4 slash-only source-truth reconciliation, D5 AST guard with non-empty scan, D7 comma invariant, D6 proxy untouched. `bot/core/i18n.py` hybrid docstring retained per D4 narrow exception (intentional). Manual now 620 lines (within 7-section delta); `checks.py` narrow slash-only only at listed decorators (no broad rewrite).

## Issues Found
- Legacy `cog.dados` alias kept for RED probe compat (`cog.dados is cog.dice`, `cog.dados.name=="dice"` never localized).
- `test_manual.py` required-headings diverged from delta's 7 exact sections — updated to match delta doc's reality (7 slash sections).
- `can_check` prefix path intentionally removed — any remaining prefix-probe tests that expect dual paths now correctly fail and were migrated to slash-only.

## Work Unit Evidence

| Evidence | Value |
|----------|-------|
| Focused test command | `uv run pytest tests/test_setup_modules_coverage.py tests/test_help_slash_only.py tests/test_zero_hybrid_guard.py tests/test_s1_verify_deltas.py tests/test_dice_rename.py tests/test_s2d1_context_typing_chars.py -q --no-cov` → 93 passed (see targeted suite); `uv run pytest -q --no-cov` → 2973 passed |
| Runtime harness | `uv run ty check` → All checks passed; `uvx prek run --all-files --no-progress` → 9 hooks Passed (ty, ruff, gga); `uv run pytest --cov=bot --cov-fail-under=80 -q` → 80.23% >=80 |
| Rollback boundary | `bot/utils/checks.py` (slash-only wrappers) + `bot/cogs/setup.py` (`@is_admin` line) + `bot/cogs/ocio.py` (`name="dice"` + `dados` compat property) + `bot/cogs/core.py` (`_resolve_prefix`) + `docs/MANUAL.md` (7 sections) + `openspec/specs/*` (12 source-truth edits) — no migration, no ledger mutation, no `TicketsCog.on_message` body change |

## Remaining Tasks
- [ ] Verify generation-6 attempt (sdd-verify 43/43 105/105) — not archived; leave verify to next step.

## Next
remediate-7 complete. Awaiting `sdd-verify` generation 6 against `v1-postrelease-zero` deltas (43/43 105/105) + Strict TDD gate. Do NOT archive from executor.
