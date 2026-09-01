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

### Requirement: Suite Metrics Ledger — Per-Slice Measurement

Each slice MUST record before/after: files, lines (`find tests -name "*.py" -exec wc -l {} +`), collected (`--collect-only -q`), `--cov` total. Baseline 184/61,622/3005/80.50% @2bb4e89 → final target: 169-181 files (measured 180 ✓), strict line decrease from the 61,622 baseline with per-slice ledger (measured 60,939 ✓), cov ≥80.50% (held) — deeper line reduction is parked pending new twin evidence for the 11 documented survivors; ~57-59.5k derived from savings assumptions measurement disproved. Budget 1500/slice, stacked-to-master.

#### Scenario: Ledger present

- GIVEN slice PR opened
- WHEN commit body inspected
- THEN it shows `files: A→B`, `lines: X→Y`, `collected: N→M`, `cov: 80.50%→Z%`, seed 42

#### Scenario: Final target

- GIVEN all slices merged
- WHEN metrics measured
- THEN files within 169-181, lines strictly below the 61,480 S3-tip ledger with total ledger trail, cov ≥80.50%, `ty`/`ruff`/`vulture` 0
- AND every deletion in the diff carries D3 proof (FAIL-regardless-of-metrics if any unproved deletion appears)
