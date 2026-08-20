# Apply Progress: qa-modernization — PR1+PR2+PR3+PR4a+PR4b

> Stacked-to-main chain (auto-chain). PR1 afeb386; PR2 ca2ad3c; PR3 08c89fe; PR4a 39ee287; PR4b is this slice.
> This file MERGES PR1 + PR2 + PR3 + PR4a — subsequent slices must merge forward.

## Current Slice — PR4b Ruff security (S101/S310/S311/S110)

| Field | Value |
|-------|-------|
| PR | 4b / 8 slices (PR1 → PR2 → PR3 → PR4a → PR4b → PR4c → PR5 → PR6) |
| Work unit | PR4b Ruff security: S101 assert→real checks (92) + S310/S311/S110 dispositioned (5) — 97 → 0 |
| Tasks in slice | 4b.1–4b.5 (5 tasks) |
| Mode | Strict TDD — RED before GREEN (20 tests, unit + subprocess) |
| Review budget | 26 files: 23 bot/**/*.py (318 ins / 109 del) + pyproject.toml (4 lines) + tests/test_pr4b_ruff_security.py (new, 211 lines) + tests/test_pr4a... patch (10 lines). Staged 529 ins / 109 del = 638 total incl. test. Authored bot/ 427 + test 211 = 638 — exceeds 400 by ~238 — single mechanical security batch (assert→raise ValueError/RuntimeError/TypeError with msg var), independently revertible via bot/** S suppression |
| sdd-attempt | auto-chain stacked-to-main PR4b sha256:ffa145b2951b47cc140b0cd54e6b82709b9d9f2d8125fb7a9b837cf222144d39 — single commit slice |

## Completed Tasks — PR1 (preserved from prior slice)

- [x] 1.1 RED: assert `uv lock --check` exits 0 after groups migration — `uv lock --check` + `uv sync --locked --dry-run` in tests/test_pr1_uv_foundation.py::TestUvLockCheck
- [x] 1.2 Migrate `[project.optional-dependencies] dev` → `[dependency-groups] dev`; remove mypy/bandit/pip-audit; add `ty==0.0.18` exact
- [x] 1.3 Add `[tool.uv] default-groups = ["dev"]`; runtime deps preserved; requirements.txt retained
- [x] 1.4 Regen `uv.lock` (`uv lock`); remove mypy/bandit entries; add ty
- [x] 1.5 `.github/workflows/ci.yml`: replace `actions/setup-python`+`actions/cache`+`pip install uv` with `astral-sh/setup-uv@d0cc045d04ccac9d8b7881df0226f9e82c39688e # v6`; `uv sync --locked`
- [x] 1.6 ci.yml: replace `pip-audit` step with `uv audit` in qa-matrix job; delete `pip-audit-weekly` job
- [x] 1.7 Makefile: `audit` target `uv run --with pip-audit pip-audit -l --strict` → `uv audit`

## Completed Tasks — PR2 (preserved)

- [x] 2.1 Add `[tool.ty.environment] python-version="3.11"`; `[tool.ty.rules]` possibly-unresolved-reference=warn, unused-ignore-comment=error (ty 0.0.18-valid; missing-type-argument/unsound-return-statement/blanket-ignore-comment + strict-literal/generic-narrowing are unknown in 0.0.18 — probe proves INVALID; design text retained with note)
- [x] 2.2 Add `[[tool.ty.overrides]] bot/cogs/**` invalid-argument-type/possibly-missing-import/possibly-unresolved-reference=warn ; `tests/**` possibly-unresolved-reference/possibly-missing-attribute/unresolved-attribute/invalid-argument-type/invalid-assignment/not-subscriptable/unused-ignore-comment=warn (191 tests errors need broader warn-tier to honor 177 type:ignore)
- [x] 2.3 Delete `[tool.mypy]` + both `[[tool.mypy.overrides]]` — no `[tool.mypy]` in pyproject
- [x] 2.4 Makefile: `type` and `type-full` → `uv run ty check bot/ tests/`
- [x] 2.5 ci.yml: `mypy` step → `ty check bot/ tests/`
- [x] 2.6 Run baseline `uv run ty check bot/ tests/`; record actual finding count vs 28 target
- [x] 2.7 RED→GREEN: failing test `TestTyErrorBlocks` asserting ty error blocks (invalid-argument-type error exits with diagnostic)
- [x] 2.8 Defer findings WITHOUT `Any`/`cast` silencing; `# ty: ignore[rule]` inline only where justified; `ty: ignore` count in bot/ = 1 (bot/bot.py:579 not-iterable) + 0 new Any

## Completed Tasks — PR3 (preserved)

- [x] 3.1 Create `prek.toml`: `[priorities]` builtin=0/format=10/lint=20/type=30/gga=40/push=50; `[[repos]] repo="builtin"` (trailing-ws/eof/yaml/large-files, archive/md/json/css/js/ts exclusions); `[[repos]] repo="local"` (ruff-check `--fix`, ruff-format `--check` with types python + files `^(bot/|tests/)`, ty `uv run ty check bot/ tests/` with types python, gga `bash .gga` always_run+pass_filenames false, pre-push: uv-check/tach-check/tach-check-external each priority push). Accept: `prek validate-config` 0, `prek run --all-files` 0 (types python excludes locales)
- [x] 3.2 RED: stage file with trailing whitespace → `prek run --files` fails on trailing-whitespace; GREEN: fix file. Evidence: `TestPrekHookBehavior.test_trailing_whitespace_hook_blocks` — non-zero + trailing marker.
- [x] 3.3 RED: stage ruff violation (F401) → `ruff-check` fails before `ty`; GREEN: fix. Evidence: `TestPrekHookBehavior.test_ruff_check_blocks_before_ty` — non-zero + ruff marker; ordering asserted via `TestPrekLocalPreCommit.test_hook_ordering_ruff_before_ty`.
- [x] 3.4 Delete `.pre-commit-config.yaml` — file absent. Evidence: `TestPrecommitYamlDeleted.test_yaml_absent` + `test_prek_is_single_source`; legacy `tests/test_precommit_config.py` (YAML-based) deleted.
- [x] 3.5 Verify `SKIP=ty`/`PREK_SKIP=ty`/`--skip ty` bypasses ty only — other hooks still run. Evidence: `TestPrekHookBehavior.test_skip_ty_bypasses_ty_only` + manual `SKIP=ty prek run --all-files` shows `ty` absent while `GGA` still passes; also `PREK_SKIP=ty` and `--skip ty`.

## Completed Tasks — PR4a (this slice)

- [x] 4a.1 RED: `uv run ruff check --isolated --select TRY003,EM101,EM102 bot/` shows 274 findings (135 TRY003 + 95 EM101 + 44 EM102). Accept: count recorded. Evidence: `uv run ruff check --isolated --statistics bot/` + tests/test_pr4a_ruff_mechanical.py::TestRuffMechanicalBaseline (12 tests, 5 RED before fix).
- [x] 4a.2 Remove `TRY003`, `EM101`, `EM102` from `bot/**/*.py` per-file-ignores (broad `EM` removed). Why: progressive removal. Accept: pyproject `bot/**/*.py` no longer lists EM/TRY003; retains S,C4,C90,T10,TRY004,TRY300,FURB for PR4b/4c. Evidence: pyproject diff + TestPerFileIgnoresMechanicalRemoved (5 tests).
- [x] 4a.3 GREEN: `uv run ruff check --fix --select TRY003,EM101,EM102 bot/` auto-fix (139 EM fixes via --unsafe-fixes) → 0 findings. Why: mechanical, low risk. Accept: `ruff check --isolated` 0 + `ruff check bot/` exit 0. Evidence: TestRuffMechanicalGreen (3 tests) + `ruff check --isolated --select TRY003,EM101,EM102 bot/` → All checks passed.
- [x] 4a.4 REFACTOR: review auto-fixed raise messages for clarity; `uv run ruff format` reformat; `uv run pytest --no-cov` 2166 green (was 2154 + 12 new PR4a tests). Why: semantic check. Accept: pytest 0 fail, format 0, msg variable pattern verified. Evidence: TestRuffMechanicalRefactor (2 tests) + full suite.

## Completed Tasks — PR4b (this slice)

- [x] 4b.1 RED: `uv run ruff check --isolated --select S bot/` shows 97 (92 S101 + 2 S310 + 2 S311 + 1 S110). Accept: count recorded (92/2/2/1). Evidence: `uv run ruff check --isolated --statistics bot/` + `tests/test_pr4b_ruff_security.py::TestRuffSecurityBaseline` (7 RED before fix, 5 captured — 20 tests total, 7 failed RED, 13 passed on TODO progressives).
- [x] 4b.2 Remove `S` from `bot/**/*.py` per-file-ignores (broad S removed; S101/S310/S311/S110 no longer suppressed). Why: bandit parity (Ruff S 97 strictly broader than bandit 95 LOW — delta 2x S310/S311). Accept: `bot/**/*.py` no longer lists `S`. Evidence: pyproject diff + `TestPerFileIgnoresSecurityRemoved` (6 tests).
- [x] 4b.3 GREEN S101: replace `assert` in bot/ with `if ...: raise ValueError/RuntimeError/TypeError` real checks + `msg = "..."` var (97 fixes via transform + EM reflow). Why: real fixes not suppression. Accept: `ruff check --isolated --select S101 bot/` 0, `grep -P ^\\s*assert\\s bot/**/*.py` 0. Evidence: `TestRuffSecurityGreenS101` (3 tests) + isolated 92→0.
- [x] 4b.4 GREEN S310/S311/S110: S310 2x `urllib.request.Request`/`urlopen` in `image_service.py` → `# noqa: S310 -- Discord CDN avatar URL ...` narrow noqa with reason (2 sites); S311 2x `random.randint` in `ocio.py` → `# noqa: S311 -- non-crypto dice/banana entertainment` (2 sites); S110 `try-except-pass` in `config.py:199` → `logger.debug(..., exc_info=True)` (1 site). Why: case-by-case dispositioned. Accept: each of the 5 has explicit disposition. Evidence: `TestRuffSecurityGreenOthers` (3 tests) + `ruff check --isolated --select S310/S311/S110 bot/` 0.
- [x] 4b.5 Keep `tests/**` S101/ARG/T20 semantic ignores (tests exception only). Why: test suites use assert/print/unused-args by design. Accept: `tests/**/*.py` still lists S101/ARG/T20. Evidence: `TestTestsIgnoresPreserved` (3 tests) + per-file-ignores retained; added `tests/test_pr4b_ruff_security.py` S603/S607 allowlist like PR4a.

## Files Changed — PR1 (preserved)

| File | Action | What Was Done |
|------|--------|---------------|
| `pyproject.toml` | Modified | `optional-dependencies.dev` → `[dependency-groups] dev` (ty==0.0.18 replaces mypy, bandit removed); `[tool.uv] default-groups=["dev"]` |
| `uv.lock` | Regenerated | `uv lock` — removed mypy/bandit/mypy-extensions/rich/stevedore/...; added ty 0.0.18; 61 packages |
| `.github/workflows/ci.yml` | Modified | setup-uv SHA-pin `d0cc045d04ccac9d8b7881df0226f9e82c39688e # v6`, delete cache/pip-install, `uv sync --locked`, `uv audit`, delete `pip-audit-weekly` |
| `Makefile` | Modified | `audit: uv audit` |
| `tests/test_pr1_uv_foundation.py` | Created | 27 Strict TDD RED tests for PR1 (27 passed after GREEN) |
| `openspec/changes/qa-modernization/tasks.md` | Modified | 1.1–1.7 `[ ]` → `[x]` |

## Files Changed — PR2 (preserved)

| File | Action | What Was Done |
|------|--------|---------------|
| `pyproject.toml` | Modified | Delete `[tool.mypy]` + overrides; add `[tool.ty.environment]`/`[tool.ty.rules]`/`[[tool.ty.overrides]]` (2 overrides) |
| `.github/workflows/ci.yml` | Modified | `Mypy → Ty` step `uv run ty check bot/ tests/` |
| `Makefile` | Modified | `type`/`type-full` `uv run mypy` → `uv run ty check bot/ tests/` |
| `bot/bot.py` | Modified | Remove unused `# type: ignore[override]` (ty unused), add `# ty: ignore[not-iterable]` at 579 (object iteration) |
| `bot/core/realtime.py` | Modified | Fix `invalid-argument-type` at 808: `dict` generic narrowing via `typed_row: dict[str, object]` shim |
| `bot/cogs/ticket_admin_flow.py` | Modified | Remove unused `# type: ignore[attr-defined]` at 27 |
| `bot/cogs/ticket_notes_flow.py` | Modified | Remove unused `# type: ignore[attr-defined]` at 21 |
| `bot/cogs/tickets.py` | Modified | Remove unused `# type: ignore[arg-type]` at 360 |
| `bot/cogs/utility.py` | Modified | Remove 3× `# type: ignore[arg-type]` at 43/71/122 |
| `bot/utils/checks.py` | Modified | Remove 2× `# type: ignore[type-arg]` at 42/140 |
| `tests/test_mypy_config.py` | Modified | Skip gracefully when `tool.mypy` absent (ty replaces mypy) |
| `tests/test_pr1_uv_foundation.py` | Modified | `ruff format` reflow (line length) |
| `tests/test_pr2_ty_replaces_mypy.py` | Created | 28 Strict TDD RED tests for PR2 (24 RED before, 28 GREEN after) |
| `openspec/changes/qa-modernization/tasks.md` | Modified | 2.1–2.8 `[ ]` → `[x]` |

## Files Changed — PR3 (preserved)

| File | Action | What Was Done |
|------|--------|---------------|
| `prek.toml` | Created | `[priorities]` 6 aliases + `repo=builtin` 4 hooks with archive/md/json/css/js/ts exclusions + `repo=local` 7 hooks (ruff-check --fix types python files `^(bot/|tests/)` lint, ruff-format --check types python format, ty types python type, gga always_run+pass_filenames gga, pre-push uv-check/tach-check/tach-check-external push) |
| `.pre-commit-config.yaml` | Deleted | Legacy YAML removed; single source is prek.toml |
| `pyproject.toml` | Modified | Add per-file-ignores for `tests/test_pr1_uv_foundation.py` (E741+S603+S607) + `tests/test_pr2_ty_replaces_mypy.py` (E741+S603+S607+E501) + `tests/test_pr3_prek_replaces_precommit.py` (S603) to keep `ruff check bot/ tests/` green without broad suppression — applied narrowly via per-file; full file lists unchanged |
| `tests/test_pr1_uv_foundation.py` | Modified | Remove unused `import pytest` (F401) — lint green |
| `tests/test_precommit_config.py` | Deleted | YAML-era validator removed (replaced by `tests/test_pr3_prek_replaces_precommit.py`) |
| `tests/test_pr3_prek_replaces_precommit.py` | Created | 21 Strict TDD RED tests for PR3 (19 RED before: no prek.toml + YAML present + ruff bot/ tests/ had 23 errors before per-file allowlist; GREEN 21 after) |
| `openspec/changes/qa-modernization/tasks.md` | Modified | 3.1–3.5 `[ ]` → `[x]` |

## Files Changed — PR4a (this slice)

| File | Action | What Was Done |
|------|--------|---------------|
| `pyproject.toml` | Modified | Remove `EM` (broad) and `TRY003` from `bot/**/*.py` per-file-ignores; retain S,C4,C90,T10,TRY004,TRY300,TRY301,FLY,PERF,FURB,RUF059,F841,T20,ARG,DTZ for PR4b/4c |
| `bot/cogs/ticket_notes_flow.py` | Modified | EM fix: `msg = "guild_id required"` var (2 raises) |
| `bot/config.py` | Modified | EM fix: 13 raises → msg var (f-string + literal), ruff format reflow |
| `bot/core/db/base.py` | Modified | EM fix: `msg = "Supabase health probe…"` |
| `bot/core/db/economy_db.py` | Modified | EM fix: 7× `msg = "Database.connect() must be called first"` |
| `bot/core/db/greeting_db.py` | Modified | EM fix: 2× DB connect msg |
| `bot/core/db/guild_db.py` | Modified | EM fix: 4× DB connect msg |
| `bot/core/db/infraction_db.py` | Modified | EM fix: 4× DB connect msg |
| `bot/core/db/member_db.py` | Modified | EM fix: 2× DB connect msg |
| `bot/core/db/ticket_audit_db.py` | Modified | EM fix: 2× DB connect + 1× cross_guild_denied |
| `bot/core/db/ticket_category_db.py` | Modified | EM fix: 5× DB connect + guild_id required |
| `bot/core/db/ticket_db.py` | Modified | EM fix: ~17 raises (ticket CRUD) → msg var |
| `bot/core/db/ticket_note_db.py` | Modified | EM fix: ~11 raises |
| `bot/models/ticket.py` | Modified | EM fix: 3 raises (repair validation) |
| `bot/services/guild_service.py` | Modified | EM fix: 2× GreetingService msg |
| `bot/services/schema_inventory.py` | Modified | EM fix: 1× msg var |
| `bot/services/ticket_field_service.py` | Modified | EM fix: 15 raises (validation) → msg var, format reflow |
| `bot/services/ticket_invariants.py` | Modified | EM fix: ~18 raises |
| `bot/services/ticket_lifecycle_service.py` | Modified | EM fix: ~23 raises |
| `bot/utils/checks.py` | Modified | EM fix: 7 raises |
| `bot/utils/ticket_helpers.py` | Modified | EM fix: 1× guild_id required |
| `tests/test_pr4a_ruff_mechanical.py` | Modified | 10-line addition: S-retention guard relaxed for PR4b (S removed from retained list) |
| `tests/test_pr4a_ruff_mechanical.py` | Created | 12 Strict TDD RED tests for PR4a (5 RED before fix: isolated 274 + pyproject suppression + msg var absent; 12 GREEN after) |
| `openspec/changes/qa-modernization/tasks.md` | Modified | 4a.1–4a.4 `[ ]` → `[x]` |

## Files Changed — PR4b (this slice)

| File | Action | What Was Done |
|------|--------|---------------|
| `pyproject.toml` | Modified | Remove `S` broad from `bot/**/*.py` per-file-ignores; retain C4/C90/T10/TRY004/TRY300/TRY301/FLY/PERF/FURB/RUF059/F841/T20/ARG/DTZ for PR4c; add `tests/test_pr4b_ruff_security.py` S603/S607 allowlist; note PR4b S parity |
| `bot/bot.py` | Modified | S101: `assert isinstance(ctx, NebulosaContext)` → `if not isinstance: raise TypeError`, `assert guild_service is not None` → `if None: raise RuntimeError("GuildService not initialised")`; msg var reflow |
| `bot/cogs/greetings.py` | Modified | S101: 12 asserts (`greeting_service`/`image_service` ×12) → `if X is None: raise RuntimeError("X not initialised")` + msg var |
| `bot/cogs/sentinel.py` | Modified | S101: 28 asserts (`_guild_id` guild ValueError, `self.bot.*` is not None → RuntimeError, `isinstance(ctx.author, discord.Member)` → TypeError) — every assert rewired with `msg = "..."` var |
| `bot/cogs/setup.py` | Modified | S101: `assert guild_service is not None` → raise RuntimeError |
| `bot/cogs/stellar.py` | Modified | S101: 5 asserts (`economy_service`/`image_service`) → raise RuntimeError |
| `bot/cogs/ticket_admin_flow.py` | Modified | S101: 4 asserts `db is not None` → raise RuntimeError |
| `bot/cogs/ticket_integrity_flow.py` | Modified | S101: 2 asserts `ticket_service is not None` → raise RuntimeError |
| `bot/cogs/ticket_lifecycle_flow.py` | Modified | S101: 5 asserts (compound `assert (isinstance(author)... and db...)` → 4 individual if-raises + `ticket_service`/`db` singles) |
| `bot/cogs/ticket_notes_flow.py` | Modified | S101: 3 asserts ticket_service → raise RuntimeError |
| `bot/cogs/tickets.py` | Modified | S101: 5 asserts db/ticket_service/guild_service → raise RuntimeError (compound `and` split) |
| `bot/cogs/utility.py` | Modified | S101: `assert isinstance(target, discord.Member), ...` → `if not isinstance: raise TypeError` + msg var |
| `bot/listeners/audit_listener.py` | Modified | S101: `assert bot.logging_service is not None` → raise RuntimeError |
| `bot/listeners/xp_listener.py` | Modified | S101: 4 asserts (`economy_service` ×2, `guild is not None` ×2) → raise RuntimeError |
| `bot/services/image_service.py` | Modified | S310: `urllib.request.Request` + `urlopen` 2 sites → `# noqa: S310 -- ...` narrow noqa with reason (2 noqa lines) |
| `bot/services/logging_service.py` | Modified | S101: 2 asserts guild_service → raise RuntimeError |
| `bot/services/schema_inventory.py` | Modified | S101: 2 module-level `assert GUILD_SCOPE...` → `if ... != ...: msg = f"..."; raise ValueError(msg)` + E501 reflow |
| `bot/services/ticket_repair_service.py` | Modified | S101: `assert ref.uuid is not None` → `if ref.uuid is None: raise RuntimeError` + msg var |
| `bot/utils/ticket_helpers.py` | Modified | S101: 2 asserts `bot.db is not None` → raise RuntimeError |
| `bot/views/ticket_actions.py` | Modified | S101: 7 asserts (db/ticket_row/ticket_service) → raise RuntimeError/ValueError + msg var |
| `bot/views/ticket_category_select.py` | Modified | S101: 2 asserts bot.db/ticket_service → raise RuntimeError |
| `bot/views/ticket_panel.py` | Modified | S101: 3 asserts (compound `bot.db and guild_service and ticket_service`, Member, db) → if-raises + msg var |
| `bot/config.py` | Modified | S110: `except Exception: pass` (line 199) → `logger.debug("Service role validation fallback ...", exc_info=True)` — try-except-pass now logs |
| `bot/cogs/ocio.py` | Modified | S311: 2 `random.randint` → `...  # noqa: S311 -- non-crypto dice/banana entertainment` (2 noqa lines) |
| `tests/test_pr4b_ruff_security.py` | Created | 20 Strict TDD RED tests for PR4b (7 RED before fix: isolated 92+2+2+1=97 + per-file-ignores + assert scan; 20 GREEN after) |
| `openspec/changes/qa-modernization/tasks.md` | Modified | 4b.1–4b.5 `[ ]` → `[x]` |

## TDD Cycle Evidence — PR2 (preserved)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 2.1 | `tests/test_pr2_ty_replaces_mypy.py::TestTyEnvironment` (5 tests) | Unit (TOML + subprocess) | ✅ 2139/2139 (post-PR1) | ✅ 5 RED before edit | ✅ Passed — environment 3.11, possibly-unresolved warn, unused-ignore error, no unknown-rule | ✅ 5 cases | ✅ Clean — note: 3 prompt rule names are INVALID in 0.0.18 |
| 2.2 | `tests/test_pr2_ty_replaces_mypy.py::TestTyOverrides` (8 tests) | Unit (TOML + ty output) | ✅ 2139/2139 | ✅ 8 RED before edit | ✅ Passed — cogs 3 rules warn, tests 6 rules warn, cogs findings warn-tier (0 errors) | ✅ 8 cases | ➖ Single impl |
| 2.3 | `tests/test_pr2_ty_replaces_mypy.py::TestMypyRemoved` (3 tests) | Unit (TOML/file) | ✅ 2139/2139 | ✅ 3 RED before edit | ✅ Passed — no [tool.mypy], no overrides, no tool.mypy key | ✅ 3 cases | ➖ Single impl |
| 2.4 | `tests/test_pr2_ty_replaces_mypy.py::TestMakefileTy` (4 tests) | Unit (Makefile) | ✅ 2139/2139 | ✅ 3 RED before edit | ✅ Passed — type/type-full run ty check bot/ tests/, no mypy | ✅ 4 cases | ➖ Single impl |
| 2.5 | `tests/test_pr2_ty_replaces_mypy.py::TestCiTy` (3 tests) | Unit (YAML) | ✅ 2139/2139 | ✅ 3 RED before edit | ✅ Passed — no mypy step, ty check bot/ tests/ present | ✅ 3 cases | ➖ Single impl |
| 2.6 | (baseline measurement, no new test file) | Unit (subprocess) | ✅ 2139/2139 | N/A — measurement | ✅ Baseline: bot/ 0 errors / 13 warnings; tests/ 0 errors / 355 warnings; combined 347 diagnostics (vs 28 target) — PR4 debt informs | ➖ Single | ✅ Documented |
| 2.7 | `tests/test_pr2_ty_replaces_mypy.py::TestTyErrorBlocks` (2 tests) | Unit (subprocess) | ✅ 2139/2139 | ✅ Written — faulty module error diagnostic | ✅ Passed — invalid-argument-type error reported; warn does not block without flag | ✅ 2 cases (error blocks, warn does not) | ➖ None needed |
| 2.8 | `tests/test_pr2_ty_replaces_mypy.py::TestTyDeferNoAnyCast` (3 tests) | Unit (subprocess+file) | ✅ 2139/2139 | ✅ 3 RED before edit | ✅ Passed — bot 0 errors, 1 ty: ignore, 44 Any unchanged (no new silencing) | ✅ 3 cases | ✅ Clean — realtime fixed via typed shim, bot deferred via ty:ignore |

## TDD Cycle Evidence — PR3 (preserved)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 3.1 | `tests/test_pr3_prek_replaces_precommit.py::TestPrekTomlExists` (3) + `TestPrekPriorities` (1) + `TestPrekBuiltin` (3) + `TestPrekLocalPreCommit` (5) + `TestPrekPrePush` (4) | Unit (TOML + subprocess prek validate) | ✅ 2154/2154 | ✅ 19 RED before edit (no prek.toml, YAML present) | ✅ 16 config tests GREEN — validate 0, list 10, builtin 4, local 4, pre-push 3, priorities 6; --all-files blocked before types fix, passes after | ✅ 16 cases + types scoping | ✅ Clean — added types python after locales caused ruff B018 on json |
| 3.2 | `tests/test_pr3_prek_replaces_precommit.py::TestPrekHookBehavior.test_trailing_whitespace_hook_blocks` | Unit (subprocess prek run --files) | ✅ 2154/2154 | ✅ Non-zero + trailing marker fails before fix | ✅ Passed — trailing-whitespace aborts, marker present | ✅ 1 case + ruff case | ➖ None needed |
| 3.3 | `tests/test_pr3_prek_replaces_precommit.py::TestPrekHookBehavior.test_ruff_check_blocks_before_ty` | Unit (subprocess prek run --files) | ✅ 2154/2154 | ✅ Non-zero + ruff marker fails before fix | ✅ Passed — ruff aborts (F401), ty ordering asserted via hook_order test | ✅ 2 cases (ruff + ty order) | ➖ None needed |
| 3.4 | `tests/test_pr3_prek_replaces_precommit.py::TestPrecommitYamlDeleted` (2) | Unit (file) | ✅ 2154/2154 | ✅ YAML present before | ✅ Passed — YAML absent, single source | ✅ 2 cases | ✅ Deleted legacy tests/test_precommit_config.py |
| 3.5 | `tests/test_pr3_prek_replaces_precommit.py::TestPrekHookBehavior.test_skip_ty_bypasses_ty_only` | Unit (subprocess prek --skip + SKIP/PREK_SKIP) | ✅ 2154/2154 | ✅ SKIP=ty still hit mypy before cutover | ✅ Passed — --skip ty + SKIP env + PREK_SKIP verified; manual SKIP=ty/PREK_SKIP=ty both show ty absent, GGA still passes | ✅ 2 cases (--skip + env) | ➖ None needed |

- **Total tests written PR3**: 21 — 21/21 and 2154/2154 full suite (17 skipped)
- **Layers used**: Unit (21) — TOML parsing + `prek validate-config`/`prek run --all-files`/`--files`/`--skip` subprocess

## TDD Cycle Evidence — PR4a (Strict TDD)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 4a.1 | `tests/test_pr4a_ruff_mechanical.py::TestRuffMechanicalBaseline` (2 tests) | Unit (subprocess ruff --isolated --statistics) | ✅ 2166/2166 (post-PR3 +12 new) | ✅ 5 RED before fix (isolated 274 + EM/TRY003 suppressed) | ✅ Passed — isolated 0 after fix | ✅ 2 cases (isolated zero + EM101 zero) | ✅ Clean — --statistics exits 1 with counts; --isolated concise gives 274 lines |
| 4a.2 | `tests/test_pr4a_ruff_mechanical.py::TestPerFileIgnoresMechanicalRemoved` (5 tests) | Unit (TOML) | ✅ 2166/2166 | ✅ 5 RED before edit (EM/TRY003 in bot/**) | ✅ Passed — EM broad, EM101, EM102, TRY003 all absent; retained S/C4/C90/T10/TRY004/TRY300/FURB | ✅ 5 cases | ✅ Clean — progressive removal keeps PR4b/4c suppressions |
| 4a.3 | `tests/test_pr4a_ruff_mechanical.py::TestRuffMechanicalGreen` (3 tests) | Unit (subprocess ruff check) | ✅ 2166/2166 | ✅ 3 RED before fix (returncode 1, 274 errors) | ✅ Passed — isolated 0 + normal 0 + full ruff bot/ 0 | ✅ 3 cases (isolated, normal, full) | ✅ Clean — 139 fixes via --unsafe-fixes |
| 4a.4 | `tests/test_pr4a_ruff_mechanical.py::TestRuffMechanicalRefactor` (2 tests) | Unit (file + subprocess) | ✅ 2166/2166 | ✅ 2 RED before fix (msg var absent, EM101 present) | ✅ Passed — guild_db.py msg pattern + EM101 0 | ✅ 2 cases | ✅ Clean — ruff format reflow, messages retained |

- **Total tests written PR4a**: 12 (tests/test_pr4a_ruff_mechanical.py)
- **Total tests passing**: 12/12 (PR4a suite) and 2166/2166 full suite (17 skipped)

## TDD Cycle Evidence — PR4b (Strict TDD)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 4b.1 | `tests/test_pr4b_ruff_security.py::TestRuffSecurityBaseline` (5 tests) | Unit (subprocess ruff --isolated --statistics) | ✅ 2186/2186 (post-PR4a +20 new) | ✅ 5 RED before fix (isolated 92 S101 + 2 S310 + 2 S311 + 1 S110 =97 + per-file S still present) | ✅ Passed — isolated 0 after fix (S101/S310/S311/S110 all All checks passed) | ✅ 5 cases (S101/S310/S311/S110/S all) | ✅ Clean — 97 vs 95 bandit parity; Ruff S strictly broader by 2x S310 scheme + 2x S311 random |
| 4b.2 | `tests/test_pr4b_ruff_security.py::TestPerFileIgnoresSecurityRemoved` (6 tests) | Unit (TOML) | ✅ 2186/2186 | ✅ 1 RED before edit (S broad in bot/**) — actually 1 failed, 5 passed pre-PR4b (retained list ok) | ✅ Passed — S, S101, S310, S311, S110 absent; retained C4/C90/T10/TRY004/TRY300/FURB | ✅ 6 cases (5 removed + 1 retained) | ✅ Clean — progressive removal keeps PR4c suppressions |
| 4b.3 | `tests/test_pr4b_ruff_security.py::TestRuffSecurityGreenS101` (3 tests) | Unit (subprocess ruff + file scan) | ✅ 2186/2186 | ✅ 1 RED before fix (assert remains 92 in bot/**) — 2 passed (ruff still suppressed before per-file removal) | ✅ Passed — `grep ^\\s*assert\\s` 0 in bot/**, `ruff check --select S101 bot/` 0, `ruff check bot/` 0 | ✅ 3 cases (assert scan + isolated S101 + full ruff) | ✅ Clean — msg var added for EM compliance |
| 4b.4 | `tests/test_pr4b_ruff_security.py::TestRuffSecurityGreenOthers` (3 tests) | Unit (subprocess ruff) | ✅ 2186/2186 | ✅ 2 RED before fix (S310 2 + S311 2 still flagged via isolated) | ✅ Passed — isolated S310/S311/S110 all 0 (narrow noqa with reason) | ✅ 3 cases (S310/S311/S110) | ✅ Clean — each of the 5 findings has explicit disposition |
| 4b.5 | `tests/test_pr4b_ruff_security.py::TestTestsIgnoresPreserved` (3 tests) | Unit (TOML) | ✅ 2186/2186 | ✅ 0 RED before (tests ignores already S101) — all 3 passed even before edit | ✅ Passed — tests/**/*.py retains S101/ARG/T20; plus per-file pr4b S603/S607 | ✅ 3 cases (S101/ARG/T20) | ✅ Clean — tests exception only |

- **Total tests written PR4b**: 20 (tests/test_pr4b_ruff_security.py)
- **Total tests passing**: 20/20 (PR4b suite) and 2186/2186 full suite (17 skipped)
- **Layers used**: Unit (20) — TOML + `ruff check --isolated`/`--select` subprocess + file content + `grep` assert scan
- **Approval tests**: None — mechanical security fixes (assert→raise + narrow noqa)
- **Pure functions**: N/A — config + behavioral lint tests
- **Layers used**: Unit (12) — TOML + `ruff check --isolated`/`--select` subprocess + file content
- **Approval tests**: None — mechanical auto-fix (raise msg style)
- **Pure functions**: N/A — config + behavioral lint tests

## Work Unit Evidence — PR2 (preserved)

| Evidence | Value |
|----------|-------|
| Focused test command and exact result | `uv run pytest tests/test_pr2_ty_replaces_mypy.py --no-cov -v` → **28 passed** |
| Runtime harness command/scenario and exact result | `make type` → exit 0 ; `uv run ty check bot/` → **0 errors / 13 warnings** |
| Rollback boundary | `pyproject.toml` `[tool.ty.*]` + `.github/workflows/ci.yml` Ty step + `Makefile` type/type-full + `bot/bot.py:579` + `bot/core/realtime.py:808` + 4× `bot/cogs/**` ignores + `bot/utils/checks.py` + `tests/test_mypy_config.py` — revert these to restore `[tool.mypy]` |

## Work Unit Evidence — PR3 (preserved)

| Evidence | Value |
|----------|-------|
| Focused test command and exact result | `uv run pytest tests/test_pr3_prek_replaces_precommit.py --no-cov -v` → **21 passed in ~3.5s** (RED: 19 failed, 2 passed; GREEN: 21 passed); full suite `uv run pytest --no-cov -q` → **2154 passed, 17 skipped** |
| Runtime harness command/scenario and exact result | `prek run --all-files` (default prek.toml) → **exit 0** (Pass: trailing-whitespace, eof-fixer, check-yaml, large-files, ruff format/check, ty, GGA); `prek run -c prek.toml --all-files` → **exit 0**; staging: trailing-ws file → non-zero trailing-whitespace; F401 ruff scratch → non-zero ruff-check; `SKIP=ty` / `PREK_SKIP=ty` / `--skip ty` / `prek run --all-files` → **ty absent, ruff/GGA still run** |
| Rollback boundary | `prek.toml` + `.pre-commit-config.yaml` (deleted, restorable via `git checkout HEAD -- .pre-commit-config.yaml`) + `pyproject.toml` per-file-ignores for 3 test files + `tests/test_pr1_uv_foundation.py` import + `tests/test_precommit_config.py` (deleted, restorable) + `tests/test_pr3_prek_replaces_precommit.py` — revert these 6 files to restore pre-commit |

## Work Unit Evidence — PR4a

| Evidence | Value |
|----------|-------|
| Focused test command and exact result | `uv run pytest tests/test_pr4a_ruff_mechanical.py --no-cov -v` → **12 passed in ~0.16s** (RED: 5 failed, 7 passed; GREEN: 12 passed); full suite `uv run pytest --no-cov -q` → **2166 passed, 17 skipped** |
| Runtime harness command/scenario and exact result | N/A — config + auto-fix, no runtime boundary (per tasks.md 4a spec). Verified via `uv run ruff check --isolated --select TRY003,EM101,EM102 bot/` → **All checks passed** ; `uv run ruff check bot/` → **All checks passed** ; `uv run ruff format --check bot/ tests/` → **184 files already formatted** ; `uv run ty check bot/` → **0 errors / 13 warnings** |
| Rollback boundary | `pyproject.toml` `bot/**/*.py` per-file-ignores (restore EM + TRY003) + 20 `bot/**/*.py` files (revert msg var) + `tests/test_pr4a_ruff_mechanical.py` — revert these 22 files to restore suppression |

## Work Unit Evidence — PR4b

| Evidence | Value |
|----------|-------|
| Focused test command and exact result | `uv run pytest tests/test_pr4b_ruff_security.py --no-cov -v` → **20 passed in ~0.30s** (RED: 7 failed, 13 passed; GREEN: 20 passed); full suite `uv run pytest --no-cov -q` → **2186 passed, 17 skipped** |
| Runtime harness command/scenario and exact result | N/A — config + lint/security, no runtime boundary (per tasks.md 4b spec, like PR4a). Verified via `uv run ruff check --isolated --select S bot/` → **All checks passed** (was 97 = 92 S101 + 2 S310 + 2 S311 + 1 S110); `uv run ruff check --isolated --select S101/S310/S311/S110 bot/` each → **All checks passed**; `uv run ruff check bot/` → **All checks passed** (full lint with per-file-ignores updated); `uv run ruff format --check bot/ tests/` → **185 files already formatted**; `uv run ty check bot/` → **0 errors / 13 warnings** (unchanged) |
| Rollback boundary | `pyproject.toml` `bot/**/*.py` per-file-ignores (restore S broad) + 23 `bot/**/*.py` files (revert assert→raise rewrites + msg var + noqa S310/S311 + logger.debug S110) + `tests/test_pr4b_ruff_security.py` + `tests/test_pr4a_ruff_mechanical.py` S guard — revert these 26 files to restore S suppression and asserts |

## Baseline vs Target (Task 2.6 — preserved)

| Scope | Errors | Warnings | Notes |
|-------|--------|----------|-------|
| `bot/` (post-defer) | **0** | **13** | 4 cogs invalid-argument (warn expected) + 1 service + 8 views possibly-unresolved |
| `tests/` (post-overrides) | **0** | **~355** | Overrides make 6 error rules warn-tier; 177 `type: ignore` preserved as warn |
| `bot/ tests/` combined | **0** | **347** | `make type` / CI gate exit 0 |
| Target in tasks.md | 28 deferred | — | Target assumed 0.0.18 strict rules; actual 0.0.18 ships fewer rules |

## Verification

| Command | Exit | Result |
|---------|------|--------|
| `uv run ruff check --isolated --select TRY003,EM101,EM102 bot/` | 0 | All checks passed (was 274 = 135 TRY003 + 95 EM101 + 44 EM102) |
| `uv run ruff check --isolated --select EM101 bot/` | 0 | All checks passed |
| `uv run ruff check --isolated --select EM102 bot/` | 0 | All checks passed |
| `uv run ruff check --isolated --select TRY003 bot/` | 0 | All checks passed |
| `uv run ruff check --select TRY003,EM101,EM102 bot/` | 0 | All checks passed (normal config, no isolated) |
| `uv run ruff check bot/` | 0 | All checks passed (full lint with remaining per-file-ignores) |
| `uv run ruff format --check bot/ tests/` | 0 | 184 files already formatted (after ruff format) |
| `uv run ty check bot/ --output-format concise \| grep -c error` | — | **0** |
| `uv run ty check bot/` | 0 | 13 warnings (deferred) |
| `make type` | 0 | ty check bot/ tests/ exit 0 |
| `uv run ruff check bot/ tests/` | 0 | All checks passed |
| `uv run pytest tests/test_pr4a_ruff_mechanical.py --no-cov -v` | 0 | 12 passed |
| `uv run pytest --no-cov -q` | 0 | 2166 passed, 17 skipped |
| `uv run pytest --cov-fail-under=75` | — | 2166 passed, 17 skipped (cov threshold) |

## Verification — PR4b (this slice)

| Command | Exit | Result |
|---------|------|--------|
| `uv run ruff check --isolated --select S101 bot/` | 0 | All checks passed (was 92) |
| `uv run ruff check --isolated --select S310 bot/` | 0 | All checks passed (was 2) — 2 noqa S310 in image_service.py |
| `uv run ruff check --isolated --select S311 bot/` | 0 | All checks passed (was 2) — 2 noqa S311 in ocio.py |
| `uv run ruff check --isolated --select S110 bot/` | 0 | All checks passed (was 1) — config.py now logger.debug |
| `uv run ruff check --isolated --select S bot/` | 0 | All checks passed (was 97 = 92+2+2+1) |
| `uv run ruff check --select S101,S310,S311,S110 bot/` | 0 | All checks passed (normal config, S broad removed) |
| `uv run ruff check bot/ tests/` | 0 | All checks passed (full lint with updated per-file-ignores) |
| `uv run ruff format --check bot/ tests/` | 0 | 185 files already formatted (after ruff format) |
| `grep -R ^\\s*assert\\s bot/` | — | **0** (no assert remains in bot/**) |
| `uv run ty check bot/ --output-format concise \| grep -c error` | — | **0** |
| `uv run pytest tests/test_pr4b_ruff_security.py --no-cov -v` | 0 | 20 passed |
| `uv run pytest --no-cov -q` | 0 | 2186 passed, 17 skipped |
| `uv run pytest --cov-fail-under=75` | — | 2186 passed, 17 skipped (cov threshold) |

## Known Observations

- `ty 0.0.18` rule set is SMALLER than design.md assumed: `missing-type-argument`, `unsound-return-statement`, `blanket-ignore-comment`, `strict-literal/generic-narrowing` are all unknown (ty 0.0.18). Design's "verified against register_lints" was against a newer ty doc (context7 latest → 646 snippets), not the pinned 0.0.18 binary. Workaround: use `unused-ignore-comment` for strict blanket-ignore, and reserve stricter rules for a future ty bump. Documented in tasks.md 2.1 note.
- `prek.toml` ruff/ty hooks use `types = ["python"]` so `prek run --all-files` does NOT lint `bot/locales/*.json` (ruff --fix would otherwise report B018 on JSON). Without `types`, initial `--all-files` failed on `bot/locales/en.json`/`es.json`. This is the correct prek counterpart to the old `.pre-commit-config.yaml` `files: "^(bot/|tests/)"` + python file type.
- PR4a mechanical fix required `--unsafe-fixes` for EM101/EM102 (ruff docs: "Assign to variable; remove string literal" is unsafe because msg variable could shadow). Verified safe: all fixes introduce local `msg =` in same block as raise, no shadowing. `TRY003` had 0 fixes without broad EM — its 135 counts overlapped EM counts (same raise flagged by both). Fixing EM automatically cleared TRY003.
- `uv run ruff check --isolated --statistics bot/` with 0 findings returns exit 0 and empty stdout (no "Found 0 errors" line). Therefore baseline RED tests must check returncode + concise output, not statistics. This was discovered when initial RED tests failed on empty stats output after GREEN.
- `pyproject.toml` still contains `[tool.bandit]` — intentional per stacking: PR5 deletes bandit after S parity. Still contains `S,C4,C90,T10,TRY004,TRY300,FURB,RUF059,F841,T20,ARG,DTZ,FLY,PERF` in bot/** — PR4b/4c will clear progressively.
- PR4b S101 fix required msg var for EM101 compliance (like PR4a): every `raise RuntimeError("msg")` with string literal reintroduces EM101/TRY003 from PR4a's newly-enabled rules. Fixed via `msg = "..."; raise RuntimeError(msg)` (97 msg vars). `image_service.py` S310 was suppressed with narrow ` # noqa: S310 -- Discord CDN avatar URL...` (2 sites: Request construction + urlopen call) — both need noqa because Ruff S310 flags the `Request(avatar_url, ...)` scheme allowlist as well as the `urlopen`. `ocio.py` S311 is non-crypto dice/banana — narrow `# noqa: S311 -- ... entertainment` (2 sites). `config.py` S110 `except Exception: pass` at line 199 was the only try-except-pass — replaced with `logger.debug(..., exc_info=True)` so the handler logs before swallow (fail-closed verifier still raises above it).
- `tests/test_pr4a_ruff_mechanical.py` S-retention guard relaxed for PR4b phase progression (PR4b removes S, so the test now accepts S absence — previously required S present after PR4a). This is the only PR4b-induced change to a prior test file.
- PR4a authored diff is 280 ins / 156 del = 436 (+ test file 124) — slightly over 400 budget, but single mechanical concern (raise msg style) with one auto-fix pass + ruff format reflow. Independently revertible by restoring `bot/**` EM/TRY003 suppression. Commit will note budget exceedance.

## Remaining Tasks (not in this slice)

- Phase 4c (Ruff quality), Phase 5 (bandit+zizmor), Phase 6 (tach), Phase 7 (cleanup) — unchanged, pending in `tasks.md`.

## Status

29/52 tasks complete (PR1 1.1–1.7 + PR2 2.1–2.8 + PR3 3.1–3.5 + PR4a 4a.1–4a.4 + PR4b 4b.1–4b.5). Ready for next batch (PR4c Ruff quality). PR4b slice complete — do NOT proceed to PR4c in this invocation.

## Workload / PR Boundary — PR4b (this slice)

- Mode: stacked PR slice (stacked-to-main)
- Current work unit: PR4b Ruff security (S101 92 + S310 2 + S311 2 + S110 1 — 97 findings → 0)
- Boundary: tasks 4b.1 → 4b.5 inclusive; 26 files (23 bot + pyproject + 1 test + 1 test guard patch) + ruff format reflow
- Review budget: 318 ins + 109 del = 427 staged (bot) + 211 test + 10 guard patch = 638 total; exceeds 400 by ~238 — documented as single mechanical security batch (92 assert→raise with msg var), independently revertible by restoring `bot/**` S suppression
- Dependencies: PR4a (TRY003/EM101/EM102) — prerequisite; PR4c depends on this
- Out-of-scope: ARG/TRY300/FURB/C901/F841+ANN/PYI/PGH003 (PR4c), bandit+zizmor (PR5), tach (PR6)

## Workload / PR Boundary — PR4a (preserved)

- Mode: stacked PR slice (stacked-to-main)
- Current work unit: PR4a Ruff mechanical (TRY003/EM101/EM102 → 0, 274 findings)
- Boundary: tasks 4a.1 → 4a.4 inclusive; 21 files (20 bot + pyproject + 1 test) + ruff format reflow
- Review budget: 280 ins + 156 del = 436 authored (bot) + ~124 test = 560 total; 21 files. Over 400 by ~36 — documented as mechanical batch with single auto-fix concern
- Dependencies: PR1 (lock + ty 0.0.18), PR2 (ty config), PR3 (prek) — prerequisites; PR4b depends on this
- Out-of-scope: S101/S310/S311/S110 (PR4b), ARG/TRY300/FURB/C901/F841+ANN/PYI/PGH003 (PR4c), bandit+zizmor (PR5), tach (PR6)
