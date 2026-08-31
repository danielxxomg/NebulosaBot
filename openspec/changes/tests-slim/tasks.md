# Tasks: tests-slim

## Review Workload Forecast

| Slice | Est. | vs400 | vs1500 | PR |
|-------|------|-------|--------|----|
| S1 locale | 400-600 | Med | OK | test/tests-slim-s1→master |
| S2 factory | 500-800 | High | OK | test/tests-slim-s2→S1 |
| S3 cluster | 400-600 | Med | OK | test/tests-slim-s3→S2 |
| S4 deletions | 200-500 | Low | OK | test/tests-slim-s4→S3 |
| Total | 1500-2500 | Sliced | Sliced | stacked-to-master |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | PR | Focused test command | Runtime harness | Rollback |
|------|------|----|----------------------|-----------------|----------|
| 1 | S1 locale hoist | PR1 S1 | `pytest tests/test_*i18n.py -q --seed 42 --cov` | suite+ty/ruff/vulture+ledger | `revert S1` |
| 2 | S2 factory hoist | PR2 S2 | `pytest tests/test_greeting_*.py -q --seed 42 --cov` | same+random | `revert S2` |
| 3 | S3 cluster param | PR3 S3 | `pytest tests/test_greeting_service.py -k TestDispatchWelcome -q --seed 42 --cov` | same+N→M | `revert S3` |
| 4 | S4 deletions | PR4 S4 | `pytest -q --seed 42 --cov` | per-batch cov+ledger | `revert S4-batch` |

## Phase 1: S1 Locale Hoist

- [x] 1.1 Add `build_nested_locale`/`swap_suffix`/`load_test_locales` to `tests/conftest.py` import-only `bot.core.i18n` outermost [Isolation and drop documented]
- [x] 1.2 Hoist 5 carriers `id=es/en`: `sentinel:135` 680, `stellar:113` 343, `tickets` 1031, `utility:36` 218 `en=None`, `ocio:33` 138; keep `core_cog:37` [Suite green with cov floor; KEEP untouched]
- [x] 1.3 Gate: `pytest -q --seed 42 --cov` green ty/ruff/vulture 0 ledger `files A→B lines X→Y N→M cov→Z% seed 42` [Ledger present; KEEP green]

## Phase 2: S2 Factory Hoist

- [ ] 2.1 Audit 6 sigs vs `conftest:260` `make_member(*,roles,admin,member_id,display_name)`: `avatar_cache:23`, `native_kwargs:22`, `thread:16`, `greetings_cog:94`, `raid:45`, `ticket_helpers:244` [Isolation and drop documented]
- [ ] 2.2 Extend `conftest:260` shim for `guild_id` sites, direct else D1 [Suite green with cov floor]
- [ ] 2.3 Replace `_make_member` in 6+1 files with `from tests.conftest import make_member` [Suite green with cov floor]
- [ ] 2.4 Gate: suite green cov≥80.50% ty/ruff/vulture 0 random-order ledger [Ledger present]

## Phase 3: S3 Cluster Parametrize

- [ ] 3.1 Collapse 12 `TestDispatchWelcome` `test_greeting_service:621-870` to `id=welcome-disabled` D2 incl `552/575` [Isolation and drop documented]
- [ ] 3.2 Collapse economy twins `economy_service↔stellar_cog`/`stellar_i18n` D6 keep `stellar_i18n:261` [Suite green with cov floor]
- [ ] 3.3 Document `N→M` same assertions ids `es`/`en`/`welcome-disabled` + gate suite green cov≥80.50% ty/ruff/vulture 0 ledger [Isolation and drop documented; Ledger present]

## Phase 4: S4 Deletions LAST

- [ ] 4.1 Batch A delete 3 proven: `pr3_8ball:162→ephemeral`, `pr4_greetings:164→can(greeting.manage)`, `pr4_tickets:234→CheckFailure` `Proof:` [Deletion with twin accepted]
- [ ] 4.2 Batch B 12 need D3 `Proof: rg + twin` else SURVIVES: `hierarchy:186`, `intent:34`, `inventory:126`, `logging:128`, `banana:17`, `ocio_service:108`, `prek:314`, `service:178`, `voice:344`, `pr4a:167`, `pr4b:221`, `pr4c:235` [Deletion without proof rejected]
- [ ] 4.3 Per-batch `pytest --cov -q` revert `<80.50%→revert`; no squash; final ledger `184/61622/3005/80.50%→169-181/~57-59.5k` KEEP 7 green ty/ruff/vulture 0 [Deletion without proof rejected; Final target]

## Cross-Slice Invariants

- [ ] C.1 `bot/` untouched KEEP 7 untouchable ledger `files A→B lines X→Y N→M cov→Z% seed 42` `filterwarnings=error` `revert` per slice [KEEP untouched]
