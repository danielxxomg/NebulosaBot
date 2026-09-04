# Design: tests-slim-fase-3

Pure test refactor, no production change. Flat parametrize with explicit `ids` for heterogeneous triplets (research C1–C2); plain-function hoists into `tests/conftest.py` beside `make_member:339`/`make_interaction:450`, autouse `_isolate_i18n_state:72` untouched (C4). Every case keeps its assertions.

## Technical Approach

Slice A: `test_ticket_model.py` (912 ln, 48 collected) → 3 parametrized tests; utility avatar pair parametrized; setup-module `_make_*` twins → `make_greeting_bot(kind)` + `make_greeting_interaction()` in conftest. Slice B: pr2 builders → conftest, 13 tests → 3 groups; live/S5 via shared helpers, markers intact. Slice C: pickers `:192-197` hardened on `:279-286`; 4 files → ~80% in existing hosts. Dashboard: UI-driven wait. Gaps: 3 self-dup clusters. Slice D: sketch only, user-gated.

## Architecture Decisions

| Option | Tradeoff | Decision |
|---|---|---|
| Flat vs stacked (ticket_model) | Triplets heterogeneous per direction | Flat: 3 tests (9+6+6 cases), explicit `ids`; 21 fns → 3 fns + tables, −300…−450 ln, collected neutral ~48→~48 |
| Extend `make_member` vs wrappers (utility) | Extension bloats all callers | Wrapper: `_make_member:106-124` → `make_member()` + 4-line enrichment; avatar pair parametrized; `_make_ctx` stays; −50…−90 ln |
| New conftest helpers (setup modules) | 9–13 ln twins × 3 files | `make_greeting_bot(kind, **overrides)` + `make_greeting_interaction()` after `:450`; plain functions, isolation order unchanged; files −100…−180, conftest +50…+70 |
| Merge vs helpers (live/S5) | Deletion triggers D3 gate | No deletion: S5 scoped-SQL pair parametrized + `fake_db_with_token(...)` helper; live gate `:53-63` + 970-bound asserts verbatim; −25…−65 ln |
| UI-first vs mock-poll wait (dashboard) | `waitFor(nthCalledWith)` races setState | Click → `await findByText(/Page 2/i)`, then sync `nthCalledWith`; same asserts reordered; 2 tests (`:122-169`); ledger-neutral |

## Data Flow

Test-only. Per slice: RED/neutral tests → refactor → ledger (seed 42) → gates → stacked commit (revert = rollback).

## File Changes

| File | Action | Description |
|---|---|---|
| `tests/test_ticket_model.py` | Modify | 21 triplet fns → 3 parametrized + tables |
| `tests/test_utility_cog.py` | Modify | avatar pair parametrize; `_make_member` → wrapper |
| `tests/test_setup_module_{welcome,goodbye,tickets}.py` | Modify | locals → conftest greeting helpers |
| `tests/conftest.py` | Modify | +4 builders (~+90…+110 ln) |
| `tests/test_pr2_on_message_red.py` | Modify | hoist + 13 tests → 3 groups (−115…−155) |
| `tests/test_live_catalog.py`, `test_production_live_close_s5_tdd.py` | Modify | scoped-SQL parametrize + provenance helper |
| `tests/test_setup_panel_pickers.py` | Modify | harden `:192-197`; welcome/panel coverage host |
| `tests/test_setup_module_welcome.py` | Modify | setter + fallback tests (+40…+70) |
| `tests/test_setup_module_goodbye.py` | Modify | setter + fallback tests (+30…+60) |
| `tests/test_live_catalog.py` | Modify | credential/PGRST205 branch tests (+40…+90) |
| `dashboard/__tests__/app/audit-panel.test.tsx` | Modify | UI-first wait reorder, 2 tests |
| `tests/test_i18n.py`, `tests/test_pr2_expired_scans_red.py` | Modify | gap-closer dedup |
| 7 KEEP files + listeners | Untouched | Diff must not list them |

## Interfaces / Contracts

```python
def make_greeting_bot(kind, **overrides) -> MagicMock: ...
def make_greeting_interaction(**overrides) -> MagicMock: ...
def make_ticket_bot() -> MagicMock: ...
def make_ticket_message(content: str, ...) -> MagicMock: ...
```

Assertion contract: each case runs its original asserts verbatim; `awaited_once` vs `not_awaited` selected by case flag, never weakened.

Pickers hardening (`:192-197`, model `:279-286`):

```python
edited_view = kwargs.get("view")
assert isinstance(edited_view, SetupPanelView)
child_ids = {getattr(c, "custom_id", None) for c in edited_view.children}
assert {_WELCOME_SELECT_ID, _GOODBYE_SELECT_ID} <= child_ids
```

Coverage (subset-measured gaps; existing hosts; RED-first): welcome 53%→~80% (setters + fallbacks `:47-121`, callbacks `:238-268`); goodbye 69%→~80% (`:47-100`, `:163-193`); setup_panel registration/error branches; live_catalog 72%→~80% (fallback `:92-98,329-344`, PGRST205 `:239-281`, provenance `:353-367`). Adds +160…+340 ln, +15…+30 collected.

Gap closers: pickers route pair (`:73-113` vs `:116-154`) → kind-axis parametrize + `_panel_interaction()` helper (hardened in C); `test_i18n` fallback trio + pair (`:117-134`) → guild-input-axis parametrize; expired-scans shim preamble (warns `:21-43`, future `:75-84`, tempbans mirrors) → `ensure_fake_querybuilder_shims(monkeypatch)` helper.

Slice D sketch (conditional): ticket_flow 42-ln scaffolding → module fixtures; `test_bot` `TestValidatePanels` (~200 ln) → panel-kind parametrize; error-handler class (~280 ln) → shared helper. Gate: after safe slices report real ledger + gross-vs-adds math to user BEFORE approving D; fallback is shrinking C scope. D3 deletions default ZERO.

## Testing Strategy

| Layer | What | Commands |
|---|---|---|
| Slice verify | per-file `-q --no-cov`, e.g. `uv run pytest tests/test_ticket_model.py -q --no-cov` | ticket_model; utility+3 setup modules; pr2+live+S5; pickers+i18n+expired |
| Gates/slice | ruff, format, ty, tach, jscpd, KEEP | `ruff check` + `format --check` `bot/ tests/`; `ty check`; `tach check`; `jscpd_check.py`; KEEP 7-file run |
| Suite | seed-42 + cov ≥80.50% | `uv run pytest -q` (addopts: cov-fail-under-80, seed 42); dashboard `npx vitest run __tests__/app/audit-panel.test.tsx` |

TDD: C RED-first (confirm new tests hit uncovered lines via `--cov --cov-report=term-missing` diff); parametrization twins-equivalent (same asserts, N→M documented, cov-neutral). Rollback: one stacked commit per slice.

## Threat Matrix

N/A — test-only; no routing, shell, subprocess, VCS, executable-classification, or process boundary (S5 shell-`False` asserts observed, not modified).

## Migration / Rollout

No migration. Stacked-to-master, ≤1500 ln/slice, ledger in commit body.

## Open Questions

- None blocking. Watchpoint: A+B+gaps (~−725…−1070) may miss +adds (~+165…+340) → D gate decides.
