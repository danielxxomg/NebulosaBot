# Proposal: tests-slim-fase-3

## Intent

Suite breaches its ceiling: **175 files / 62,384 ln** at `9871add` vs **<61,480 ln** (`test-suite-governance`). Net cut **≥905 ln** before additions. Fase-2 took easy deletions; fase-3 cuts via parametrization (no D3 burden).

## Scope

### In Scope
- A: `test_ticket_model` parametrization + utility trios + welcome/goodbye/tickets hoist to `conftest.py`
- B: `pr2_on_message` hoist + live-catalog merge (assertions preserved)
- C: pickers hardening + 4 low files to ~80% in existing hosts
- Dashboard: flaky pagination (`audit-panel.test.tsx:122-169`), no ledger impact
- Gap closers: pickers 34, `test_i18n` 36, `pr2_expired_scans` 25/24 self-pairs

### Out of Scope
- Slice D (ticket_flow/test_bot): **conditional fallback — user consulted BEFORE escalation**
- D3 deletions: default ZERO; KEEP files, listeners, bulk-unique files untouched

## Capabilities

### New Capabilities
- None — pure test refactor, no production behavior change.

### Modified Capabilities
- None — spec requirements unchanged.

## Approach

Flat tuples (heterogeneous triplets), stacked (orthogonal axes), explicit IDs, helpers to `conftest.py` keeping `_isolate_i18n_state` outermost. TDD, stacked-to-master, ≤1500 ln/slice.

| Slice | Gross Δ |
|-------|---------|
| A (safe) | −500…−700 |
| B (medium) | −140…−220 |
| Gap closers | −100…−150 |
| C (adds) | +165…+430 → 4 files ~80% |
| D (conditional) | −180…−350 |

Cuts: drops documented, cov neutral; C adds cases.

Final ≤61,300 needs gross−adds ≥1,084; safe slices (−740…−1070) may miss → gate: re-measure after safe slices, return to user with real numbers BEFORE approving D. If cuts underperform, shrink coverage, never breach ceiling.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `test_ticket_model.py` | Modified | triplet→parametrize (~300–450 ln) |
| `test_utility_cog.py`, `test_setup_module_{welcome,goodbye,tickets}.py` | Modified | trio/twin hoist |
| `test_pr2_on_message_red.py`, `test_live_catalog.py`, `test_production_live_close_s5_tdd.py` | Modified | hoist + merge |
| `test_setup_panel_pickers.py` + 3 hosts | Modified | harden `:192-197`, +150–400 ln |
| `audit-panel.test.tsx` | Modified | pagination unit |
| `test_ticket_flow.py`, `test_bot.py` | Gated | Slice D only |

## Risks
| Risk | Like. | Mitigation |
|------|-------|------------|
| Budget misses without D | High | D gate: real numbers + user consult |
| Baseline drift (184/61,622 vs 175/62,384) | Med | per-slice ledger, seed 42 |
| RED/provenance weakening | Med | same assertions per case, live-gate intact |
| jscpd/collect drift | Low | per-slice re-measure + `--collect-only` |

## Rollback Plan

Per-slice stacked PRs; revert the slice commit. No production code touched.

## Dependencies

Gates: `ruff`, `ty`, `tach`, `pytest --cov-fail-under=80`, per-slice cov ≥80.50%, seed 42. Test-only: no /Diagramas impact.

## Success Criteria

- [ ] ≤61,300 ln, 169–181 files, jscpd tests ≤5.08
- [ ] 4 files ~80%; cov ≥80.50%/slice, N→M documented, seed-42 green
- [ ] Pagination stable; KEEP untouched; zero D3 debt
