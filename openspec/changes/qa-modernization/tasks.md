# Tasks: QA Modernization

> Stacked-to-main, 6 PRs. PR1 first (lock prerequisite). PR2 before PR4 (ty informs ruff ignore removal). PR4 = 3 sub-batches. Delivery strategy `auto-chain`. Strict TDD: RED before GREEN for source edits; config tasks verify via tool exit 0.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1800 change-wide (1200 authored + ~600 PR4 fixes) |
| 400-line budget risk | High (change-wide); per-slice ≤400 |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 → PR3 → PR4a → PR4b → PR4c → PR5 → PR6 (8 slices; PR4 pre-split to honor 400/slice) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | uv foundation: PEP735 groups + lock + setup-uv | PR1 | `uv lock --check && uv sync --locked` | `make audit` (uv audit) | revert pyproject `[dependency-groups]`/`[tool.uv]`, restore pip-audit-weekly |
| 2 | ty replaces mypy, baseline measured | PR2 | `uv run ty check bot/ tests/` | `make type` | restore `[tool.mypy]`, revert Makefile/ci ty |
| 3 | prek replaces pre-commit | PR3 | `prek run --all-files` | `git commit` with staged violation → aborts | restore `.pre-commit-config.yaml` |
| 4a | Ruff mechanical: TRY003/EM101/EM102 | PR4a | `uv run ruff check bot/` | N/A — config + auto-fix, no runtime boundary | restore `bot/**` TRY003/EM101/EM102 suppression |
| 4b | Ruff security: S101/S310/S311/S110 | PR4b | `uv run ruff check --select S bot/` | `make ci` (pytest 2101 green) | restore `bot/**` S suppression |
| 4c | Ruff quality: ARG/TRY300/FURB/C901/F841 + ANN/PYI/PGH003 | PR4c | `uv run ruff check bot/` | `make ci` | restore remaining `bot/**` suppression |
| 5 | bandit delete + zizmor SHA-pin | PR5 | `uvx zizmor --format=github .` | CI workflow-security job | restore `[tool.bandit]` + bandit hooks |
| 6 | tach.toml + parse_ticket_ref move | PR6 | `uv run tach check && uv run tach check-external` | `make tach` | delete tach.toml, restore ticket_helpers import |

## Phase 1 — PR1: uv Foundation (MUST land first)

- [x] 1.1 RED: assert `uv lock --check` exits 0 after groups migration (test: `uv lock --check`); record baseline. **Why**: stale lock breaks all downstream PRs. **Accept**: exit 0. **Evidence**: sdd-attempt goal = lock fresh. **Dep**: none.
- [x] 1.2 Migrate `[project.optional-dependencies] dev` → `[dependency-groups] dev`; remove mypy/bandit/pip-audit; add `ty==0.0.18` exact. **Why**: PEP735, ty exact pin. **Accept**: `uv sync` installs dev without `--extra`. **Evidence**: `uv sync --locked` exit 0. **Dep**: 1.1.
- [x] 1.3 Add `[tool.uv] default-groups = ["dev"]`. Keep runtime deps in `[project] dependencies`. Keep `requirements.txt` (Pterodactyl pip). **Why**: PEP735 not published; Pterodactyl safe. **Accept**: `pip install -r requirements.txt` still resolves. **Evidence**: `uv sync` exit 0. **Dep**: 1.2.
- [x] 1.4 Regen `uv.lock` (`uv lock`); remove mypy/bandit/pip-audit entries; add ty. **Why**: source of truth. **Accept**: `uv lock --check` exit 0. **Evidence**: lock contains ty, lacks mypy. **Dep**: 1.2.
- [x] 1.5 `.github/workflows/ci.yml`: replace `actions/setup-python`+`actions/cache`+`pip install uv` with `astral-sh/setup-uv@<40-char-sha> # v6`; `uv sync --locked`. **Why**: native cache, SHA-pin. **Accept**: no `setup-python` step. **Evidence**: workflow YAML lint. **Dep**: 1.4.
- [x] 1.6 ci.yml: replace `pip-audit` step with `uv audit` in quality job; delete `pip-audit-weekly` job. **Why**: uv audit supersedes. **Accept**: no `pip-audit` references. **Evidence**: `grep pip-audit` empty. **Dep**: 1.5.
- [x] 1.7 Makefile: `audit` target `uv run --with pip-audit pip-audit` → `uv audit`. **Why**: target alignment. **Accept**: `make audit` runs `uv audit`. **Evidence**: `make audit`. **Dep**: 1.6.

## Phase 2 — PR2: ty Replaces mypy (MUST land before PR4)

- [x] 2.1 Add `[tool.ty.environment] python-version="3.11"`; `[tool.ty.rules]` possibly-unresolved-reference=warn, unused-ignore-comment=error (ty 0.0.18-valid; missing-type-argument/unsound-return-statement/blanket-ignore-comment are unknown-rule in 0.0.18 — probe proves INVALID; strict-literal/generic-narrowing also unknown-field in 0.0.18 analysis). **Why**: Astral strict; rule names verified vs ty 0.0.18 registry. **Accept**: `ty check` reads config. **Evidence**: `uv run ty check --help`. **Dep**: Phase 1.
- [x] 2.2 Add `[[tool.ty.overrides]] include=["bot/cogs/**"]` rules: invalid-argument-type=warn, possibly-missing-import=warn, possibly-unresolved-reference=warn (discord.py stub gaps; #3638 unsupported). `[[tool.ty.overrides]] include=["tests/**"]` possibly-unresolved-reference=warn, possibly-missing-attribute=warn + unresolved-attribute/invalid-argument-type/invalid-assignment/not-subscriptable/unused-ignore-comment=warn (191 tests errors require broader warn-tier to honor 177 type:ignore preservation; bot-only baseline is 2 errors). **Why**: cogs warn / rest error. **Accept**: cogs findings warn-tier. **Evidence**: `ty check bot/cogs/`. **Dep**: 2.1.
- [x] 2.3 Delete `[tool.mypy]` + both `[[tool.mypy.overrides]]`. **Why**: ty replaces. **Accept**: no `[tool.mypy]` in pyproject. **Evidence**: `grep tool.mypy` empty. **Dep**: 2.2.
- [x] 2.4 Makefile: `type` and `type-full` → `uv run ty check bot/ tests/`. **Why**: target migration. **Accept**: `make type` runs ty. **Evidence**: `make type`. **Dep**: 2.3.
- [x] 2.5 ci.yml: `mypy` step → `ty check bot/ tests/`. **Why**: CI gate. **Accept**: no mypy step. **Evidence**: workflow YAML. **Dep**: 2.3.
- [x] 2.6 Run baseline `uv run ty check bot/ tests/`; record actual finding count vs 28 target. **Why**: PR2 open question — measure before PR4. **Accept**: count documented in PR body. **Evidence**: ty output captured. **Dep**: 2.2.
- [x] 2.7 RED→GREEN: write failing test asserting ty error diagnostic blocks (stage a typed violation in a scratch module under tests/); then confirm `ty check` exits non-zero. **Why**: strict TDD for blocking behavior. **Accept**: non-zero exit on error. **Evidence**: `ty check` exit≠0. **Dep**: 2.6.
- [x] 2.8 Defer 28 (or actual count) findings WITHOUT `Any`/`cast` silencing; use `# ty: ignore[<rule>]` inline only where justified. **Why**: no broad suppression. **Accept**: deferred list in PR body. **Evidence**: `ty check` exit 0 on bot/ tests/. **Dep**: 2.7.

## Phase 3 — PR3: prek Replaces pre-commit (after PR2)

- [x] 3.1 Create `prek.toml`: `[priorities]` builtin=0/format=10/lint=20/type=30/gga=40/push=50; `[[repos]] repo="builtin"` (trailing-ws/eof/yaml/large-files, archive/md/json/css/js/ts exclusions); `[[repos]] repo="local"` (ruff-check `--fix`, ruff-format `--check`, ty `uv run ty check bot/ tests/`, gga `bash .gga`, pre-push: uv-check/tach-check/tach-check-external). **Why**: YAML→TOML, pre-push stage. **Accept**: `prek run --all-files` exit 0. **Evidence**: `prek run --all-files`. **Dep**: Phase 2.
- [x] 3.2 RED: stage a file with trailing whitespace; assert `prek run trailing-whitespace` fails. GREEN: fix file. **Why**: strict TDD hook behavior. **Accept**: non-zero on violation. **Evidence**: staged violation aborts. **Dep**: 3.1.
- [x] 3.3 RED: stage a ruff violation; assert `ruff-check` hook fails before `ty` runs. GREEN: fix. **Why**: ordering spec. **Accept**: ty not reached when ruff fails. **Evidence**: hook output order. **Dep**: 3.2.
- [x] 3.4 Delete `.pre-commit-config.yaml`. **Why**: single source of truth. **Accept**: file absent. **Evidence**: `ls .pre-commit-config.yaml` fails. **Dep**: 3.3.
- [x] 3.5 Verify `SKIP=ty git commit` bypasses ty only. **Why**: SKIP spec. **Accept**: commit succeeds, other hooks ran. **Evidence**: `SKIP=ty` commit. **Dep**: 3.4.

## Phase 4a — PR4a: Ruff Mechanical (after PR2; TRY003/EM101/EM102)

- [x] 4a.1 RED: `uv run ruff check --select TRY003,EM101,EM102 bot/` shows ~274 findings. **Why**: establish baseline. **Accept**: count recorded (274 = 135 TRY003 + 95 EM101 + 44 EM102 via --isolated). **Evidence**: ruff --isolated --statistics + tests/test_pr4a_ruff_mechanical.py::TestRuffMechanicalBaseline. **Dep**: Phase 2.
- [x] 4a.2 Remove `TRY003`, `EM101`, `EM102` from `bot/**/*.py` per-file-ignores. **Why**: progressive removal. **Accept**: EM broad + TRY003 removed; bot/** retains S,C4,C90,T10,TRY004,TRY300. **Evidence**: pyproject diff (PR4a). **Dep**: 4a.1.
- [x] 4a.3 GREEN: run `uv run ruff check --fix --select TRY003,EM101,EM102 bot/` (auto-fixable message style). **Why**: mechanical, low risk. **Accept**: 0 findings (isolated + normal both 0). **Evidence**: `ruff check --isolated` 0 + `ruff check bot/` 0 + 12 tests green. **Dep**: 4a.2.
- [x] 4a.4 REFACTOR: review auto-fixed raise messages for clarity; run `make test` (2166 green, 17 skipped). **Why**: semantic check. **Accept**: pytest 0 fail, ruff format 0, msg variable pattern verified. **Evidence**: `uv run pytest --no-cov` 2166 passed. **Dep**: 4a.3.

## Phase 4b — PR4b: Ruff Security (S101/S310/S311/S110)

- [ ] 4b.1 RED: `uv run ruff check --select S bot/` shows ~97 (92 S101 + 2 S310 + 2 S311 + 1 S110). **Why**: baseline. **Accept**: count recorded. **Evidence**: ruff output. **Dep**: 4a.4.
- [ ] 4b.2 Remove `S` from `bot/**/*.py` per-file-ignores. **Why**: bandit parity (S strictly broader: 97 vs 95). **Accept**: S removed. **Evidence**: pyproject diff. **Dep**: 4b.1.
- [ ] 4b.3 GREEN S101: replace `assert` in bot/ with `raise ValueError(...)` / `if … else` real checks. **Why**: real fixes not suppression. **Accept**: 0 S101 in bot/. **Evidence**: `ruff check --select S101 bot/`. **Dep**: 4b.2.
- [ ] 4b.4 GREEN S310/S311/S110: review each (url-open/non-crypto-random/try-pass) case-by-case; fix or document narrow `# noqa: Sxxx` with reason. **Why**: ~30 need review. **Accept**: each dispositioned. **Evidence**: `ruff check --select S310,S311,S110 bot/`. **Dep**: 4b.3.
- [ ] 4b.5 Keep `tests/**` S101/ARG/T20 semantic ignores. **Why**: test exceptions only. **Accept**: tests ignores unchanged. **Evidence**: pyproject per-file-ignores. **Dep**: 4b.4.

## Phase 4c — PR4c: Ruff Quality + Preview (ARG/TRY300/FURB/C901/F841 + ANN/PYI/PGH003)

- [ ] 4c.1 RED: `uv run ruff check --select ARG,TRY300,TRY301,FURB,C901,F841 bot/` shows ~55. **Why**: baseline. **Accept**: count recorded. **Evidence**: ruff output. **Dep**: 4b.5.
- [ ] 4c.2 Remove remaining `bot/**` suppression entries (C4,C90,T20,ARG,DTZ,EM,T10,TRY004,TRY300,TRY301,FLY,PERF,FURB,RUF059,F841). **Why**: full suppression removal. **Accept**: `bot/**/*.py` key absent or empty. **Evidence**: pyproject diff. **Dep**: 4c.1.
- [ ] 4c.3 GREEN: fix individually (no broad ignores). **Why**: real fixes. **Accept**: 0 findings. **Evidence**: `ruff check bot/` exit 0. **Dep**: 4c.2.
- [ ] 4c.4 Add `ANN`, `PYI`, `PGH003` to `select` with `preview = true`. **Why**: ty alignment. **Accept**: preview rules enforced. **Evidence**: `ruff check --preview bot/`. **Dep**: 4c.3.
- [ ] 4c.5 `make ci` green: lint→type→test→cov, 2101 tests, cov ≥75%. **Why**: regression gate. **Accept**: `make ci` exit 0. **Evidence**: `make ci`. **Dep**: 4c.4.

## Phase 5 — PR5: Security (bandit delete + zizmor) (after PR4)

- [ ] 5.1 Run BOTH bandit and ruff S once; record parity (bandit 95 ↔ S 97). **Why**: parity proof. **Accept**: delta documented. **Evidence**: both outputs. **Dep**: Phase 4c.
- [ ] 5.2 Delete `[tool.bandit]` from pyproject; delete bandit hooks from prek.toml; delete Makefile `security` target; remove bandit from `ci` chain. **Why**: S strictly broader. **Accept**: `grep bandit` empty. **Evidence**: `grep -ri bandit`. **Dep**: 5.1.
- [ ] 5.3 Add `workflow-security` job in ci.yml: `uvx zizmor --format=github .` (or sarif + `github/codeql-action/upload-sarif@<sha>`), blocking. **Why**: supply-chain gate. **Accept**: job fails on finding. **Evidence**: workflow YAML. **Dep**: 5.2.
- [ ] 5.4 SHA-pin ALL `uses:` to 40-char SHA + `# vN` comment: checkout, setup-uv, setup-node, upload-artifact, codeql-action/upload-sarif, zizmor-action. **Why**: zizmor unpinned-uses. **Accept**: no `@vN` refs. **Evidence**: `grep '@v[0-9]' .github/workflows/`. **Dep**: 5.3.
- [ ] 5.5 RED: temporarily revert one action to `@v4`; assert zizmor flags it. GREEN: restore SHA. **Why**: strict TDD for zizmor gate. **Accept**: zizmor fails on tag-pin. **Evidence**: zizmor output. **Dep**: 5.4.
- [ ] 5.6 Top-level `permissions: contents: read`; `workflow-security` job elevates `security-events: write` for SARIF. **Why**: minimal permissions. **Accept**: no `write-all`. **Evidence**: YAML lint. **Dep**: 5.5.
- [ ] 5.7 Fix `.github/workflows/code-quality.yml` trigger `main` → `master`. **Why**: repo default master. **Accept**: triggers on master PR. **Evidence**: workflow YAML. **Dep**: 5.6.

## Phase 6 — PR6: Tach Boundaries (after PR3; pre-push tach hook)

- [ ] 6.1 RED: create `bot/core/ticket_ref.py` with `parse_ticket_ref` + `TicketRef` moved from `bot/services/ticket_invariants.py`; existing `tests/contract/test_ticket_invariants.py` + `tests/test_ticket_invariants.py` pass unchanged (re-export shim keeps importers green). **Why**: zero-churn move; resolves utils→services violation. **Accept**: pytest ticket tests green. **Evidence**: `uv run pytest tests/test_ticket_invariants.py tests/contract/test_ticket_invariants.py`. **Dep**: Phase 5.
- [ ] 6.2 Add re-export shim in `bot/services/ticket_invariants.py`: `from bot.core.ticket_ref import parse_ticket_ref, TicketRef` (keeps 8 importers: ticket_service, ticket_repair_service, ticket_lifecycle_service + 5 test files). **Why**: blast-radius zero. **Accept**: no importer edits. **Evidence**: `grep ticket_invariants import` unchanged. **Dep**: 6.1.
- [ ] 6.3 Edit `bot/utils/ticket_helpers.py:17` → `from bot.core.ticket_ref import parse_ticket_ref`. **Why**: utils→core allowed, utils→services forbidden. **Accept**: helpers import from core. **Evidence**: `grep ticket_helpers`. **Dep**: 6.2.
- [ ] 6.4 Create `tach.toml`: `layers=["cogs","views","services","utils","core","db","models"]`; `source_roots=["."]`; `exact=true`; `forbid_circular_dependencies=true`; `ignore_type_checking_imports=true`; `respect_gitignore=true`; `root_module="ignore"`; `exclude=["**/*__pycache__","build/","dist/","dashboard/","locales/"]`; 8 `[[modules]]` (cogs/views/services/utils/listeners/core/core.db/models per design); `[[interfaces]]` expose `parse_ticket_ref`,`TicketRef` from `bot.core.ticket_ref` + `Ticket`,`TicketNote`,`TicketCategory` from `bot.models`; `[external]` exclude pytest/hypothesis/freezegun, rename PIL:pillow/psycopg:psycopg. **Why**: capture current arch, not pretext. **Accept**: `tach check` exit 0. **Evidence**: `uv run tach check`. **Dep**: 6.3.
- [ ] 6.5 RED: add temp `models→cogs` import; assert `tach check` fails. GREEN: remove temp import. **Why**: strict TDD boundary enforcement. **Accept**: violation reported. **Evidence**: `tach check` exit≠0 then 0. **Dep**: 6.4.
- [ ] 6.6 Makefile: add `tach` (`tach check` + `tach check-external`) and optional `tach-external` targets; update `.PHONY`. **Why**: DX target. **Accept**: `make tach` runs both. **Evidence**: `make tach`. **Dep**: 6.5.
- [ ] 6.7 ci.yml quality job: add `tach check` + `tach check-external` steps (blocking). prek.toml pre-push stage already declares tach hooks (Phase 3) — wire `uv run tach check` / `tach check-external`. **Why**: CI + pre-push gates. **Accept**: both steps present. **Evidence**: workflow YAML + prek.toml. **Dep**: 6.6.
- [ ] 6.8 Final `make ci`: lint→type→test→cov green, 2101 tests, cov ≥75%, matrix 3.11-3.14, PYTHONASYNCIODEBUG=1. **Why**: success criteria. **Accept**: exit 0. **Evidence**: `make ci`. **Dep**: 6.7.

## Phase 7 — Cleanup / Documentation

- [ ] 7.1 Update PR bodies with dependency diagram (📍 current PR), prior-PR links, out-of-scope. **Why**: chained-pr contract. **Accept**: each PR has Chain Context. **Evidence**: PR descriptions. **Dep**: per phase.
- [ ] 7.2 Verify no `mypy`/`bandit`/`pip-audit`/`.pre-commit-config.yaml` remnants repo-wide. **Why**: complete migration. **Accept**: `grep -ri` empty. **Evidence**: `git grep`. **Dep**: Phase 6.
- [ ] 7.3 Confirm `requirements.txt` still pip-resolves (Pterodactyl). **Why**: runtime safety. **Accept**: `pip install -r requirements.txt --dry-run` ok. **Evidence**: dry-run. **Dep**: Phase 6.
