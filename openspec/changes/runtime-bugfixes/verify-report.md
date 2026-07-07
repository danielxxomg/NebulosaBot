## Verification Report

**Change**: `runtime-bugfixes`  
**Mode**: Strict TDD  
**Artifact store**: OpenSpec + Engram  
**Verified on**: 2026-07-07  
**Verification type**: Re-verify after remediation of prior FAIL  
**Verdict**: **PASS WITH WARNINGS**

Re-verification confirms the previously blocking issues were remediated: Migration 001 spec wording now allows the legacy create/drop sequence, Migration 007 exists with idempotency handling, realtime log assertions now use `caplog`, and `bot/core/realtime.py` passes targeted `mypy` and `ruff` checks. The remaining risks are pre-existing/out-of-scope or verification-depth limitations, not blockers for archive.

---

### Completeness

| Metric | Value | Status |
|--------|-------|--------|
| Proposal/design/specs/tasks read | Yes | ✅ |
| Tasks total | 19 | ✅ |
| Tasks complete | 18 | ✅ |
| Tasks incomplete | 1 | ✅ archive-only (`5.1`) |
| Unchecked implementation tasks | 0 | ✅ none |
| Previous CRITICAL items remediated | 3/3 | ✅ |
| Previous WARNING item remediated | 1/1 | ✅ |
| Runtime test command executed | Yes | ✅ |
| Targeted mypy executed | Yes | ✅ |
| Targeted ruff executed | Yes | ✅ |

Task inspection source: `openspec/changes/runtime-bugfixes/tasks.md`. Task `5.1` remains unchecked because it is explicitly for archive-phase spec merge.

---

### Build, Tests, Coverage, Mypy, Ruff Evidence

#### Runtime tests + coverage

Command:

```text
uv run pytest --tb=short -q
```

Result:

```text
766 passed, 3 skipped, 2 warnings in 8.82s
TOTAL 3721 statements, 762 missed, 80% coverage
bot/core/realtime.py 356 statements, 40 missed, 89% coverage
bot/cogs/ocio.py 33 statements, 1 missed, 97% coverage
```

Status: ✅ full runtime suite passes. Coverage is emitted by project pytest addopts (`--cov=bot --randomly-seed=42`).

#### Type checker

Command:

```text
uv run mypy bot/core/realtime.py
```

Result:

```text
Success: no issues found in 1 source file
```

Status: ✅ the two introduced `str | None` errors in `bot/core/realtime.py` are fixed.

#### Linter

Command:

```text
uv run ruff check bot/core/realtime.py
```

Result:

```text
All checks passed!
```

Status: ✅ no new ruff errors in the targeted changed runtime file.

#### Out-of-scope quality probes

```text
uv run ruff check tests/test_realtime.py --select B007
```

Result: `tests/test_realtime.py:1092` still reports pre-existing `B007` for an unused loop variable. This is out of scope and not introduced by the remediation.

```text
uv run mypy bot/cogs/ocio.py
```

Result: project/import graph still reports pre-existing typing errors, including `bot/cogs/ocio.py:44` and `bot/cogs/ocio.py:59` discord.py decorator type issues. These were explicitly out of scope for this re-verify.

---

### Source Inspection Evidence

| Claim | Evidence | Status |
|-------|----------|--------|
| Spec wording fixed for Migration 001 | `openspec/changes/runtime-bugfixes/specs/initial-schema/spec.md:14` says Migration 001 MAY create `user`, but Migration 006 MUST drop it | ✅ |
| Final migration state removes `user` table | `tests/test_migrations.py:583-620` covers final no-user-table state; `migrations/006_drop_user_table.sql:17-25` drops 4 FKs and table | ✅ |
| Publication migration exists | `migrations/007_realtime_publication.sql:16-24` adds required tables to `supabase_realtime` in a `DO` block | ✅ |
| Publication migration idempotency represented | `migrations/007_realtime_publication.sql:19-23` catches `duplicate_object`; tests at `tests/test_migrations.py:656-707` passed | ✅ |
| Realtime table None guard fixed | `bot/core/realtime.py:541-548` returns early when normalized table is `None` before `_extract_guild_id` / `contains` | ✅ |
| Healthy/disconnected/reconnected/unresolvable log assertions added | `tests/test_realtime.py:689-749` and `452-475` assert log content with `caplog` | ✅ |
| WebSocket close and escalation log assertions pass | `tests/test_realtime.py:1038-1103` covers close code/reason and ERROR escalation | ✅ |

---

### Spec Compliance Matrix

Status meanings: ✅ COMPLIANT = a covering test passed at runtime; ⚠️ PARTIAL = a passing test covers the behavior indirectly/static-artifact only or live external execution was not performed.

#### `initial-schema`

| Requirement | Scenario | Covering test evidence | Result |
|-------------|----------|------------------------|--------|
| User table removed | User table and 4 FKs removed | `test_migration_006_drops_four_fk_constraints`, `test_migration_006_drops_user_table`, `test_migration_006_is_idempotent` passed | ✅ COMPLIANT |
| Migration 001 | Fresh install: all migrations 001-006 leave no `user` table and no FK refs | `test_final_state_has_no_user_table_after_all_migrations`, `test_no_fk_references_to_user_table_in_final_schema` passed | ✅ COMPLIANT (static final-state proof) |
| Member table | Member insert succeeds without User row FK | FK drop is covered by Migration 006 tests; no live DB insert was executed | ⚠️ PARTIAL |
| Infraction table | Infraction insert succeeds without User rows | FK drops for `targetId` and `moderatorId` covered by Migration 006 tests; no live DB insert was executed | ⚠️ PARTIAL |
| Ticket table | Ticket insert stores `authorId` without FK enforcement | FK drop for `authorId` covered by Migration 006 tests; no live DB insert was executed | ⚠️ PARTIAL |

#### `cache-sync-realtime`

| Requirement | Scenario | Covering test evidence | Result |
|-------------|----------|------------------------|--------|
| Payload table resolution | Payload includes table field | `TestNormalizeCdcPayload::test_nested_sdk_payload_invalidates_guild` passed | ✅ COMPLIANT |
| Payload table resolution | Payload omits table field | `TestNormalizeCdcPayload::test_table_hint_fallback_when_data_table_missing` passed | ✅ COMPLIANT |
| Payload table resolution | Unresolvable table logs warning and skips | `test_ticket_note_unresolvable_skips_invalidation` passed with `caplog` warning assertion | ✅ COMPLIANT |
| Reconnection and health check | Healthy subscription logged | `test_healthy_subscribed_logs_debug` passed with `caplog` debug assertion | ✅ COMPLIANT |
| Reconnection and health check | Disconnected triggers poll fallback | `test_channel_error_over_60s_enables_fallback` passed with warning assertion | ✅ COMPLIANT |
| Reconnection and health check | Reconnection disables poll fallback and logs reconnection | `test_recovery_disables_fallback` and `test_poll_stops_on_recovery` passed | ✅ COMPLIANT |
| Reconnection and health check | WebSocket close event logged | `test_on_connect_error_logs_close_code` and `test_channel_on_close_records_closed_state` passed | ✅ COMPLIANT |
| Reconnection and health check | Escalation after repeated unhealthy cycles | `test_health_escalation_after_three_unhealthy_cycles` passed | ✅ COMPLIANT |
| Migration prerequisite/watchdog | Events received and skipped events increment watchdog counter | `TestReceivedCounter` tests passed for valid, skipped, self-echo, and watchdog paths | ✅ COMPLIANT |
| Migration prerequisite/watchdog | Migration not applied warning logged | `test_warns_after_30s_no_events` passed | ✅ COMPLIANT |
| Migration prerequisite/watchdog | Watchdog counts skipped events and no warning | `test_watchdog_uses_received_count` passed | ✅ COMPLIANT |
| Migration prerequisite/watchdog | Idempotent publication migration safe to re-run | `test_migration_007_file_exists`, `test_migration_007_adds_tables_to_realtime_publication`, `test_migration_007_is_idempotent` passed; SQL uses duplicate-object handling | ✅ COMPLIANT (static artifact proof) |

#### `ocio-commands`

| Requirement | Scenario | Covering test evidence | Result |
|-------------|----------|------------------------|--------|
| Banana command | Normal banana uses WebP path, filename, attachment URL, and measurement range | `test_banana_measurement_in_range`, `test_banana_file_uses_webp_filename`, `test_banana_embed_uses_webp_attachment_url`, `test_banana_uses_assets_images_path` passed | ✅ COMPLIANT |
| Banana command | Missing image asset returns error embed | `test_banana_missing_asset_shows_error` passed | ✅ COMPLIANT |

Compliance summary: all previously CRITICAL scenarios are now covered by passing runtime tests. DB insert/live migration execution remains static-artifact verified, so related database behavior is recorded as PARTIAL rather than overclaimed.

---

### Correctness Table

| Area | Status | Notes |
|------|--------|-------|
| C1 runtime FK cleanup | ✅ Implemented | Migration 006 drops all 4 User FKs and the vestigial `user` table. |
| C1 fresh-install/final-state wording | ✅ Remediated | Delta spec now matches implementation: Migration 001 MAY create `user`; Migration 006 MUST drop it. |
| C2 watchdog spam fix | ✅ Implemented | `_received_count` increments before filtering and watchdog checks received events. |
| C3 nested payload/table hint fix | ✅ Implemented | Nested realtime-py payloads and `table_hint` fallback are covered by passing tests. |
| C4 close/reconnect observability | ✅ Implemented | Close code/reason, healthy/disconnected/reconnected logs, and escalation are tested with `caplog`. |
| Realtime publication reproducibility | ✅ Implemented | Migration 007 adds the required CDC tables with duplicate-object handling. |
| S1 banana WebP path | ✅ Implemented | WebP path, filename, attachment URL, and missing-asset behavior pass tests. |
| Static quality | ✅ Targeted pass | `bot/core/realtime.py` passes targeted `mypy` and `ruff`. |

---

### Design Coherence Table

| Decision | Followed? | Evidence |
|----------|-----------|----------|
| C1: drop all 4 FK constraints and drop vestigial `user` table | ✅ Yes | `migrations/006_drop_user_table.sql:17-25`; migration tests pass. |
| C2: separate received event counter from processed invalidation counter | ✅ Yes | `bot/core/realtime.py:538`, `768-777`; received-counter tests pass. |
| C3: normalize nested SDK payload and use table hint as fallback | ✅ Yes | `bot/core/realtime.py:81-108`, `375-381`; normalization tests pass. |
| C4: wrap SDK close/error hooks and escalate repeated unhealthy cycles | ✅ Yes | `bot/core/realtime.py:475-505`, `665-689`; close/escalation tests pass. |
| Publication migration: reproducible Supabase Realtime table registration | ✅ Yes | `migrations/007_realtime_publication.sql:16-24`; Migration 007 tests pass. |
| S1: move banana asset to `assets/images/banana.webp` | ✅ Yes | Ocio WebP asset tests pass. |

---

### TDD Compliance

Primary TDD artifact source: Engram observation `#721`, topic `sdd/runtime-bugfixes/apply-progress`.

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | TDD Cycle Evidence table exists in apply-progress. |
| Original tasks have tests | ✅ | C1-C4/S1 list test files or structural/static verification. |
| RED confirmed | ✅ | Referenced files exist: `tests/test_migrations.py`, `tests/test_realtime.py`, `tests/test_ocio_cog.py`. |
| GREEN confirmed | ✅ | Full suite now passes: 766 passed, 3 skipped. |
| Remediation tests present | ✅ | Final-state migration tests, Migration 007 tests, and `caplog` assertions are present and passing. |
| Remediation write-order provenance | ⚠️ | No separate remediation apply-progress artifact was found; final git state proves tests+fixes exist, but not exact write order. |
| Safety net | ✅ | Full suite, targeted mypy, and targeted ruff were executed in this re-verify. |

**TDD Compliance**: ✅ sufficient for archive readiness, with a provenance warning for the remediation cycle order.

---

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit/static artifact tests | Change-related tests in `tests/test_migrations.py`, `tests/test_realtime.py`, `tests/test_ocio_cog.py` | 3 | pytest, pytest-asyncio |
| Integration/full-suite safety | Full test suite | multiple | pytest |
| E2E/live DB | 0 | 0 | Not used in this re-verify |

---

### Changed File Coverage

| File | Line % | Branch % | Uncovered Lines | Rating |
|------|--------|----------|-----------------|--------|
| `bot/core/realtime.py` | 89% | N/A | Not expanded by default pytest coverage output | ⚠️ Acceptable |
| `bot/cogs/ocio.py` | 97% | N/A | Not expanded by default pytest coverage output | ✅ Excellent |
| `migrations/006_drop_user_table.sql` | N/A | N/A | Covered by static pytest assertions | ✅ Covered |
| `migrations/007_realtime_publication.sql` | N/A | N/A | Covered by static pytest assertions | ✅ Covered |

Aggregate project coverage from the executed pytest command: 80%.

---

### Assertion Quality

No tautologies, ghost loops, or assertions without production/artifact access were found in the reviewed change-related tests. The new remediation assertions check concrete behavior or SQL content: final migration state, publication SQL/idempotency mechanism, and actual `caplog` log messages.

**Assertion quality**: ✅ no CRITICAL assertion-quality issues found.

---

### Issues Found

#### CRITICAL

None.

#### WARNING

1. **Live DB execution not performed** — migration final state and publication idempotency are verified by passing static SQL artifact tests, not by applying migrations against a real Postgres/Supabase database in this verify run.
2. **Remediation TDD order cannot be independently proven** — tests and fixes are present and passing, but no separate remediation apply-progress artifact records RED-before-GREEN ordering.

#### OUT OF SCOPE / PRE-EXISTING

1. `tests/test_realtime.py:1092` still has ruff `B007` for unused loop variable `i`; verified with `uv run ruff check tests/test_realtime.py --select B007` and accepted as pre-existing/out-of-scope.
2. `bot/cogs/ocio.py:44` and `bot/cogs/ocio.py:59` still have discord.py decorator typing issues when checking `bot/cogs/ocio.py`; accepted as pre-existing/out-of-scope.
3. Full pytest run still emits two `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` warnings in ticket service tests; not introduced by this remediation.

#### SUGGESTION

1. If future verification needs stronger proof for migration behavior, add an isolated Postgres migration execution harness that applies 001-007 twice and asserts final catalog state.

---

### Final Verdict

**PASS WITH WARNINGS**

The remediation clears all previously blocking findings. Proceed to `sdd-archive`, while carrying the noted live-DB/TDD-provenance warnings as non-blocking follow-up context.
