# Proposal: v1-postrelease-zero — Restore v1.0.0 Gates and Slash-Only Truth

## Intent

Restore `v1.0.0` (`70db4e3`) gates after `clean-1.0`: 80 `ty` block `prek`, 79.78%<80, 12 specs 27 hybrid/prefix vs `bot-core`. No features.

## Scope

### In Scope
- **Baseline re-verify (HARD pre-apply):** proxy `sdd-verify` vs pinned `archive/2026-08-26-clean-1-0` (gen9 6064B 77/77 93/93); evidence here; archive/ledger untouched; dispatcher blocked — do not claim ran.
- **S0 gates <1500 (`uv run pytest`):** `ty` 0 via ignore deletion+narrowing (keep `error-on-warning=true`), `prek`/`ruff` green, ≥80 via `setup_modules`.
- **S1 truth <1500:** 12 specs → `bot-core`; `checks.py`→`app_commands`; AST guard `bot/cogs/**/*.py`; `,` invariant each slice.

### Out of Scope
- DDL (29 migrations), `bot-core` redef, threshold/suppression relax.

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `economy-commands`: hybrid → slash-only
- `utility-commands`: hybrid → slash-only
- `sentinel-commands`: dual-path → slash-only
- `ticket-commands`: hybrid → slash-only
- `unclaim-command`: hybrid → slash-only
- `setup-wizard`: hybrid → slash-only
- `permission-model`: slash-only, prefix inert
- `slash-locale-translator`: slash-only
- `qa-help-builder`: help slash-only
- `i18n-system`: examples slash-only
- `docs-manual`: drop hybrid/prefix
- `guild-config`: `prefix` data-only

## Approach

Two slices `auto-chain`→`stacked-to-main`, TDD, <1500. `ty` green ⇒ `prek` green.

- **S0:** Delete 52+8 ignores; narrow 14+4 diagnostics; keep `warn`; +≥22 lines via `setup_modules/*`.
- **S1:** Deltas for 12 specs (`grep hybrid/prefix`→0 except `bot-core`+`,`); guard checks decorators.
- **Verify split:** baseline proxy before `sdd-apply`; final verify of this change.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `pyproject.toml`/`prek.toml` | Verify | `error-on-warning=true`, 80, `ty` hook |
| `bot/cogs/*.py`+`ticket_*.py` | Modified | Ignore deletion, narrowing |
| `bot/views/setup_modules/*` | Covered | Additive tests |
| `bot/utils/checks.py` | Modified | `hybrid`→`app_commands` |
| `tests/*hybrid*`/`*comma*`/`*prek*` | Modified | Guards green each slice |
| `openspec/specs/{12}` | Modified | 27 fixes |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `ty` gaps >14 | Med | `isinstance`/`hasattr`, keep `warn` |
| Shallow coverage | Low | Cover `handle`/`render`, assert ≥80 |
| Missed hybrid | Low | `grep hybrid` RED→0 |
| `,` regression | Low | No `on_message` diff; invariant |
| Lineage falsification | Low | Hash-pin + gen9 |

## Rollback Plan

Each slice one stacked PR; revert commit. No DDL. Archive never mutated. S0/S1 independent.

## Dependencies

Pinned `clean-1.0` archive; `ty`/`prek`/`pytest --cov-fail-under=80`/`ruff`/`tach` at `70db4e3`; `sdd-verify-validate --requirements 35 --scenarios 93`.

## Success Criteria

- [ ] Proxy `sdd-verify` of `clean-1.0` before apply (archive untouched, gen9)
- [ ] `ty check` 0; `error-on-warning=true`, no new suppressions
- [ ] `prek run --all-files` green; `ruff` green
- [ ] `pytest --cov-fail-under=80` ≥80%
- [ ] Zero `hybrid_command`/`hybrid_group` decorators (AST)
- [ ] 12 specs reconciled — `grep` 0 (except history+`,`)
- [ ] `,` invariant green each slice; 29 migrations untouched
