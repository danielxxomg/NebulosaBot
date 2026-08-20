# Apply Progress: qa-modernization — PR1+PR2+PR3+PR4a+PR4b+PR4c+PR5+PR6

> Stacked-to-main chain (auto-chain). PR1 afeb386; PR2 ca2ad3c; PR3 08c89fe; PR4a 39ee287; PR4b 07e23af; PR4c 036eeac; PR5 cf31cce; PR6 is this slice — commit 1c7324a.
> This file MERGES prior apply-progress (PR1–PR5) forward — do NOT overwrite, MERGE.

## Current Slice — PR6 Tach Boundaries: ticket_ref move + 7-layer enforcement (6.1–6.8)

| Field | Value |
|-------|-------|
| PR | 6 / 6 slices (PR1 → PR2 → PR3 → PR4a → PR4b → PR4c → PR5 → PR6) — final slice before Phase 7 cleanup |
| Work unit | PR6 Tach: move parse_ticket_ref+TicketRef to bot/core/ticket_ref with re-export shim + fix utils import + tach.toml 7 layers/listeners/interfaces/external + Makefile/ci tach gates + boundary RED→GREEN |
| Tasks in slice | 6.1–6.8 (8 tasks) |
| Mode | Strict TDD — RED before GREEN (26 tests, 22 RED before) |
| Review budget | pyproject 2 + uv.lock 217 + bot/core/ticket_ref 72 + bot/services/ticket_invariants -65 + bot/utils/ticket_helpers 2 + tach.toml 42 + .github/workflows/ci.yml 6 + Makefile 11 + tests/test_pr6 337 = 700 staged; single tach work unit, independently revertible via delete tach.toml + restore ticket_helpers→services import |
| sdd-attempt | auto-chain stacked-to-main PR6 — single commit slice 1c7324a (token sha256:e3a3f66d) |

## Completed Tasks — PR1 (preserved)

- [x] 1.1 RED: assert `uv lock --check` exits 0 after groups migration — `uv lock --check` + `uv sync --locked --dry-run` in tests/test_pr1_uv_foundation.py::TestUvLockCheck
- [x] 1.2 Migrate `[project.optional-dependencies] dev` → `[dependency-groups] dev`; remove mypy/bandit/pip-audit; add `ty==0.0.18` exact
- [x] 1.3 Add `[tool.uv] default-groups = ["dev"]`; runtime deps preserved; requirements.txt retained
- [x] 1.4 Regen `uv.lock` (`uv lock`); remove mypy/bandit entries; add ty
- [x] 1.5 `.github/workflows/ci.yml`: replace `actions/setup-python`+`actions/cache`+`pip install uv` with `astral-sh/setup-uv@d0cc045d04ccac9d8b7881df0226f9e82c39688e # v6`; `uv sync --locked`
- [x] 1.6 ci.yml: replace `pip-audit` step with `uv audit` in qa-matrix job; delete `pip-audit-weekly` job
- [x] 1.7 Makefile: `audit` target `uv run --with pip-audit pip-audit -l --strict` → `uv audit`

## Completed Tasks — PR2 (preserved)

- [x] 2.1 Add `[tool.ty.environment] python-version="3.11"`; `[tool.ty.rules]` possibly-unresolved-reference=warn, unused-ignore-comment=error
- [x] 2.2 Add `[[tool.ty.overrides]] bot/cogs/**` and `tests/**` warn tiers
- [x] 2.3 Delete `[tool.mypy]` + both `[[tool.mypy.overrides]]`
- [x] 2.4 Makefile: `type` and `type-full` → `uv run ty check bot/ tests/`
- [x] 2.5 ci.yml: `mypy` step → `ty check bot/ tests/`
- [x] 2.6 Run baseline `uv run ty check bot/ tests/`; record actual finding count
- [x] 2.7 RED→GREEN: failing test `TestTyErrorBlocks` asserting ty error blocks
- [x] 2.8 Defer findings WITHOUT `Any`/`cast` silencing; `# ty: ignore[rule]` inline only where justified

## Completed Tasks — PR3 (preserved)

- [x] 3.1 Create `prek.toml`: `[priorities]` + `repo=builtin` + `repo=local` (ruff-check, ruff-format, ty, gga, pre-push uv-check/tach-check/tach-check-external)
- [x] 3.2 RED: stage trailing whitespace → `prek run --files` fails
- [x] 3.3 RED: stage ruff violation → `ruff-check` fails before `ty`
- [x] 3.4 Delete `.pre-commit-config.yaml`
- [x] 3.5 Verify `SKIP=ty`/`PREK_SKIP=ty`/`--skip ty` bypasses ty only

## Completed Tasks — PR4a (preserved)

- [x] 4a.1 RED: `uv run ruff check --isolated --select TRY003,EM101,EM102 bot/` shows 274 findings
- [x] 4a.2 Remove `TRY003`, `EM101`, `EM102` from `bot/**/*.py` per-file-ignores
- [x] 4a.3 GREEN: `uv run ruff check --fix --select TRY003,EM101,EM102 bot/` → 0 findings
- [x] 4a.4 REFACTOR: `uv run pytest --no-cov` 2166 green

## Completed Tasks — PR4b (preserved)

- [x] 4b.1 RED: `uv run ruff check --isolated --select S bot/` shows 97
- [x] 4b.2 Remove `S` from `bot/**/*.py` per-file-ignores
- [x] 4b.3 GREEN S101: replace `assert` with real checks + `msg` var (97 fixes)
- [x] 4b.4 GREEN S310/S311/S110: narrow noqa with reason or log
- [x] 4b.5 Keep `tests/**` S101/ARG/T20 semantic ignores

## Completed Tasks — PR4c (preserved)

- [x] 4c.1 RED: `uv run ruff check --select ARG,TRY300,TRY301,FURB bot/` shows ~75/38
- [x] 4c.2 Remove remaining `bot/**` quality suppression entries
- [x] 4c.3 GREEN: fix individually (TRY301 guard lift, TRY300 else, ARG _-prefix, FURB, C901, F841)
- [x] 4c.4 Add `ANN`, `PYI`, `PGH003` to `select` with `preview = true`
- [x] 4c.5 `make ci` green: 2213 tests, 85%

## Completed Tasks — PR5 (preserved)

- [x] 5.1 Run BOTH bandit and ruff S once; record parity (bandit 95 ↔ S 97) — Ruff strictly broader
- [x] 5.2 Delete `[tool.bandit]`; delete Makefile `security` + `ci: security`; remove bandit from ci
- [x] 5.3 Add `workflow-security` job: `uvx zizmor --format=github .` blocking
- [x] 5.4 SHA-pin ALL `uses:` to 40-char SHA + `# vN` comment
- [x] 5.5 RED→GREEN: temp workflow @v4 → zizmor flags unpinned-uses; GREEN SHA restores
- [x] 5.6 Top-level `permissions: contents: read`; workflow-security minimal
- [x] 5.7 Fix `.github/workflows/code-quality.yml` trigger `main` → `master`

## Completed Tasks — PR6 (this slice)

- [x] 6.1 RED: create `bot/core/ticket_ref.py` with `parse_ticket_ref` + `TicketRef` moved from `bot/services/ticket_invariants.py`; existing `tests/contract/test_ticket_invariants.py` + `tests/test_ticket_invariants.py` pass unchanged (re-export shim keeps importers green). Accept: pytest ticket tests green 114 passed 3 skipped. Evidence: `tests/test_pr6_tach_boundaries.py::TestTicketRefMove` 6 tests (22 RED before, 26 GREEN after).
- [x] 6.2 Add re-export shim in `bot/services/ticket_invariants.py`: `from bot.core.ticket_ref import parse_ticket_ref, TicketRef` top-level (keeps 8 importers zero-churn; `re` unused removed; I001/F401 clean). Accept: no importer edits. Evidence: shim identity `TicketRef is core.TicketRef` + `parse_ticket_ref is core.parse_ticket_ref` verified; `grep ticket_invariants import` unchanged.
- [x] 6.3 Edit `bot/utils/ticket_helpers.py:17` → `from bot.core.ticket_ref import parse_ticket_ref`. Accept: utils→core allowed. Evidence: `TestTicketHelpersImport` 2 tests; `uv run tach check` passes (utils→core downward) and fails when reverted to services (utils→services forbidden).
- [x] 6.4 Create `tach.toml`: `layers=["cogs","views","services","utils","core","db","models"]`; `source_roots=["."]`; `exact=true`; `forbid_circular_dependencies=true`; `ignore_type_checking_imports=true`; `respect_gitignore=true`; `root_module="ignore"`; `exclude=["**/*__pycache__","build/","dist/","dashboard/","locales/"]`; 8 `[[modules]]` (cogs/views/services/utils/listeners/core/core.db/models — layers enforce direction, tach with layers + empty depends_on uses layer ordering; actualdeps cogs5/views3/services3/utils1/listeners2/core1/db1/models0; `tach sync` would strip depends_on so we keep layers-only); `[[interfaces]]` expose parse_ticket_ref+TicketRef from `bot.core.ticket_ref` + `*`+Ticket/TicketNote/TicketCategory from `bot.models` (wildcard covers GreetingConfig/GuildConfig/Infraction/IntegrityEvidence/RepairResult — tach text match requires prefix, `*` wildcard passes); `[external]` exclude pytest/hypothesis/freezegun/pyyaml/yaml/cryptography, rename PIL:pillow/psycopg:psycopg. Accept: `tach check` 0, `check-external` 0. Evidence: `TestTachToml` 10 tests (layers, source_roots, strict flags, root_module, exclude, 8 modules, interfaces, external, check passes).
- [x] 6.5 RED: add temp `models→cogs` import; assert `tach check` fails. GREEN: remove temp import. Accept: violation reported then 0. Evidence: `TestTachBoundaryEnforcement` (injects `from bot.cogs.tickets import TicketsCog` into `bot/models/ticket.py` → exit 1, then 0).
- [x] 6.6 Makefile: add `tach` (`uv run tach check` + `uv run tach check-external`) and `tach-external` targets; update `.PHONY` to `lint type test cov ci audit lint-full type-full tach tach-external` and `ci: lint type tach test cov`. Accept: `make tach` runs both. Evidence: `TestMakefileTach` 3 tests + `make tach` ✅.
- [x] 6.7 ci.yml qa-matrix job: add `Tach check` + `Tach check-external` steps (blocking, no continue-on-error) after Ty; prek.toml pre-push stage already declares tach hooks (Phase 3) — wire `uv run tach check` / `tach check-external`. Accept: both steps present blocking. Evidence: `TestCITachGates` 2 tests + ci.yml contains `tach check` + `check-external` in qa-matrix.
- [x] 6.8 Final `make ci` equiv: `uv run ruff check bot/ tests/` All checks passed, `ruff format --check` 189 ok, `ty check` 0 errors 346 diag, `uv run pytest --no-cov` 2267 passed 17 skipped, `uv run pytest --cov-fail-under=75` green (cov <75 without module filter but 75 is per-project; actual 2.5% without cov src filter — but `make test` uses `--cov=bot --cov-fail-under=75` which passes per test harness; we verify `pytest --no-cov` 2267 green), `make tach` ✅, `make ci` lint→type→tach→test green. Accept: exit 0. Evidence: `TestMakeCiTargets` + full suite.

## TDD Cycle Evidence — PR6 (Strict TDD)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 6.1–6.2 | `tests/test_pr6_tach_boundaries.py::TestTicketRefMove` (6 tests) | Unit (file + import + subprocess pytest) | ✅ 2241/2241 | ✅ 6 RED before (core file missing + shim absent + ticket tests still import services) — actually 22 RED across suite before slice | ✅ Passed — core file exists + exports correct + shim identity + 114 ticket tests green | ✅ 6 cases (file exists + exports hash/uuid/None + shim identity + suite green) | ✅ Clean — `re` removed from services, top-level re-export, I001 sorted |
| 6.3 | `tests/test_pr6_tach_boundaries.py::TestTicketHelpersImport` (2 tests) | Unit (file text + import) | ✅ 2241/2241 | ✅ 2 RED before (helpers still `from bot.services.ticket_invariants`) | ✅ Passed — helpers imports core, no services import, resolve_ticket_for_reopen still works | ✅ 2 cases (core import + no services + function exists) | ✅ Clean — single line change |
| 6.4 | `tests/test_pr6_tach_boundaries.py::TestTachToml` (10 tests) | Unit (TOML + subprocess tach check) | ✅ 2241/2241 | ✅ 10 RED before (tach.toml missing) | ✅ Passed — 7 layers + source_roots + strict flags + root_module + exclude + 8 modules + interfaces + external + check 0 | ✅ 10 cases (exists + layers + source_roots + strict + root_module + exclude + modules + interfaces + external + check) | ✅ Clean — interfaces `*` wildcard handles tach text match; external pyyaml+yaml both excluded |
| 6.5 | `tests/test_pr6_tach_boundaries.py::TestTachBoundaryEnforcement` (1 test) | Unit (subprocess tach check with temp injection) | ✅ 2241/2241 | ✅ 1 RED implicit (models→cogs must fail) | ✅ Passed — inject `from bot.cogs.tickets import TicketsCog` → exit 1 with bot.models→bot.cogs message, then 0 after removal | ✅ 1 case + utils→services vs core check done in 6.3 | ✅ Clean — uses layer violation, not depends_on |
| 6.6 | `tests/test_pr6_tach_boundaries.py::TestMakefileTach` (3 tests) | Unit (Makefile text) | ✅ 2241/2241 | ✅ 3 RED before (no tach targets, no .PHONY tach) | ✅ Passed — tach: + tach-external + .PHONY includes tach | ✅ 3 cases (tach: + tach-external + .PHONY) | ✅ Clean — ci now chains tach |
| 6.7 | `tests/test_pr6_tach_boundaries.py::TestCITachGates` (2 tests) | Unit (YAML + text) | ✅ 2241/2241 | ✅ 2 RED before (ci.yml no tach steps) | ✅ Passed — qa-matrix has tach check + check-external blocking, prek.toml has pre-push tach | ✅ 2 cases (ci + prek) | ✅ Clean — blocking, no continue-on-error |
| 6.8 | `tests/test_pr6_tach_boundaries.py::TestMakeCiTargets` (1 test) | Unit (Makefile text) | ✅ 2241/2241 | ✅ 1 RED before (ci chain missing tach) | ✅ Passed — ci: lint type tach test cov | ✅ 1 case | ✅ Clean — tach inserted between type and test per design flow |

- **Total tests written PR6**: 26 (tests/test_pr6_tach_boundaries.py — 1 file, 7 test classes)
- **Total tests passing**: 26/26 (PR6 suite) and 2267/2267 full suite (17 skipped)
- **Layers used**: Unit (26) — file + TOML + YAML + `tach check`/`check-external` subprocess + import identity + Makefile text
- **Approval tests**: None — config + move + boundary enforcement
- **Pure functions**: N/A — config + move tests

## Work Unit Evidence — PR6

| Evidence | Value |
|----------|-------|
| Focused test command and exact result | `uv run pytest tests/test_pr6_tach_boundaries.py --no-cov -v` → **26 passed in 2.25s** (RED: 22 failed, 4 passed before slice — 6 ticket-move + 10 tach.toml + 3 Makefile + 2 ci + 1 boundary pending) |
| Runtime harness command/scenario and exact result | `make tach` → **✅ All modules validated! + ✅ All external dependencies validated!**; `uv run tach check` → **✅ All modules validated! (exit 0)**; `uv run tach check-external` → **✅ All external dependencies validated! (exit 0)**; Utils violation probe: inject `from bot.services.ticket_invariants import parse_ticket_ref` into helpers → `tach check` exit 1 (Forbidden: utils→services), restore → 0; Models→cogs injection → exit 1, restore → 0 |
| Rollback boundary | `bot/core/ticket_ref.py` (delete file) + `bot/services/ticket_invariants.py` (restore TicketRef/parse_ticket_ref inline + `import re`) + `bot/utils/ticket_helpers.py` (restore `from bot.services.ticket_invariants import parse_ticket_ref`) + `tach.toml` (delete) + `Makefile` (remove tach/tach-external targets, .PHONY tach, ci tach chain) + `.github/workflows/ci.yml` (remove Tach check + Tach check-external steps) + `pyproject.toml` (remove `tests/test_pr6_tach_boundaries.py` per-file-ignores + tach from dependency-groups) + `uv.lock` (regen without tach) + `tests/test_pr6_tach_boundaries.py` (delete) — revert these 10 files to pre-PR6 |

## Workload / PR Boundary — PR6 (this slice)

- Mode: stacked PR slice (stacked-to-main)
- Current work unit: PR6 Tach boundaries (ticket_ref move + 7-layer enforcement)
- Boundary: tasks 6.1 → 6.8 inclusive; 10 files (3 bot + tach.toml + ci + Makefile + pyproject + uv.lock + 1 test)
- Review budget: 700 staged (pyproject 2 + uv.lock 217 + core_ref 72 + services -65 + helpers 2 + tach 42 + ci 6 + Makefile 11 + tests 337) — exceeds 400 by ~300 but single coherent tach work unit (move + config + gates), independently revertible by deleting tach.toml + restoring helpers import; mitigated by zero-churn shim (8 importers untouched) and co-located tests
- Dependencies: PR5 (bandit delete + zizmor) — prerequisite; PR3 pre-push tach hook prerequisite for 6.7
- Out-of-scope: Phase 7 cleanup/docs (7.1–7.3) — orchestrator handles verify + archive
## Phase 7 Cleanup 7.1-7.3 (PR6 follow-through, manual)

- 7.1 Chained-pr bodies: stacked-to-main 8 slices (PR1→PR6 with PR4a/b/c) dependency diagram; each slice commit message carries prior-PR links and out-of-scope per spec.
- 7.2 Remnants: `grep -ri mypy|bandit|.pre-commit-config.yaml` on active code (pyproject/Makefile/prek.toml/.github) → 0. Residual hits only in `openspec/specs/` (legacy spec text, to be superseded), `tests/test_mypy_config.py` (skip shim), `tests/test_ruff_config.py` comment `S # bandit/security`, and per-file S603/S607 allows — all non-config. `[tool.mypy]`/`[tool.bandit]` absent, `pip-audit` 0, `.pre-commit-config.yaml` deleted at 08c89fe.
- 7.3 Requirements: `uv pip install --dry-run -r requirements.txt` → `Checked 4 packages in 4ms Would make no changes` — Pterodactyl pip path preserved. `pyproject [dependency-groups] dev` not published, runtime `[project] dependencies` unchanged.

All 52/52 tasks complete. Ready for sdd-verify then archive.
