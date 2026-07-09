# Tasks: ops-hardening

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 60–90 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

## Phase 1: Migration Files

- [x] 1.1 Create `migrations/010_rpc_revoke_grants.sql` — REVOKE EXECUTE on `increment_member_xp`, `increment_member_coins`, `increment_member_warnings`, `set_member_daily` FROM `anon`, `authenticated`. Use exact signatures from migration 009.
- [x] 1.2 Create `migrations/011_ticket_channel_index.sql` — `CREATE INDEX IF NOT EXISTS idx_ticket_channel ON public.ticket ("channelId");` with idempotency comment.

## Phase 2: Structural Tests (TDD)

- [x] 2.1 RED: Add `TestMigration010` class to `tests/test_migrations.py` — assert file exists, contains REVOKE for all 4 functions, targets `anon` and `authenticated`, uses exact function signatures with correct param types.
- [x] 2.2 GREEN: Run `uv run pytest tests/test_migrations.py::TestMigration010` — all pass against 1.1 file.
- [x] 2.3 RED: Add `TestMigration011` class to `tests/test_migrations.py` — assert file exists, contains `CREATE INDEX IF NOT EXISTS`, index name `idx_ticket_channel`, targets `public.ticket ("channelId")`.
- [x] 2.4 GREEN: Run `uv run pytest tests/test_migrations.py::TestMigration011` — all pass against 1.2 file.

## Phase 3: Apply & Verify (via Supabase MCP)

- [x] 3.1 Repair migration tracking: INSERT rows for 006–009 into `supabase_migrations.schema_migrations` with `ON CONFLICT (version) DO NOTHING`.
- [x] 3.2 Apply migration 010 via Supabase MCP `apply_migration`.
- [x] 3.3 Apply migration 011 via Supabase MCP `apply_migration`.
- [x] 3.4 Verify: `get_advisors` type=security reports 0 RPC grant warnings (down from 8).
- [x] 3.5 Verify: `execute_sql` query on `pg_indexes` confirms `idx_ticket_channel` exists on `ticket."channelId"`.
- [x] 3.6 Verify: `git diff bot/` is empty — zero bot code changes.

## Phase 4: Manual Checklist

- [ ] 4.1 Enable "Leaked Password Protection" in Supabase Dashboard → Settings → Auth.
- [ ] 4.2 Confirm toggle shows ENABLED in dashboard.
