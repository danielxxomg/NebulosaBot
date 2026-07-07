# Tasks: Runtime Bugfixes

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 250-300 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-chain |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | All 5 fixes (C1-C4 + S1) | PR 1 | Single PR — tightly related runtime bugfixes, ~250 lines total |

## Phase 1: Foundation

- [x] 1.1 **RED** — Test in `tests/test_migrations.py`: assert `006_drop_user_table.sql` contains 4 `DROP CONSTRAINT IF EXISTS` + `DROP TABLE IF EXISTS "user"`
- [x] 1.2 **GREEN** — Create `migrations/006_drop_user_table.sql`: drop 4 FK constraints then `DROP TABLE IF EXISTS "user"`
- [x] 1.3 Add constants to `bot/core/realtime.py`: `_received_count`, `_unhealthy_cycles`, `REALTIME_UNHEALTHY_ERROR_CYCLES = 3`

## Phase 2: Core Implementation

- [x] 2.1 **RED** — Write test in `tests/test_realtime.py`: pass nested SDK payload `{"data": {"type":"UPDATE","table":"guild","record":{"id":"G1"},"old_record":{}},"ids":[1]}` to `_handle_cdc`; assert cache invalidation fires
- [x] 2.2 **GREEN** — Add `_normalize_cdc_payload(payload, table_hint)` in `bot/core/realtime.py`: extract `data = payload.get("data", {})`, read `table`, `record`, `old_record`, `type` from `data`; return `(table or table_hint, record)`
- [x] 2.3 **REFACTOR** — Wire `_normalize_cdc_payload` into `_handle_cdc` replacing top-level `payload.get("record")` / `payload.get("table")` reads
- [x] 2.4 **RED** — Write test: send skipped payload; assert `_received_count` increments; assert watchdog uses `_received_count` not `_event_count`
- [x] 2.5 **GREEN** — Increment `_received_count` at top of `_handle_cdc` before any filtering; update watchdog to compare `_received_count`
- [x] 2.6 **RED** — Test: fake `WebSocketException` with `code`/`reason`; assert log contains close code; assert health escalation after 3 unhealthy cycles
- [x] 2.7 **GREEN** — `_wire_close_logging`: wrap `client._on_connect_error(e)` for close code/reason; wrap `channel.on_close()` for CLOSED state; escalate WARNING→ERROR after 3 cycles, reset on SUBSCRIBED
- [x] 2.8 **REFACTOR** — Extract `_record_for_event(data)` helper if `_normalize_cdc_payload` grew complex; ensure all paths tested

## Phase 3: Asset Fix

- [x] 3.1 **RED** — Write test in `tests/test_ocio_cog.py`: patch path existence; assert `discord.File` called with `filename="banana.webp"` and embed uses `attachment://banana.webp`
- [x] 3.2 **GREEN** — `git mv banana.png assets/images/banana.webp`; update `bot/cogs/ocio.py:25` path to `Path("assets/images/banana.webp")`; set filename to `"banana.webp"` in `discord.File`
- [x] 3.3 Delete `assets/images/banana.png` if present (422-byte placeholder)

## Phase 4: Integration Verification

- [x] 4.1 Run `uv run pytest` — all tests green (existing + new)
- [x] 4.2 Verify migration 006 SQL is idempotent (re-run produces no error)
- [x] 4.3 Verify no remaining references to `"user"` table in code or specs (grep check)

## Phase 5: Cleanup

- [ ] 5.1 Update `openspec/specs/initial-schema/spec.md` to remove `user` table and FK references (done by archive phase)
- [x] 5.2 Verify `banana.png` no longer exists at repo root after git mv
