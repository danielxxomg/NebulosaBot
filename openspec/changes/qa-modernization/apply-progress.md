# Apply Progress: qa-modernization — PR1 uv foundation

> PR1 is the first slice of the qa-modernization stacked-to-main chain (auto-chain).
> This file records PR1 completion and is MERGED forward for subsequent PRs.

## Current Slice

| Field | Value |
|-------|-------|
| PR | 1 / 8 slices (PR1 → PR2 → PR3 → PR4a → PR4b → PR4c → PR5 → PR6) |
| Work unit | PR1 uv foundation: PEP735 groups + lock + setup-uv + uv audit |
| Tasks in slice | 1.1–1.7 (7 tasks) |
| Mode | Strict TDD — RED before GREEN for config tasks (verify via tool exit 0 + TOML/YAML asserts) |
| Review budget | 4 files, 54 insertions + 345 deletions (uv.lock regen dominates; authored Δ ~54) ≤400 |
| sdd-attempt | sha256:9d75eee51f5dff190ec35e1c4464439d15591f81b5b3c4c33ee9a264bba0b6a2 / pr1-uv-foundation-001 |

## Completed Tasks (PR1)

- [x] 1.1 RED: assert `uv lock --check` exits 0 after groups migration — `uv lock --check` + `uv sync --locked --dry-run` in tests/test_pr1_uv_foundation.py::TestUvLockCheck
- [x] 1.2 Migrate `[project.optional-dependencies] dev` → `[dependency-groups] dev`; remove mypy/bandit/pip-audit; add `ty==0.0.18` exact
- [x] 1.3 Add `[tool.uv] default-groups = ["dev"]`; runtime deps preserved; requirements.txt retained
- [x] 1.4 Regen `uv.lock` (`uv lock`); remove mypy/bandit entries; add ty
- [x] 1.5 `.github/workflows/ci.yml`: replace `actions/setup-python`+`actions/cache`+`pip install uv` with `astral-sh/setup-uv@d0cc045d04ccac9d8b7881df0226f9e82c39688e # v6`; `uv sync --locked`
- [x] 1.6 ci.yml: replace `pip-audit` step with `uv audit` in qa-matrix job; delete `pip-audit-weekly` job
- [x] 1.7 Makefile: `audit` target `uv run --with pip-audit pip-audit -l --strict` → `uv audit`

## Files Changed (PR1)

| File | Action | What Was Done |
|------|--------|---------------|
| `pyproject.toml` | Modified | `optional-dependencies.dev` → `[dependency-groups] dev` (ty==0.0.18 replaces mypy, bandit removed); `[tool.uv] default-groups=["dev"]` |
| `uv.lock` | Regenerated | `uv lock` — removed mypy/bandit/mypy-extensions/rich/stevedore/...; added ty 0.0.18; 61 packages |
| `.github/workflows/ci.yml` | Modified | setup-uv SHA-pin `d0cc045d04ccac9d8b7881df0226f9e82c39688e # v6`, delete cache/pip-install, `uv sync --locked`, `uv audit`, delete `pip-audit-weekly` |
| `Makefile` | Modified | `audit: uv audit` |
| `tests/test_pr1_uv_foundation.py` | Created | 27 Strict TDD RED tests for PR1 (27 passed after GREEN) — part of slice, reverted before PR if desired |
| `openspec/changes/qa-modernization/tasks.md` | Modified | 1.1–1.7 `[ ]` → `[x]` |
| `openspec/changes/qa-modernization/apply-progress.md` | Created | This file |

## TDD Cycle Evidence (Strict TDD — PR1)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/test_pr1_uv_foundation.py::TestUvLockCheck` (2 tests) | Unit (subprocess tool exit) | ✅ 2094/2094 pre-phase | ✅ 2 RED before edit (uv lock) | ✅ Passed — `uv lock --check` exit 0, `uv sync --locked --dry-run` exit 0 | ✅ 2 cases: check + sync | ✅ Clean — no code to refactor (lock artifact) |
| 1.2 | `tests/test_pr1_uv_foundation.py::TestDependencyGroups` (8 tests) | Unit (TOML parse) | ✅ 2094/2094 | ✅ 5 RED before edit (groups/ty/ruff/pytest/bandit) | ✅ Passed — dependency-groups dev + ty==0.0.18 + pytest stack, no mypy/bandit | ✅ 8 cases cover all assertions | ✅ Clean |
| 1.3 | `tests/test_pr1_uv_foundation.py::TestToolUv` (3 tests) | Unit (TOML + file) | ✅ 2094/2094 | ✅ 1 RED before edit (tool.uv) | ✅ Passed — default-groups=["dev"], runtime deps, requirements.txt | ✅ 3 cases | ✅ Clean |
| 1.4 | `tests/test_pr1_uv_foundation.py::TestUvLockContent` (4 tests) | Unit (lock file) | ✅ 2094/2094 | ✅ 3 RED before edit (ty/mypy/bandit) | ✅ Passed — lock has ty, lacks mypy/bandit | ✅ 4 cases incl pip-audit | ✅ Clean |
| 1.5 | `tests/test_pr1_uv_foundation.py::TestCiSetupUv` (5 tests) | Unit (YAML text) | ✅ 2094/2094 | ✅ 5 RED before edit (SHA/cache/pip/sync) | ✅ Passed — SHA-pin `d0cc045d04ccac9d8b7881df0226f9e82c39688e # v6`, no setup-python/cache/pip-install, uv sync --locked | ✅ 5 cases | ➖ Single impl |
| 1.6 | `tests/test_pr1_uv_foundation.py::TestCiAudit` (3 tests) | Unit (YAML text) | ✅ 2094/2094 | ✅ 3 RED before edit (pip-audit/uv-audit/weekly) | ✅ Passed — uv audit present, pip-audit absent, weekly deleted | ✅ 3 cases | ➖ Single impl |
| 1.7 | `tests/test_pr1_uv_foundation.py::TestMakefileAudit` (2 tests) | Unit (Makefile text) | ✅ 2094/2094 | ✅ 2 RED before edit (audit target) | ✅ Passed — `uv audit` in audit:, no pip-audit | ✅ 2 cases | ➖ Single impl |

- **Total tests written**: 27 (tests/test_pr1_uv_foundation.py)
- **Total tests passing**: 27/27 (PR1 suite) and 2121/2121 full suite (7 skipped) at 87.85% cov
- **Layers used**: Unit (27) — config/lock/YAML/Make parsing + subprocess tool exits
- **Approval tests**: None — no refactoring tasks (net-new migration)
- **Pure functions**: N/A — config migration, no runtime code

## Work Unit Evidence (PR1)

| Evidence | Value |
|----------|-------|
| Focused test command and exact result | `uv run pytest tests/test_pr1_uv_foundation.py -v` → **27 passed in 0.78s** (RED: 18 failed on baseline, 9 passed; GREEN: 27 passed) |
| Runtime harness command/scenario and exact result | `uv audit` → exit 0 (36 vulnerabilities reported in aiohttp/cryptography — expected, blocking is deferred to PR2 gating; PR1 harness is `uv audit` presence, not clean) — `uv run pytest` → **2121 passed, 7 skipped, 87.85% cov** |
| Rollback boundary | `pyproject.toml` `[dependency-groups]`/`[tool.uv]` + `uv.lock` + `.github/workflows/ci.yml` (setup-uv + pip-audit-weekly) + `Makefile` `audit:` — revert these 4 files; `tests/test_pr1_uv_foundation.py` is slice-local test |

## Verification

| Command | Exit | Result |
|---------|------|--------|
| `uv lock --check` | 0 | Resolved 61 packages in 1ms |
| `uv sync --locked --dry-run` | 0 | Valid lock (would uninstall mypy/bandit, consistent) |
| `uv audit` | 0 | 36 known vulns in 60 packages (aiohttp/cryptography — pre-existing, not blocking PR1) |
| `uv run pytest tests/test_pr1_uv_foundation.py -v` | 0 | 27 passed |
| `uv run pytest -q` | 0 | 2121 passed, 7 skipped, 87.85% cov |

## Known Observations

- `pyproject.toml` still contains `[tool.mypy]` + `[tool.bandit]` — intentional per stacking: PR2 deletes mypy, PR5 deletes bandit (after S parity). PR1 only touches dependency-groups and lock.
- `ci.yml` still contains `mypy`/`bandit` steps — PR2/PR5 remove them; PR1 only touches setup-uv + audit + weekly deletion.
- `requirements.txt` unchanged — Pterodactyl pip-safe.
- Setup-uv SHA `d0cc045d04ccac9d8b7881df0226f9e82c39688e` is tag `v6` (v6.8.0 commit) — matches `ls-remote` tag v6 → d0d8abe → d0cc045.

## Remaining Tasks (not in this slice)

- Phase 2 PR2 (2.1–2.8), Phase 3 PR3 (3.1–3.5), Phase 4a/4b/4c, Phase 5, Phase 6, Phase 7 — unchanged, pending in `tasks.md`.

## Status

7/52 tasks complete. Ready for next batch (PR2 ty replaces mypy). PR1 slice complete — do NOT proceed to PR2 in same invocation.

## Workload / PR Boundary

- Mode: stacked PR slice (stacked-to-main)
- Current work unit: PR1 uv foundation (PEP735 groups + lock + setup-uv + uv audit)
- Boundary: tasks 1.1 → 1.7 inclusive; 4 files modified (pyproject, uv.lock, ci.yml, Makefile) + 1 test file + tasks/apply-progress
- Review budget: ~54 authored Δ + lock regen (346 Δ but generated) — within 400/slice
- Dependencies: none (PR1 must land first — prerequisite for all subsequent PRs)
- Out-of-scope: ty config, prek.toml, tach.toml, ruff fixes, bandit delete, zizmor — deferred to PR2–PR6
