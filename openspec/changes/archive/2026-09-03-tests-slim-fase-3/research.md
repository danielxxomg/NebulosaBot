# Research: tests-slim-fase-3 — Suite consolidation patterns for fase-3

**State**: `gentle-ai.sdd-research/v1`
**Revision**: 2
**Outcome**: `done`
**Change**: `tests-slim-fase-3`
**Artifact store**: hybrid (OpenSpec file + Engram `sdd/tests-slim-fase-3/research`)
**Accessed at**: 2026-09-03

## Selected intent (retained)

Single research lane: "Suite consolidation patterns for fase-3" — evidence-backed idioms for
(1) pytest parametrization of dataclass-mapping field triplets
(populated/null/missing x from_db_row/to_db_dict/round-trip),
(2) fixture/helper hoisting into conftest.py without breaking i18n isolation
(_isolate_i18n_state) and random-order (pytest-randomly seed 42) determinism,
(3) parametrization accounting effects: collected-test-count drop, coverage accounting
(--cov-fail-under=80) and per-slice cov >= 80.50% floor, and jscpd clone re-counting
after parametrization,
(4) safe assertion-preserving transformations (spec compliance: same assertions per case).

Retained from revision 1 (blocked): identical lane, identical five questions. This revision
replaces the blocked revision with a positive `done` revision under the orchestrator-supplied
runtime capability declaration `gentle-ai.sdd-research-capability/v1` declared 2026-09-03.

## Admission

- Required capability: `gentle-ai.sdd-research-capability/v1` with exact declared,
  non-empty grants for `documentation` and/or `open-web`.
- Declared grants (orchestrator, 2026-09-03):
  - `documentation`: granted=true, tools=`["context7_resolve-library-id", "context7_query-docs"]`,
    mapped sources: pytest official documentation via context7 (library `pytest`,
    docs.pytest.org: parametrize semantics, fixture/conftest collection, marks/ids),
    jscpd documentation via context7 or official site (github.com/kucherenko/jscpd:
    clone detection accounting, min-tokens, threshold semantics).
  - `open-web`: granted=true, tools=`["webfetch"]`, mapped sources:
    docs.pytest.org how-to/parametrize page (canonical URL) if context7 coverage
    is insufficient; jscpd README/CLI options page if needed.
  - `denied_classes`: `[]`.
- Observed grants: `documentation` exercised via context7 (resolve + 3 query-docs calls);
  `open-web` granted but unused — context7 coverage was sufficient, no webfetch fallback
  was needed. Repository-internal evidence (openspec specs, archived fase-2 artifacts,
  pyproject.toml, tests/conftest.py, Makefile, AGENTS.md, tests/test_ticket_model.py,
  scripts/jscpd_check.py, reports/jscpd-baseline.json) was read directly with file tools;
  per the orchestrator note it does not require an external grant class but is cited
  with `file:line` locators and classed `repository` below.
- Verdict: admission GRANTED. All requested classes supported by exact declared grants.

## Questions

1. What are the pytest-documented semantics of `@pytest.mark.parametrize` (ids,
   indirect fixtures, conftest.py collection) applicable to field-triplet compression?
2. What did the fase-2 precedent prove about consolidation without D3 burden?
3. How do repo configs (addopts, conftest helpers, Makefile gates) constrain new test code?
4. How does parametrization affect jscpd clone counting against the ceilings?
5. Which AGENTS.md test rules constrain new test code?

All five questions are SUPPORTED in this revision (see validated claims).

## Sources

| id | class | title | publisher | URL | accessed_at | excerpt |
|----|-------|-------|-----------|-----|-------------|---------|
| S1 | documentation | pytest how-to parametrize: parametrizing test functions + stacking decorators | pytest-dev (via context7 `/pytest-dev/pytest`) | https://github.com/pytest-dev/pytest/blob/main/doc/en/how-to/parametrize.rst | 2026-09-03 | "`@pytest.mark.parametrize` decorator enables parametrization of arguments for a test function by defining multiple sets of parameter values... causing the test function to run once for each tuple of values." / "Stack multiple `@pytest.mark.parametrize` decorators to generate test cases for all possible combinations" / "To obtain all combinations of multiple parametrized arguments, you can stack `parametrize` decorators... exhausting parameters in the order the decorators are applied." |
| S2 | documentation | pytest parametrize custom test IDs (ids list, idfn callable, pytest.param id) + --collect-only expansion | pytest-dev (via context7 `/pytest-dev/pytest`) | https://github.com/pytest-dev/pytest/blob/main/doc/en/example/parametrize.rst | 2026-09-03 | "This snippet illustrates various ways to customize test IDs... including default generation, explicit string lists, custom ID functions, and using `pytest.param`." (`ids=["forward","backward"]`, `ids=idfn`, `pytest.param(..., id="forward")`); collect-only shows one `<Function test_a[spam]>` node per param case. |
| S3 | documentation | pytest conftest.py fixture sharing + autouse fixtures (hierarchical discovery) | pytest-dev (via context7 `/pytest-dev/pytest`) | https://github.com/pytest-dev/pytest/blob/main/doc/en/reference/fixtures.rst | 2026-09-03 | "`conftest.py` file serves as a means of providing fixtures for an entire directory. Fixtures defined in a conftest.py can be used by any test in that package without needing to import them." / "Fixtures from parent directory conftest.py files are available to child directories." / Autouse: "`@pytest.fixture(autouse=True)`... automatically requested by all tests in their scope." |
| S4 | documentation | jscpd options: min-tokens/min-lines defaults, threshold semantics, reporters | kucherenko/jscpd (via context7 `/kucherenko/jscpd`) | https://github.com/kucherenko/jscpd/blob/master/rust/crates/cpd/src/options.rs ; https://github.com/kucherenko/jscpd/blob/master/docs/api.md ; https://github.com/kucherenko/jscpd/blob/master/apps/jscpd/README.md ; https://github.com/kucherenko/jscpd/blob/master/rust/crates/cpd/README.md | 2026-09-03 | "`min_tokens` defaults to 50, `min_lines` defaults to 5, `threshold` has no default (None) when not specified" (options.rs); "`detectClones({minLines: 5, minTokens: 50, mode: 'mild'})`" (api.md); "Key settings include 'min-tokens' and 'min-lines' to define the minimum size of code blocks to analyze... Users can also set a 'threshold' to trigger an error if the total duplication level exceeds a defined limit." (apps/jscpd README); CLI: "`cpd --min-tokens 50 --min-lines 5 --reporters json,console .`" (cpd README). |
| R1 | repository | pyproject.toml pytest addopts + dev dependencies | repo | file: `pyproject.toml` | 2026-09-03 | addopts `--cov=bot --cov-fail-under=80 --randomly-seed=42`, `asyncio_mode=auto`, `testpaths=["tests"]`; dev pins pytest>=8.0, pytest-asyncio>=0.23, pytest-cov>=5.0, pytest-randomly>=3.15. |
| R2 | repository | tests/conftest.py: live gate, i18n isolation, locale helpers, factories | repo | file: `tests/conftest.py` | 2026-09-03 | `pytest_collection_modifyitems` live-skip gate; session `_load_real_locales`; autouse `_isolate_i18n_state` snapshot/restore of `_locales`/`_guild_languages`; `build_nested_locale`/`swap_suffix`/`load_test_locales`; `make_member`/`make_ctx`/`make_interaction` factories; `mock_db`/`mock_guild`/`mock_member` fixtures. |
| R3 | repository | Makefile blocking gates | repo | file: `Makefile` | 2026-09-03 | `lint`: ruff check + format --check over bot/+tests/; `type`: ty check; `tach`: tach check + check-external; `test`/`cov`: pytest --cov-fail-under=80. |
| R4 | repository | test-suite-governance spec (parametrization, D3 gate, ledger) | repo | file: `openspec/specs/test-suite-governance/spec.md` | 2026-09-03 | Parametrization must preserve assertions per case, seed 42, isolation; N→1 drop expected + documented; per-slice cov >=80.50%; ledger files/lines/collected/cov + seed 42; lines strictly below 61,480, files 169-181; unproved deletion FAIL-regardless-of-metrics. |
| R5 | repository | tests/test_ticket_model.py field-triplet shape | repo | file: `tests/test_ticket_model.py` | 2026-09-03 | `_ticket_row(**overrides)` builder; per-field populated/null/missing x from_db_row/to_db_dict/round-trip triplets with identical arrange/act/assert skeleton (parent_id, subject/description blocks). |
| R6 | repository | jscpd budget gate + baseline ceilings | repo | file: `scripts/jscpd_check.py` + `reports/jscpd-baseline.json` | 2026-09-03 | Pinned `npx jscpd@4.0.1 <scope> --reporters json`; compares `statistics.total.percentage` per scope against baseline `{"bot": 2.5, "tests": 5.08}`; strictly-above = exit 2 violation; no `--threshold` passed. |
| R7 | repository | AGENTS.md Python/Discord/Testing rules | repo | file: `AGENTS.md` | 2026-09-03 | pytest+pytest-asyncio; mock Discord objects, never call API; independent tests; type hints; no function-level imports without `# noqa: PLC0415 -- <reason>`; logging not print; 100% `t()` for user-facing strings; slash-only surface; permission decorators. |
| R8 | repository | fase-2 precedent (twin-first/delete-last, 3 batches) | repo | file: `openspec/changes/archive/2026-09-02-tests-slim-fase-2/tasks.md` | 2026-09-03 | B1 182→178, B2 178→176, B3 176→173; 11 survivor files deleted with D3 proof (commits b4a72de/fd4778e/6ddf443). |

Open-web fallback: not invoked. Context7 coverage sufficed for S1–S4; canonical
docs.pytest.org how-to/parametrize content is mirrored by S1 (same source tree), and
jscpd README/CLI content is covered by S4.

## Validated claims (evidence table)

| claim | source | locator | confidence |
|-------|--------|---------|------------|
| C1. Single `@pytest.mark.parametrize("names", [tuples])` runs the test once per tuple; stacking two `@parametrize` decorators yields the Cartesian product in decorator-application order. Either shape compresses populated/null/missing x from_db_row/to_db_dict/round-trip triplets (flat tuple list preferred for heterogeneous asserts; stacked preferred for orthogonal axes). | S1 | how-to/parametrize.rst § "@pytest.mark.parametrize: parametrizing test functions" + § "Stacking Decorators" | high |
| C2. Failure readability after compression is preserved via explicit IDs: `ids=[...]` list, `ids=idfn` callable, or per-case `pytest.param(..., id="...")`; `--collect-only` then lists one `Function test_x[id]` node per case, which is the `collected N→M` accounting unit. | S2 | example/parametrize.rst § "Custom Test IDs"; how-to/fixtures.rst § collect-only listing | high |
| C3. Fixtures/helpers defined in `tests/conftest.py` are auto-discovered for the whole `tests/` tree without imports; hierarchy inherits parent→child. Plain builder functions (`make_member`, `make_ctx`, `make_interaction`) are importable via `from tests.conftest import ...` — the established hoist destination (precedent: `make_member`, locale helpers already live there). | S3, R2 | fixtures.rst § "conftest.py - Sharing Fixtures Across Multiple Files"; `tests/conftest.py:99-164` (locale helpers), `:339-464` (factories), `:191-330` (fixtures) | high |
| C4. `autouse=True` fixtures run for every test in scope. `_isolate_i18n_state` (autouse, dict-copy snapshot of `i18n_mod._locales`/`_guild_languages` around `yield`, restore after) is the order-independence mechanism under pytest-randomly; hoisted fixtures must `yield` and rely on it as outermost (per in-file comment), never replace or reorder it. | S3, R2 | fixtures.rst § "Autouse Fixture"; `tests/conftest.py:71-88` (isolate), `:95-96` (outermost contract) | high |
| C5. Repo pins determinism + coverage floor: `addopts = "--cov=bot --cov-fail-under=80 --randomly-seed=42"`, `asyncio_mode = "auto"`, `testpaths = ["tests"]`. New parametrized/hoisted code runs under seed 42 by default and must stay green under both seed 42 and random order. | R1 | `pyproject.toml:57-63` | high |
| C6. Governance requires per param case the SAME assertions (no weakening), seed-42 green, isolation preserved, and the `collected N→M` drop documented in the commit; per-slice `cov >= 80.50%` with full ledger `files/lines/collected/cov + seed 42`; final lines strictly below 61,480, files 169-181. | R4 | `openspec/specs/test-suite-governance/spec.md:39`, `:47-57`, `:93-112` | high |
| C7. Coverage accounting is code-execution accounting, not test-count accounting: collapsing N near-identical tests into 1 parametrized test with M cases preserves coverage iff the same production lines/branches execute with the same assertions. `--cov-fail-under=80` (pyproject/Makefile) is the hard floor; 80.50% is the additional per-slice governance floor. | R1, R3, R4 | `pyproject.toml:60`; `Makefile:23-27`; `spec.md:47-51,95,103-111` | medium-high (floor values direct; execution-not-count is standard coverage-tool behavior applied to the repo gate) |
| C8. jscpd accounting: defaults `min-tokens 50 / min-lines 5`, `threshold` unset unless passed; repo gate does NOT pass `--threshold` — it parses `statistics.total.percentage` per scope and fails strictly-above the `reports/jscpd-baseline.json` ceilings (`bot 2.5 / tests 5.08`). Advisory CI thresholds (bot 5 / tests 10) are distinct from this blocking budget gate. | S4, R6 | options.rs defaults; apps/jscpd README threshold §; `scripts/jscpd_check.py:72-90,102-112,160-172`; `reports/jscpd-baseline.json:1-4` | high |
| C9. Parametrization lowers the jscpd numerator mechanistically: N near-identical 9-13-line blocks that each clear min-tokens/min-lines collapse into one parametrized body + data table, so surviving fragments fall below the clone minimums and are no longer counted; percentage is recomputed over the new totals, so a re-count after each slice is mandatory. | S4, R6 | min-tokens/min-lines § (S4); `_measure_scope` recompute (jscpd_check.py:72-129) | medium (mechanism follows directly from documented minimums + re-measure code; exact per-slice delta not pre-computable without running the gate) |
| C10. Fase-2 proved twin-first/delete-last in 3 batches (182→178→176→173, 11 survivors, commits b4a72de/fd4778e/6ddf443) with per-file D3 proof. Parametrization/hoisting carries no D3 burden (no file deleted), which is why fase-3's recommended slices A/B are parametrization-first. | R8, R4 | `archive/2026-09-02-tests-slim-fase-2/tasks.md:5-8`; `spec.md:60-90,112` (D3 gate) | high for process; medium for "easy deletions exhausted" (explore estimate, not a measured fact) |
| C11. `test_ticket_model.py` is the top compression target: `_ticket_row(**overrides)` builder plus repeating populated/null/missing x from_db_row/to_db_dict/round-trip triplets per field (parent_id, subject/description, ...) with identical arrange/act/assert skeleton — the canonical flat-`parametrize` candidate (field × state × direction as data, one body, per-case asserts preserved). | R5 | `tests/test_ticket_model.py:25-45` (builder), `:58-83` (from_db_row triplet), `:91-127` (to_db_dict), `:135-171` (round-trip), `:184-289` (subject/description repeat) | high |
| C12. New/hoisted test code must obey: mock Discord objects (never call API), independent tests (no shared mutable state), type hints on public functions, no function-level imports without `# noqa: PLC0415 -- <reason>` (tests carry per-file ignores but new violations still fail `ruff`), `logging` never `print`, 100% `t()` for user-facing strings, slash-only commands for any new command surface. | R7 | `AGENTS.md:5-13` (Python), `:26-28` (i18n/permissions), `:71-75` (Testing), `:79-91` (anti-patterns) | high |
| C13. Quality gates that will judge every slice: `ruff check` + `ruff format --check` (bot/+tests/), `ty check`, `tach check` + `check-external`, `pytest --cov-fail-under=80`, plus governance per-slice cov ≥80.50% and zero-warning discipline (`filterwarnings = ["error", ...]` with narrow ignores). | R3, R1 | `Makefile:8-31`; `pyproject.toml:64-85` | high |
| C14. Safe-transformation boundary: same assertions per case; KEEP 7 files + listener observe+delegate untouched and green; live-marker gating (`pytest_collection_modifyitems` skip unless `--run-live`/LIVE_SUPABASE=1) intact — live-catalog/RED dedup must not weaken credential-gated or provenance-token assertions. | R4, R2 | `spec.md:9-35,39`; `tests/conftest.py:44-63` (live gate) | high |

## Contradictions

- None among admitted sources. Apparent tension resolved: (a) S1 flat-vs-stacked
  parametrize are alternatives, not contradictions — flat tuple lists suit heterogeneous
  field triplets (C11), stacked suits orthogonal axes; (b) jscpd CLI `--threshold`
  vs repo budget gate are complementary — the gate intentionally omits `--threshold`
  and compares raw `statistics.total.percentage` against versioned ceilings
  (`scripts/jscpd_check.py:87-89`); (c) CI advisory jscpd thresholds vs blocking
  `jscpd_check.py` ceilings are distinct gates, not conflicting values.
- Ledger-baseline drift (background, not a source contradiction): governance spec states
  baseline 184 files / 61,622 ln / 3005 collected @2bb4e89 (`spec.md:5,95`), while the
  fase-3 exploration measured 175 files / 62,384 ln fresh at HEAD 9871add. Proposal must
  re-baseline at its own HEAD; both figures are retained, neither is altered here.

## Uncertainty

- Gross savings per file (e.g. test_ticket_model ~300-450 ln, utility trios ~80-120)
  are exploration estimates, not measured facts — actuals depend on chosen flat vs
  stacked shape and ID style. Recorded as ranges, not claims.
- Exact post-parametrization jscpd delta and new `collected M` cannot be known without
  running the gate/collection; state-mutating runs were out of scope for this
  read-only research. Re-measure per slice (`--collect-only -q`, `jscpd_check.py`).
- Exact uncovered lines in the four low-coverage files (welcome 54%, setup_panel 62%,
  goodbye 69%, live_catalog 72%) need `pytest --cov=... --cov-report=term-missing`
  in proposal — not run here.
- pytest-randomly ordering of stacked-parametrize ID sequences under seed 42 is
  deterministic, but failure-message readability (flat descriptive IDs vs stacked
  Cartesian IDs) remains a reviewer judgment, not a documented fact.
- jscpd version skew: docs (S4, current) vs pinned gate `jscpd@4.0.1` (R6) — defaults
  cited from current source tree; if 4.0.1 defaults differ, the gate's measured
  percentage still governs (it reads the report, not the default).

## Freshness

- External docs (S1–S4) accessed 2026-09-03 via context7 from current main branches
  (pytest 9.x era, jscpd current). pytest parametrize/conftest semantics are stable
  long-horizon APIs; risk of staleness before proposal is low.
- Repository evidence (R1–R8) read fresh at fase-3 HEAD context 2026-09-03. Ledger
  numbers drift with every merged PR — proposal must re-verify `find tests`,
  `--collect-only`, `--cov`, and jscpd at its own HEAD.
- No time-sensitive deprecation affects the recommended idioms.

## Product choices (non-authoritative, orchestrator-owned)

- Pending. No product decisions are made or confirmed by this research.
- Exploration-recommended direction (background only, NOT a research claim): combine
  slices 1+2 (parametrization-first + live-catalog twin merge), defer flow/scaffold
  dedup unless the ledger misses, zero D3 deletions by default; coverage scope and
  gross-cut target (1,100-1,400 ln) and dashboard-pagination scoping await orchestrator
  product discovery.
- Proposal readiness: READY — evidence is valid and `done`; orchestrator must still
  confirm product decisions and validate OpenSpec + Engram references (same revision
  and bytes on readback) before invoking `sdd-propose`.
