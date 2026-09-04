# test-suite-governance Specification

## Purpose

Govern tests-only slimming (184 files, 61,622 ln, 3005 collected @2bb4e89, cov 80.50%). No product code.

## Requirements

### Requirement: KEEP Invariants — Must Not Be Modified or Deleted

The suite MUST preserve these guards; every slice MUST keep them green.

| File | Ln | Role |
|------|----|------|
| `test_comma_timer_invariant.py` | 42 | `,` trigger |
| `test_zero_hybrid_guard.py` | 49 | slash-only |
| `test_i18n_key_coverage.py` | 416 | `t()` keys |
| `test_s3d1_guardrails.py` | 325 | guardrails |
| `test_ops_observability.py` | 245 | OO-R3+Sentry |
| `property/test_economy_math.py` | 76 | Hypothesis |
| `test_rank_renderer_wiring.py` | 33 | `__slots__` behavioral |

Listeners (`test_audit_listener.py` 802, `test_xp_listener.py` 424) MUST stay observe+delegate.

#### Scenario: KEEP green

- GIVEN any slice applied
- WHEN KEEP suite runs (7 files above)
- THEN all pass, zero warnings

#### Scenario: KEEP untouched

- GIVEN slice diff
- WHEN changed files listed
- THEN none of 7 KEEP paths appears

### Requirement: Parametrization — Behavior-Preserving Hoist S1-S3

S1-S3 MUST preserve assertions per param case, keep seed 42 green, preserve isolation via `conftest.py:_isolate_i18n_state`. N→1 pass-count drop EXPECTED and MUST be documented; no assertion weakened.

S1 locale (5 `*i18n.py`): `sentinel_i18n` 680 (both), `utility_i18n` 218, `stellar_i18n` 343 (both), `ocio_i18n` 138, `tickets_i18n` 1031. 9 `def _load_i18n` total; `i18n.py` 903/`timer_embed` 145 carry neither.

S2 factory (6+1 → `conftest.py:make_member` 345): `greeting_avatar_cache:23`, `greeting_service_native_kwargs:22`, `greeting_service_thread:16`, `greetings_cog:94`, `greeting_service_raid:45`, `ticket_helpers:244`. 10 `def _make_member` total; 13 files mention it.

S3 cluster (`greeting_service.py` 1179): 12 `TestDispatchWelcome` 621,641,662,684,706,728,751,773,798,823,845,870 (+552/575 near). Economy twins: `economy_service` ↔ `stellar_cog`/`stellar_i18n`.

#### Scenario: Suite green with cov floor

- GIVEN S1/S2/S3 applied
- WHEN `uv run pytest --cov --cov-fail-under=80 --randomly-seed=42 -q` runs
- THEN green, `ty`/`ruff`/`vulture` 0, cov ≥80.50%

#### Scenario: Isolation and drop documented

- GIVEN hoisted helpers in `conftest.py`
- WHEN suite runs with `pytest-randomly` (seed 42 + random)
- THEN no order flake; commit documents `collected N→M` + "same assertions"

### Requirement: Deletion Proof Gate — Per-File Proof + Revert-on-Dip S4

S4 deletions MUST occur LAST. Each deleted file MUST carry proof: (a) live/parametrized twin (name it), OR (b) grep-equivalence. Per-batch `--cov` MUST be measured; ANY dip below 80.50% MUST revert. KEEP MUST NOT be candidate.

| Candidate | Ln | Guard | Twin |
|-----------|----|-------|------|
| `pr3_8ball_cooldown_red.py` | 162 | cooldown/locale | Proven: `test_8ball_command_ephemeral` |
| `pr4_greetings_red.py` | 164 | `greeting.manage` | Proven: `can("greeting.manage")` |
| `pr4_tickets_red.py` | 234 | `tickets.manage` | Proven: `CheckFailure` |
| `pr3_hierarchy_rls_flags_red.py` | 186 | hierarchy/RLS | Partial |
| `pr3_intent_red.py` | 34 | `voice_states` | No twin |
| `pr3_inventory.py` | 126 | guild-scope | No twin |
| `pr3_logging_red.py` | 128 | `log_voice_event` | Needs map |
| `pr3_ocio_banana_assets_red.py` | 17 | asset glob | No twin |
| `pr3_ocio_service_red.py` | 108 | OcioService | Needs map |
| `pr3_prek_replaces_precommit.py` | 314 | prek | No twin |
| `pr3_service_role_rls.py` | 178 | service_role | No twin |
| `pr3_voice_listener_red.py` | 344 | voice | Needs map |
| `pr4a/b/c_ruff*.py` | 167/221/235 | ruff | No twin |
| KEEP excluded: `rank_renderer_wiring` 33, `ops_observability` 245, `economy_math` 76 |

#### Scenario: Deletion with twin accepted

- GIVEN candidate has named twin, cov ≥80.50%
- WHEN file deleted with twin in commit
- THEN deletion accepted

#### Scenario: Deletion without proof or dip rejected

- GIVEN candidate lacks twin/grep-equivalence OR cov <80.50%
- WHEN reviewer measures batch
- THEN slice MUST be rejected/reverted

<!-- BEGIN DELTA: unified-pending-close (test-suite-governance) -->
### Requirement: Suite Metrics Ledger — Per-Slice Measurement

Each slice MUST record before/after: files, lines (`find tests -name "*.py" -exec wc -l {} +`), collected (`--collect-only -q`), `--cov` total. Baseline 175/62,384/3063/81.99% @9871add → lines strictly below 61,480 (the ONLY gate); files within 169-181. Ledger budget 1500 lines/slice bounds suite-size delta per slice and MUST NOT be conflated with the 800 diff-lines/PR review budget — distinct dimensions (suite growth vs reviewer load). Final aim ≤61,300 is ASPIRATIONAL with documented buffer, explicitly NOT a gate. Line-additive slices MUST satisfy the Slice Headroom Gate first. Restoration is parametrization-first: zero D3 deletions by default; any deletion still requires D3 proof per the FAIL-regardless-of-metrics gate below. Coverage scope: `bot/views/setup_modules/welcome.py`, `bot/views/setup_panel.py`, `bot/views/setup_modules/goodbye.py`, `bot/services/live_catalog.py` each to ~80%, funded by probes resurrected from dc371d0. The dashboard pagination unit (`dashboard/__tests__/app/audit-panel.test.tsx:122-169`) is excluded from the Python ledger.

(Previously: no headroom rule; 1500-vs-800 coexistence undocumented; aim read as gate.)

#### Scenario: Ledger present

- GIVEN slice PR opened
- WHEN commit body inspected
- THEN it shows `files: A→B`, `lines: X→Y`, `collected: N→M`, `cov: 80.50%→Z%`, seed 42

#### Scenario: Hard ceiling gates, aim does not

- GIVEN all slices merged
- WHEN metrics measured
- THEN lines strictly below 61,480 with total ledger trail, cov ≥80.50%, `ty`/`ruff`/`vulture` 0
- AND every deletion carries D3 proof (FAIL-regardless-of-metrics if any unproved deletion appears)
<!-- END DELTA: unified-pending-close (test-suite-governance) -->

<!-- BEGIN DELTA: unified-pending-close (test-suite-governance) -->
### Requirement: Slice Headroom Gate

Before any line-additive test slice lands, the ledger MUST show margin ≥100 lines above the ceiling (lines ≤61,380 at ceiling 61,480). Each slice MUST measure before/after with ledger trail; a slice that would breach the ceiling MUST NOT land.

#### Scenario: Headroom satisfied

- GIVEN ledger shows margin ≥100 above ceiling
- WHEN line-additive slice lands with before/after ledger
- THEN slice accepted, trail recorded

#### Scenario: Headroom blocks additive slice

- GIVEN ledger margin <100 above ceiling
- WHEN line-additive slice proposed
- THEN slice MUST NOT land until cuts restore margin

### Requirement: Assert Strength Standard

Weak `is not None` asserts MUST be replaced with exact-equality or isinstance where a concrete expected value exists (mirrors `tests/test_i18n.py:525`); hardening rides the probe slices.

#### Scenario: Weak assert hardened

- GIVEN probe slice touches a file with `is not None` asserts
- WHEN a concrete expected value exists
- THEN asserts use exact-equality/isinstance

### Requirement: Apply Staging Discipline

Apply commits MUST stage only intentional paths. The GGA hook is read-only (behavioral repro 2026-09-04: exit 0, index untouched; mechanism refuted, no upstream report).

#### Scenario: Intentional staging only

- GIVEN apply commit prepared
- WHEN staged paths listed
- THEN only intentional paths appear, hook leaves index untouched
<!-- END DELTA: unified-pending-close (test-suite-governance) -->
