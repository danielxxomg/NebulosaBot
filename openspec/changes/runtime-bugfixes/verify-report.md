## Verification Report

**Change**: `runtime-bugfixes`  
**Mode**: Strict TDD  
**Artifact store**: OpenSpec + Engram  
**Verified on**: 2026-07-07  
**Verdict**: **FAIL**

Runtime tests pass, lint passes, and the core C1-C4/S1 implementation is present. Verification still fails because Strict SDD requires every spec scenario to have a passing covering test, and several required scenarios are only partially covered or untested. `mypy` also reports errors in changed files.

---

### Completeness

| Metric | Value | Status |
|--------|-------|--------|
| Tasks total | 19 | ✅ |
| Tasks complete | 18 | ✅ |
| Tasks incomplete | 1 | ✅ expected |
| Deferred task | 5.1 archive-phase spec merge | ✅ allowed |
| Unchecked implementation tasks | 0 | ✅ none |

Task inspection source: `openspec/changes/runtime-bugfixes/tasks.md`. Tasks `1.1-4.3` and `5.2` are checked. Only `5.1` remains unchecked and is explicitly deferred to archive.

---

### Build & Tests Execution

#### Test command

Command:

```text
uv run pytest --tb=short -q
```

Result:

```text
761 passed, 3 skipped, 2 warnings in 8.96s
```

Status: ✅ runtime tests pass.

#### Coverage command

Command:

```text
uv run pytest --cov=bot --cov-report=term
```

Result:

```text
761 passed, 3 skipped, 1 warning in 8.41s
TOTAL 3718 statements, 760 missed, 80% coverage
bot/core/realtime.py 353 statements, 38 missed, 89% coverage
bot/cogs/ocio.py 33 statements, 1 missed, 97% coverage
```

Additional changed-file missing-line evidence was collected with `uv run pytest --cov=bot --cov-report=term-missing`:

```text
bot/core/realtime.py 353 Stmts, 38 Miss, 89%, Missing: 235-237, 255-257, 369, 410-411, 416-417, 422-423, 435, 438-439, 528-534, 592-594, 645-649, 681, 686, 748-752, 761, 772, 783
bot/cogs/ocio.py 33 Stmts, 1 Miss, 97%, Missing: 88
TOTAL 80%
```

#### Linter

Command:

```text
uv run ruff check bot/core/realtime.py bot/cogs/ocio.py
```

Result:

```text
All checks passed!
```

Status: ✅ no lint errors.

#### Type checker

Command:

```text
uv run mypy bot/core/realtime.py bot/cogs/ocio.py
```

Result:

```text
bot/core/realtime.py:540: error: Argument 1 to "_extract_guild_id" has incompatible type "str | None"; expected "str"  [arg-type]
bot/core/realtime.py:563: error: Argument 1 to "contains" of "RecentWriteSet" has incompatible type "str | None"; expected "str"  [arg-type]
bot/cogs/ocio.py:44: error: Argument 1 has incompatible type "Callable[[OcioCog, Context[Any], int], Coroutine[Any, Any, None]]"; expected "def (Never, Never, /, *Never, **Never) -> Coroutine[Any, Any, Never] | def (Never, /, *Never, **Never) -> Coroutine[Any, Any, Never]"  [arg-type]
bot/cogs/ocio.py:59: error: Argument 1 has incompatible type "Callable[[OcioCog, Context[Any]], Coroutine[Any, Any, None]]"; expected "def (Never, Never, /, *Never, **Never) -> Coroutine[Any, Any, Never] | def (Never, /, *Never, **Never) -> Coroutine[Any, Any, Never]"  [arg-type]
Found 27 errors in 8 files (checked 2 source files)
```

Status: ⚠️ type checker failed; 4 reported errors are in changed files.

---

### Source Inspection Evidence

| Claim | Evidence | Status |
|-------|----------|--------|
| C1 migration has 4 FK drops | `migrations/006_drop_user_table.sql:17-20` drops `member_userId_fkey`, `infraction_targetId_fkey`, `infraction_moderatorId_fkey`, `ticket_authorId_fkey` with `IF EXISTS` | ✅ |
| C1 migration drops user table | `migrations/006_drop_user_table.sql:25` has `DROP TABLE IF EXISTS "user";` | ✅ |
| Legacy FK references removed from final migration sequence | `006` removes them, but `migrations/001_initial_schema.sql` still creates `"user"` and 4 FK references | ⚠️ final state depends on running 006 |
| C2 received counter | `_received_count` exists and increments at top of `_handle_cdc` before filtering (`bot/core/realtime.py:538`) | ✅ |
| C2 watchdog uses received counter | `_watchdog_check_once` checks `_received_count == 0` (`bot/core/realtime.py:764`) | ✅ |
| C3 payload normalization | `_normalize_cdc_payload` extracts `data = payload.get("data", {})`, resolves `data.get("table") or table_hint`, and selects `record`/`old_record` through `_record_for_event` (`bot/core/realtime.py:81-108`) | ✅ |
| C3 callback table hint | `on_postgres_changes(... callback=lambda payload, t=table: self._cdc_callback(payload, t))` (`bot/core/realtime.py:375-381`) | ✅ |
| C4 close logging | `_wire_close_logging` wraps `client._on_connect_error(e)` and `channel.on_close()` (`bot/core/realtime.py:475-505`) | ✅ |
| C4 unhealthy escalation | `REALTIME_UNHEALTHY_ERROR_CYCLES = 3`; `_unhealthy_cycles` escalates to `logger.error` at threshold (`bot/core/realtime.py:46`, `663-668`) | ✅ |
| S1 root `banana.png` removed | Glob found no `banana.png` at repo root | ✅ |
| S1 WebP asset exists | `assets/images/banana.webp` exists | ✅ |
| S1 code references WebP | `bot/cogs/ocio.py:25`, `76-77` use `assets/images/banana.webp` / `banana.webp` | ✅ |

---

### Spec Compliance Matrix

Status meanings: ✅ COMPLIANT = covering test passed; ⚠️ PARTIAL = passing test covers only part of the scenario; ❌ UNTESTED = no covering passing test found.

#### `initial-schema`

| Requirement | Scenario | Covering test evidence | Result |
|-------------|----------|------------------------|--------|
| User table removed | User table and 4 FKs removed | `tests/test_migrations.py::test_migration_006_drops_four_fk_constraints`, `test_migration_006_drops_user_table` passed | ✅ COMPLIANT for Migration 006 |
| Migration 001 | Fresh install: four tables created and `user` table does not exist | No covering test for `migrations/001_initial_schema.sql`; grep shows `migrations/001_initial_schema.sql:27` still creates `"user"` | ❌ UNTESTED / implementation mismatch |
| Member table | Member insert succeeds without User row FK | Static SQL test verifies `member_userId_fkey` drop in Migration 006; no insert-level test found | ⚠️ PARTIAL |
| Infraction table | Infraction insert succeeds without User rows | Static SQL test verifies `infraction_targetId_fkey` and `infraction_moderatorId_fkey` drops in Migration 006; no insert-level test found | ⚠️ PARTIAL |
| Ticket table | Ticket insert stores `authorId` without FK enforcement | Static SQL test verifies `ticket_authorId_fkey` drop in Migration 006; no insert-level test found | ⚠️ PARTIAL |

#### `cache-sync-realtime`

| Requirement | Scenario | Covering test evidence | Result |
|-------------|----------|------------------------|--------|
| Payload table resolution | Payload includes table field | `tests/test_realtime.py::TestNormalizeCdcPayload::test_nested_sdk_payload_invalidates_guild` passed | ✅ COMPLIANT |
| Payload table resolution | Payload omits table field | `tests/test_realtime.py::TestNormalizeCdcPayload::test_table_hint_fallback_when_data_table_missing` passed | ✅ COMPLIANT |
| Payload table resolution | Unresolvable table logs warning and skips | Existing `ticket_note` unresolved/received-counter tests pass; warning behavior is covered by source inspection more than explicit log assertion | ⚠️ PARTIAL |
| Reconnection and health check | Healthy subscription logged | `test_healthy_subscribed_logs_debug` passed but asserts fallback state, not debug log content | ⚠️ PARTIAL |
| Reconnection and health check | Disconnected triggers poll fallback | `test_channel_error_over_60s_enables_fallback` passed; warning log content not asserted | ⚠️ PARTIAL |
| Reconnection and health check | Reconnection disables poll fallback and logs reconnection | `test_recovery_disables_fallback` / `test_poll_stops_on_recovery` passed; reconnection log not asserted | ⚠️ PARTIAL |
| Reconnection and health check | WebSocket close event logged | `test_on_connect_error_logs_close_code` passed; `test_channel_on_close_records_closed_state` passed | ✅ COMPLIANT |
| Reconnection and health check | Escalation after repeated unhealthy cycles | `test_health_escalation_after_three_unhealthy_cycles` passed | ✅ COMPLIANT |
| Migration prerequisite/watchdog | Events received within 5s and counter increments even if skipped | `TestReceivedCounter` tests passed for valid, skipped, and self-echo events; no live dashboard write test | ⚠️ PARTIAL |
| Migration prerequisite/watchdog | Migration not applied warning logged | `test_warns_after_30s_no_events` passed | ✅ COMPLIANT |
| Migration prerequisite/watchdog | Watchdog counts skipped events and no warning | `test_watchdog_uses_received_count` passed | ✅ COMPLIANT |
| Migration prerequisite/watchdog | Idempotent publication migration safe to re-run | No migration SQL containing `ALTER PUBLICATION supabase_realtime ADD TABLE ...` found; no covering test found | ❌ UNTESTED |

#### `ocio-commands`

| Requirement | Scenario | Covering test evidence | Result |
|-------------|----------|------------------------|--------|
| Banana command | Normal banana uses WebP path, filename, attachment URL, and measurement range | `test_banana_measurement_in_range`, `test_banana_file_uses_webp_filename`, `test_banana_embed_uses_webp_attachment_url`, `test_banana_uses_assets_images_path` passed | ✅ COMPLIANT |
| Banana command | Missing image asset returns error embed | `test_banana_missing_asset_shows_error` passed | ✅ COMPLIANT |

Compliance summary: 10 compliant, 7 partial, 2 untested/mismatch. Under SDD Verify rules, untested required scenarios are CRITICAL.

---

### Correctness Table

| Area | Status | Notes |
|------|--------|-------|
| C1 runtime FK cleanup | ✅ Implemented | Migration 006 is idempotent and contains all required drops. |
| C1 fresh-install spec wording | ❌ Not proven | Raw Migration 001 still creates `user` and User FKs; final state after all migrations depends on 006. |
| C2 watchdog spam fix | ✅ Implemented | `_received_count` separates received CDC events from processed invalidations. |
| C3 nested payload fix | ✅ Implemented | Handles realtime-py `{data, ids}` envelope and table hint fallback. |
| C4 close/reconnect observability | ✅ Implemented | Private SDK hook and channel close wrapper are present; escalation present. |
| S1 banana WebP path | ✅ Implemented | Asset exists and command references WebP. |
| Static quality | ⚠️ Mixed | Ruff passes; mypy fails. |

---

### Design Coherence Table

| Decision | Followed? | Evidence |
|----------|-----------|----------|
| C1: `006_drop_user_table.sql` has 4 `DROP CONSTRAINT IF EXISTS` + `DROP TABLE IF EXISTS "user"` | ✅ Yes | `migrations/006_drop_user_table.sql:17-25` |
| C2: `_received_count` increments at top; watchdog uses it | ✅ Yes | `bot/core/realtime.py:538`, `764` |
| C3: normalize nested SDK payload; table hint secondary fallback | ✅ Yes | `bot/core/realtime.py:101-107`; callback passes `t=table` |
| C4: wrap `_on_connect_error` and `channel.on_close`; escalation after 3 unhealthy cycles | ✅ Yes | `bot/core/realtime.py:475-505`, `663-668` |
| S1: root `banana.png` removed; `assets/images/banana.webp` present; code references WebP | ✅ Yes | glob + `bot/cogs/ocio.py:25`, `76-77` |

---

### TDD Compliance

Apply-progress artifact source: Engram observation `#721`, topic `sdd/runtime-bugfixes/apply-progress`.

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | TDD Cycle Evidence table found in Engram apply-progress. |
| All implementation tasks have tests | ✅ | C1-C4/S1 list test files or structural/static verification. |
| RED confirmed | ✅ | Referenced files exist: `tests/test_migrations.py`, `tests/test_realtime.py`, `tests/test_ocio_cog.py`. |
| GREEN confirmed | ✅ | Full suite passed: 761 passed, 3 skipped. |
| Triangulation adequate | ⚠️ | Implementation tasks are triangulated, but spec-level scenarios have partial/untested coverage listed above. |
| Safety net for modified files | ✅ | Apply-progress reports pre-change safety runs for modified test files; full suite now passes. |
| Refactor evidence | ✅ | Apply-progress records clean refactor for C1-C4/S1. |

**TDD Compliance**: Implementation-task TDD evidence is present, but spec-scenario coverage is insufficient for final PASS.

---

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit/static artifact tests | 22 change-related tests claimed/run | 3 | pytest, pytest-asyncio |
| Integration | Full suite run | multiple | pytest |
| E2E | 0 | 0 | Not used |

Change-related test files verified:

- `tests/test_realtime.py` — C2/C3/C4 unit tests.
- `tests/test_ocio_cog.py` — S1 unit tests.
- `tests/test_migrations.py` — C1 static SQL artifact tests.

---

### Changed File Coverage

| File | Line % | Branch % | Uncovered Lines | Rating |
|------|--------|----------|-----------------|--------|
| `bot/core/realtime.py` | 89% | N/A | 235-237, 255-257, 369, 410-411, 416-417, 422-423, 435, 438-439, 528-534, 592-594, 645-649, 681, 686, 748-752, 761, 772, 783 | ⚠️ Acceptable |
| `bot/cogs/ocio.py` | 97% | N/A | 88 | ✅ Excellent |
| `migrations/006_drop_user_table.sql` | N/A | N/A | SQL file; covered by static pytest assertions | ✅ Covered by artifact tests |

Average changed Python file coverage: 93%.

---

### Assertion Quality

No tautologies, ghost loops, or assertions without production/artifact access were found in the change-related tests. Some mock-call assertions exist in broader tests, but the new C1-C4/S1 coverage uses behavior/value assertions as well.

**Assertion quality**: ✅ No CRITICAL assertion-quality issues found.

---

### Quality Metrics

**Linter**: ✅ No errors.  
**Type Checker**: ⚠️ Failed — changed-file errors in `bot/core/realtime.py` and `bot/cogs/ocio.py`.  
**GGA hook**: ✅ Orchestrator reported the GGA pre-commit hook already ran and passed.  
**Non-blocking GGA observation**: SUGGESTION — `Path.exists()` is synchronous inside async command flow in `bot/cogs/ocio.py`; consider moving file I/O checks off the event loop if this path grows beyond a trivial metadata check.

---

### Issues Found

#### CRITICAL

1. **Spec scenario untested/mismatched: `initial-schema` / Migration 001 fresh install**  
   The delta spec says Migration 001 MUST NOT create the `user` table, but `migrations/001_initial_schema.sql` still creates `"user"` and 4 FKs to it. Migration 006 fixes final runtime state after all migrations, but the specific scenario is not covered as written.

2. **Spec scenario untested: idempotent `supabase_realtime` publication migration**  
   `cache-sync-realtime` requires the publication migration to be idempotent. No SQL containing `ALTER PUBLICATION supabase_realtime ADD TABLE ...` was found, and no covering test exists.

3. **Spec scenario coverage is partial for several log/assertion requirements**  
   Passing tests cover state transitions, but not all required logging assertions: healthy debug log, disconnected warning log, reconnection log, and unresolvable-table warning are not all directly asserted.

#### WARNING

1. `uv run mypy bot/core/realtime.py bot/cogs/ocio.py` exits non-zero. Four errors are in changed files; 27 total errors are reported across imported modules.
2. Insert-level DB behavior for Member/Infraction/Ticket FK removal is inferred from Migration 006 static SQL tests, not proven by insert-level migration execution tests.
3. Coverage warning emitted during test runs: `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` in existing ticket service tests.

#### SUGGESTION

1. Keep the GGA non-blocking observation: `Path.exists()` is sync in an async command (`bot/cogs/ocio.py:62`). It is probably harmless for a single local metadata check, but it is still worth revisiting if command asset handling grows.
2. Rename the stale test docstring `When banana.png is missing...` in `tests/test_ocio_cog.py:207` to avoid confusing future reviewers.

---

### Final Verdict

**FAIL**

The runtime implementation largely matches the design and the full pytest suite passes, but Strict SDD verification cannot pass while required spec scenarios are untested or mismatched and mypy fails on changed files. Recommended next step: remediate spec coverage/type-check issues, then rerun `sdd-verify` before archive.
