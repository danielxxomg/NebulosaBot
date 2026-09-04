# Tasks: Unified Pending Close

## Review Workload Forecast

Diff / ledger per slice: S0 ~40 / 0 · S1a ~500 / −180 · S1b ~500 / −170 · S5a ~500 / −184 · S5b1 ~550 / −222 · S5b2 ~400 / −160 · S2 ~250 / −85 · GATE 0 / re-check · S3a ~450 / +~330 · S3b1 ~600 / +~330 · S3b2 ~250 / +~140 · S4 ~550 / 0 · S6 ~20 / re-check.

61,478 → ~60,477 → ~61,277 (<61,480; aim ≤61,300 edge). L3 = `wc -l`,`--collect-only`,`--cov` s42; body `files/lines/collected/cov`.

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
800-line budget risk: High
400-line budget risk: High

Budget 800 (`openspec/config.yaml`, read-only); auto-chain, 12 PRs.

### Suggested Work Units

- PR1 S0: test `pytest test_suite_governance`, harness N/A docs, rollback `openspec/specs/test-suite-governance/spec.md`.
- PR2 S1a: test `pytest test_ticket_service`, harness L3, rollback `tests/test_ticket_service.py:1133-2160`.
- PR3 S1b: test `pytest test_ticket_service`, harness L3, rollback `tests/test_ticket_service.py:220-385,2174-2640`.
- PR4 S5a: test `pytest test_database test_ticket_db`, harness L3, rollback both files.
- PR5 S5b1: test `pytest` S5b1 set (pins), harness L3, rollback those 5 files.
- PR6 S5b2: test `pytest` S5b2 set (pins), harness L3, rollback those 7 files.
- PR7 S2: test `pytest test_tickets_cog`, harness L3 + dc371d0 diff empty, rollback `tests/test_tickets_cog.py`.
- PR8 S3a: test FULL `--cov` s42, gate ≥80% ea revert <80.50%, rollback `tests/test_setup_module_welcome.py`, `tests/test_setup_module_goodbye.py`.
- PR9 S3b1: test FULL `--cov` s42, same harness, rollback `tests/test_setup_panel_pickers.py`.
- PR10 S3b2: test FULL `--cov` s42, same harness, rollback `tests/test_live_catalog.py`, `tests/test_i18n.py:537`.
- PR11 S4: test `lint:ox`=0 + CI, node ≥22.6, rollback `dashboard/**`, `.github/workflows/code-quality.yml`.
- PR12 S6: test FULL `--cov` s42, harness trail <61,480, rollback re-measure only.

V1 = assert parity + falsification probe, KEEP-7 green, L3 ±.

## Pins (ec3d2fa)

S1 `tests/test_ticket_service.py` 4625 no drift — S1a `:1133-1229,:1970-2160`; S1b `:220-385,:2174-2330,:2448-2640`. S2 `tests/test_tickets_cog.py` 3455 no drift — no_guild `:693,:1087,:1295,:1371,:1439`, mod-gated `:1564-1579` (drift: 6 tests ~18 ln), unclaim `:2718-2870`, sweep `:3071-3270`; `:1621-1712` plus kick/ban `:295-510` aggressive-only. S5 — fixture `tests/test_database.py:228`, 24 guards (drift +1); `tests/test_ticket_db.py` 7 guards, `:294-330`; lock `:576-600`. Do-not-merge: success-vs-error, polarity, depth, parametrized. dc371d0 non-ancestor, i18n/pr2 byte-identical via cabdbca → skip. Weak asserts at `tests/test_live_catalog.py:87`, `tests/test_i18n.py:537` (model `:525`).

## Phase 1: S0

- [x] 1.1 Amend `openspec/specs/test-suite-governance/spec.md` (headroom, coexistence, buffer, GGA); green, delta 0.

## Phase 2: Cuts (parametrize each; V1 verifies)

- [x] 2.1 S1a ranges; −180.
- [x] 2.2 S1b ranges, countdown same-polarity only; −170 (actual −7: 4 groups merged — subject/description, sanitized-name, reopen-fallback, unclaim-denied; countdown family is do-not-merge, trio outside pins).
- [x] 2.3 S5a guards/filters/onwrite + ticket_db; −184 (actual −101: guards 30→2 matrices −110 net incl. format +14; filters 7→1 −3; onwrite 4→1 −3; close pair −5; ruff-format reflow +14).
- [x] 2.4 S5b1 invariants/greeting/helpers/infraction/realtime; −222 (actual −72 branch-local: invariants 6 groups +PLC0415 hoist −77; greeting quartets aggressive branched −62 +hoist −12; helpers 5 matrices −19; infraction trio −74 incl. +40 reflow; realtime 4 matrices −28; typefix +6; PR5 #111).
- [x] 2.5 S5b2 logging/audit/economy/config/migrations/views/sentinel-lock; −160 (actual −25 branch-local: logging 3 groups −12; audit 3 groups −19 incl. duplicate-row drop; greeting 3 groups +16 (dual-write 3-assert dense, positional-tuple compaction); migrations 2 quartets −7; economy 3 matrices −3; bot/ + migrations/ untouched — views/sentinel-lock groups NOT in this slice per orchestrator batch scope; PR6 #112; falsification 5/5; collected parity 3064; cov 81.99%).
- [x] 2.6 S2 no_guild/mod-gated/pairs; diff-check + skip; −85 (actual −26 branch-local: no_guild 7-row matrix −33 incl. sweep/repair pair; mod-gated sextet −3; unclaim denial pair −10; unclaim error-guard pair −12; GGA repair +32 (PLC0415 hoist, 2 pre-existing function-level imports); dc371d0 diff-check vs tests/test_i18n.py + test_pr2_expired_scans_red.py EMPTY at c0f6695 → removal-side dedups pre-landed, re-apply SKIPPED per gate; falsification 7/7; collected parity 146=146; cov 81.99%; PR7 #113). 2.7 GATE note (NOT checked — orchestrator measures): projected cumulative 61478 −30 −7 −101 −72 −25 −26 = 61,217 ≤ 61,380 (headroom 163), raw-line branch-local projection.
- [x] 2.7 GATE ≤61,380 else more cuts. (OFFICIAL, independently measured: cumulative 61,225 — margin 155; additive s1a/s1b merge-file validated; s1a yield corrected 30→22)
- [x] 2.8 S5c1 test_ticket_views helpers+merges + test_sentinel_cog helpers+aggressive cross-pairs (new-vein #5141; ~−370; actual −402 branch-local: views −250 (helpers H-V1..V5 + merges G-V1/V2/V4/V5/V8/V11/V12; G-V3/V6/V13/V14/V16 + generic-VE + required-empty + mod-role-valid NOT merged), sentinel −152 (H-S1/H-S3 + G-S3/S4/S5/S7 + G-S2 kick/ban cross-pairs; G-S1/S6/S9/S10/S11 + mute pair 700-736 NOT merged); falsification 7/7; collected 114 vs master 113 (+1 G-V12); cov 81.99%; split PR8a #114 + PR8b #115 (1790 > 800) + tracker #116)
- [x] 2.9 S5c2 economy-additional G-E1..G-E9/H-E1 + test_tickets_i18n + D3-proven deletions −35 (never-collected underscore tests :492-508,:544-560; ~−250; actual −126 branch-local: econ G-E1..E5/E8/E9+H-E1 983→846 (−137, incl. −80 parity repair dropping 3 originals duplicated by G-E1 rows), i18n G-I1/I2/I5/I6/I7 1009→973 (−36 net incl. +6 PLC0415 hoist), D3 −36 (never-collected underscore pair; proof: grep :485/:535 + collect-only empty + Group no-callback at tickets.py:569/:647); falsification 8/8; collected 108=108 (econ 47=47 exact 1:1, i18n 61=61); cov 81.99%; PR9 #117)

## Phase 3: Probes

- [ ] 3.1 S3a via `git show dc371d0:<path>` (read-only) → welcome/goodbye; FULL cov ≥80%.
- [ ] 3.2 S3b1 same → pickers; FULL cov ≥80%.
- [ ] 3.3 S3b2 same → live_catalog; harden `:87`,`:537`; cov ≥80%.

## Phase 4: Oxlint/Reconcile

- [ ] 4.1 S4 fix-all 321, drop `continue-on-error`, re-stamp, flip; `lint:ox` 0 + CI; split if >800.
- [ ] 4.2 S6 re-measure <61,480 trailed, cov ≥80.50%, `ty`/`ruff`/`vulture` 0.
- [ ] 4.3 Optional gated climbs: privacy ~75, kick/ban ~135, sweep/edit/audit.
