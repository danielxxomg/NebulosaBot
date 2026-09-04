# Exploration: tests-slim-fase-3

## Current State

The test suite violates its governance ceiling. Verified fresh at HEAD `9871add`:
`find tests -name '*.py' | wc -l` = **175 files / 62,384 lines** vs the normative
ceiling **lines strictly below 61,480, files within 169-181**
(`openspec/specs/test-suite-governance/spec.md:95,107-111`). Excess: **+904 lines**,
so a net cut of **>=905 lines** is REQUIRED before any additions.

Duplication is inside budget but concentrated: jscpd over `tests/` reports
**4.26%** vs ceiling **5.08** (`reports/jscpd-baseline.json:1-4`,
report `/tmp/opencode/jscpd-tests/jscpd-report.json`: 166 clones, 1,870 duplicated
lines over 43,861). Clone-count leaders match the orchestrator list
(`test_ticket_model.py` 18, `test_production_live_close_s5_tdd.py` 17,
`test_pr2_on_message_red.py` 14, `test_live_catalog.py` 14,
`integration/test_ticket_flow.py` 13, `test_bot.py` 13, `test_utility_cog.py` 12,
`test_setup_module_welcome.py` 10).

Fase-2 precedent (`openspec/changes/archive/2026-09-02-tests-slim-fase-2/tasks.md:1-10`):
twin-first/delete-last in 3 batches (182->178->176->173 files), 11 survivor files
deleted with D3 proof. Fase-2 already harvested the easy deletions; fase-3 must
earn its cuts chiefly via **parametrization/hoisting**, which carries no D3 burden.

Two line-additive workstreams compete with the ceiling in the same change:
(a) hardening `tests/test_setup_panel_pickers.py:192-197` (weak
`kwargs.get("view", object()) is not None`; strong same-file patterns at
`tests/test_setup_panel_pickers.py:42-56` children/type/custom_id inspection and
`:279-286` registration proof), est. +15-30 ln;
(b) coverage tests for `bot/views/setup_modules/welcome.py` (54%),
`bot/views/setup_panel.py` (62%), `bot/views/setup_modules/goodbye.py` (69%),
`bot/services/live_catalog.py` (72%), est. +150-400 ln.

## Affected Areas

- `tests/test_ticket_model.py` (912 ln, 48 tests, 18 clones, mostly self-dup) — top parametrization target; pure dataclass mapping, no Discord mocks (`tests/test_ticket_model.py:58-159` repeating populated/null/missing/round-trip triplets per field).
- `tests/test_utility_cog.py` (408 ln, 11 tests; self-dup pairs 9-13 ln + overlap with `test_utility_i18n.py`) — avatar/serverinfo/userinfo trios.
- `tests/test_setup_module_welcome.py` (439 ln) + `tests/test_setup_module_goodbye.py` + `tests/test_setup_module_tickets.py` (9+ cross-file 9-13 ln twin pairs) — registration/parity twins hoistable to a shared helper.
- `tests/test_pr2_on_message_red.py` (393 ln, 13 tests; self-dup 9-11 ln pairs; `_make_bot`/`_make_message` scaffolding at `tests/test_pr2_on_message_red.py:12-60`) — helper hoist.
- `tests/test_live_catalog.py` (517 ln) + `tests/test_production_live_close_s5_tdd.py` (357 ln; cross-file clones 33+20+14+13 ln on RLS/scoped-SQL/provenance) — overlap merge, MEDIUM risk (live-marker gating, RED semantics).
- `tests/integration/test_ticket_flow.py` (871 ln, 23% self-duplicated, 42-ln self pair) — flow scaffolding dedup, MEDIUM-HIGH risk.
- `tests/test_bot.py` (871 ln, 28 tests; `TestValidatePanels` ~200 ln + `TestGlobalErrorHandlersLogExceptions` ~280 ln) — MEDIUM risk.
- `tests/test_setup_panel_pickers.py` (287 ln; 34-ln self-dup `:159-192` vs `:76-109`, weak assert at `:192-197`) — dedup + harden together.
- `tests/test_tickets_i18n.py` (1003 ln), `tests/contract/test_ticket_invariants.py` (947 ln, 0 clones), `tests/test_ticket_service.py` (4980 ln), `tests/test_tickets_cog.py` (3750 ln) — bulk but UNIQUE coverage; explicitly OUT of fase-3 scope (see Risks).
- `dashboard/__tests__/app/audit-panel.test.tsx:122-169` — flaky pagination (`waitFor`/`findByText` over mocks); dashboard-side, zero ceiling impact.
- `tests/conftest.py` (487 ln; `make_member` at `:339`, `make_interaction` at `:450`, `_isolate_i18n_state` at `:72`) — hoist destination for shared helpers.

## Approaches

1. **Parametrization-first, no deletions** — compress `test_ticket_model` field triplets
   (`populated/null/missing` x `from_db_row/to_db_dict/round-trip`) into
   `@pytest.mark.parametrize` cases; parametrize utility-cog command trios and
   welcome/goodbye/tickets registration twins; hoist `_make_bot`/`_make_message`
   into `conftest.py`. Zero D3 proof burden (no file deleted).
   - Pros: no D3 gate; behavior-preserving by construction (same assertions per case, per `spec.md:39`); attacks the single biggest lever (`test_ticket_model` ~300-450 ln est.).
   - Cons: `collected N->M` drop must be documented per `spec.md:53-57`; large diff in one file needs careful review.
   - Effort: Medium

2. **Cross-file twin merge (live-catalog + production-live-close)** — unify the
   33+20+14+13 ln provenance/RLS/scoped-SQL clones behind one parametrized module
   or shared fixtures; keep live-marker gating (`tests/conftest.py:53-63`) intact.
   - Pros: removes the only large CROSS-file clone cluster; directly lowers jscpd numerator.
   - Cons: RED-test semantics + credential-gated branches are the riskiest duplication in scope; provenance-token binding (`970_bound`) must not be weakened.
   - Effort: Medium

3. **Flow/scaffold dedup (ticket_flow integration + test_bot panels/handlers)** —
   extract repeated flow scaffolding (42-ln self-dup pair + siblings) into module
   fixtures; compress `TestValidatePanels`/error-handler repetitions.
   - Pros: second-largest gross lever (~180-350 ln combined est.).
   - Cons: highest behavioral-specificity density (custom-fields/integrity-repair/PR5 slices); fixture extraction can hide arrange-steps and hurt failure readability; HIGHEST regression risk per line saved.
   - Effort: High

4. **Deletions under D3 (twin-first/delete-last, fase-2 style)** — only if a file
   with a proven live/parametrized twin is found; each deletion needs named twin
   or grep-equivalence + per-batch `--cov` with revert-on-dip (`spec.md:61,86-90`,
   FAIL-regardless-of-metrics per `spec.md:112`).
   - Pros: fastest lines-per-diff; proven fase-2 machinery.
   - Cons: fase-2 already deleted the 11 known survivors — remaining files likely lack twins, so discovery cost is high and payoff uncertain; D3 proof per file is expensive.
   - Effort: High (discovery-dominated)

## Recommendation

Combine **1 + 2**, defer 3 unless the ledger still misses, avoid 4 unless a
twin-backed candidate surfaces during work:

- Slice A (safe, ~500-700 ln est.): `test_ticket_model` parametrization
  (~300-450) + utility-cog trios (~80-120) + welcome/goodbye/tickets twin hoist
  (~100-180, shared helper in `conftest.py` next to `make_member:339`).
- Slice B (medium, ~140-220 ln est.): pr2_on_message helper hoist (~80-120) +
  live-catalog/production-live-close overlap merge (~60-100).
- Slice C (hardening + coverage, +165-430 ln): pickers assert fix (+15-30, modeled
  on `:279-286` inspection style) + targeted coverage tests hosted in the
  existing files (`test_setup_module_welcome.py`, `test_setup_panel_pickers.py`,
  `test_setup_module_goodbye.py`, `test_live_catalog.py` — files window 175/181
  allows +6 but new files cost ledger room; prefer existing hosts).
- Slice D (conditional): ticket_flow/test_bot dedup ONLY if A+B net still misses
  the cut target below.

### Line budget math (verified inputs)

- Current ledger: 175 files / **62,384 ln**; ceiling **<61,480** (`spec.md:95,111`).
- Compliance gap: 62,384 - 61,480 = 904 -> **net cut >= 905 ln** before additions.
- Planned additions: hardening +15-30, coverage +150-400 -> **+165 to +430 ln**.
- **Gross cut target: 905 + 165 = ~1,070 (min) to 905 + 430 = ~1,335 (max).**
  Propose committing to **1,100-1,400 ln gross** so the final ledger lands
  **below 61,480 with margin** (aim <= 61,300 to absorb estimate error).
- Feasibility: A (~500-700) + B (~140-220) = ~640-920 gross — SHORT of 1,070 at
  midpoint. Gap closers, in preference order: (i) pickers self-dup 34 ln +
  `test_i18n.py` 36-ln self pair + `test_pr2_expired_scans_red.py` 25/24-ln self
  pairs (~100-150, low risk); (ii) Slice D flows (~180-350, high risk);
  (iii) D3 deletion only with proof. **The budget does NOT close on safe slices
  alone — the proposal must either scope Slice D in or negotiate smaller
  coverage additions.**

### Quality gates that will run (exact)

- `qa-matrix` (`.github/workflows/ci.yml:20-62`, py 3.11-3.14):
  `ruff check bot/ tests/` + `ruff format --check bot/ tests/` (`Makefile:8-10`),
  `ty check bot/ tests/` (`Makefile:12-13`), `tach check` + `tach check-external`
  (`Makefile:29-34`; `tach.toml:3-4` exact=true, circular deps forbidden),
  `uv audit`, `pytest --cov-fail-under=80` (`Makefile:23-27`;
  `pyproject.toml:58-60` addopts `--cov=bot --cov-fail-under=80 --randomly-seed=42`,
  `asyncio_mode=auto`). Governance spec additionally demands per-slice
  **cov >= 80.50%** and seed-42 ledger (`spec.md:51,95,103-105`).
- `quality-reports` (`.github/workflows/code-quality.yml:15-44`, PRs to master):
  jscpd advisory (`bot/` threshold 5, `tests/` threshold 10) + **BLOCKING**
  `scripts/jscpd_check.py` budget gate (ceilings bot 2.5 / tests 5.08);
  `vulture bot/ --min-confidence 80` advisory; OSV-Scanner + Betterleaks BLOCKING.
- Parametrization MUST preserve `_isolate_i18n_state` (`tests/conftest.py:72`) and
  document the `collected N->M` drop (`spec.md:53-57`); new test code obeys
  AGENTS.md (mock Discord objects, `t()` for user-facing strings, no new
  function-level imports without `# noqa: PLC0415`, type hints, `logging`).

### Coverage-gap feasibility

- Hosts exist for all four files: welcome -> `test_setup_module_welcome.py` (+
  `test_setup_modules_coverage.py`), panel -> `test_setup_panel_pickers.py` (+
  `test_setup_panel.py`, `test_setup_cog.py`), goodbye ->
  `test_setup_module_goodbye.py`, live_catalog -> `test_live_catalog.py`.
- Likely untested (source sizes: `welcome.py` 291 ln, `setup_panel.py` 464 ln,
  `goodbye.py` 216 ln, `live_catalog.py` 401 ln): template-picker callbacks and
  `_template_picker.py` (331 ln) branches, preview-real-artifact paths, panel
  persistent-registration paths, live_catalog credential-fallback/PGRST205
  branches. Exact missing lines need `pytest --cov=... --cov-report=term-missing`
  in the proposal phase — NOT run here (read-only exploration, no test execution).
- Tension is structural: +150-400 ln of coverage tests consumes 15-40% of the
  gross cut. Proposal must fix the coverage scope (which of the 4 files, target
  %: e.g. welcome 54%->80%?) BEFORE the cut target is final.

## Risks

- **Budget may not close without Slice D (HIGH)**: safe slices A+B (~640-920 gross) fall short of the 1,070-1,335 target; closing the gap needs flow-dedup risk or scoped-down coverage.
- **Unproved deletion fails the whole slice (HIGH)**: any deletion without named twin/grep-equivalence + cov proof fails regardless of metrics (`spec.md:112`); default to zero deletions.
- **Coverage additions eat the cuts (MEDIUM)**: every +100 ln of new tests needs +100 ln of extra cuts; cap coverage scope in proposal.
- **RED/provenance weakening (MEDIUM)**: live-catalog/production-live-close dedup touches credential-gated and token-bound assertions; require per-case assertion preservation (`spec.md:39`).
- **KEEP collateral (LOW)**: 7 KEEP files (`spec.md:13-21`) + listener observe+delegate (`spec.md:23`) must stay untouched and green; none is a consolidation candidate.
- **i18n isolation regressions (LOW)**: parametrization across i18n-adjacent files must keep `_isolate_i18n_state` green under seed 42 + random ordering.

## Ready for Proposal

Yes — with three user decisions needed in proposal: (1) accept gross cut target
**1,100-1,400 ln** aiming final **<=61,300 ln**? (2) coverage scope: all 4 low
files or subset + target %? (3) Slice D (ticket_flow/test_bot dedup) pre-approved
as gap-closer, or parametrization-only with reduced coverage scope?
Also confirm: dashboard flaky pagination fix (`audit-panel.test.tsx:122-169`) in
or out of this change (recommend: separate change, zero ceiling interaction)?

## Open Questions

1. Cut-vs-coverage priority if estimates collide: protect the ceiling (<61,480) or the coverage gains?
2. Are D3 deletions allowed at all in fase-3, or parametrization-only?
3. Coverage targets per file (e.g. welcome 54%->?) — uniform 80% or risk-based?
4. One stacked PR or sliced PRs (budget 1500/slice per `spec.md:95`) with per-slice ledger?
5. Dashboard pagination stabilization — same change or separate?
