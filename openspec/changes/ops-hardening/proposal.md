# Proposal: ops-hardening

## Intent

Three prior audits (`audit-infra-pending`, `audit-supabase-practices`, `audit-docs-gaps`) identified overlapping ops/security gaps. This change consolidates the **actionable, low-risk** items: migration tracking drift that blocks safe future `supabase db push` runs, RPC functions callable by `anon`/`authenticated` when only `service_role` needs access, and a missing index on the most-queried ticket column. Zero bot code changes expected.

## Scope

### In Scope
- Repair migration tracking for 006–009 (INSERT into `supabase_migrations.schema_migrations`, NOT re-running DDL)
- New migration 010: `REVOKE EXECUTE` on 4 member RPCs from `anon` + `authenticated`
- New migration 011: `CREATE INDEX` on `ticket."channelId"`
- Manual checklist item: enable Auth Leaked Password Protection in Supabase Dashboard

### Out of Scope
- Bot UX features, code-quality, git branch cleanup
- RLS policy redesign on core tables
- Removing orphan dashboard realtime migration rows
- App Python code changes (zero expected)
- `updated_at` columns, N+1 elimination, SELECT * optimization

## Capabilities

### New Capabilities

- `rpc-least-privilege`: REVOKE EXECUTE on `increment_member_xp`, `increment_member_coins`, `increment_member_warnings`, `set_member_daily` from `anon` and `authenticated` roles. Only `service_role` retains access.

### Modified Capabilities

- `initial-schema`: Add index on `ticket."channelId"` (new requirement). RPC grant scope narrowed (existing functions, tighter permissions).

## Approach

**Single cycle, 3 artifacts, 0 code changes.**

1. **Migration repair** (SQL via Supabase MCP): INSERT 4 rows into `supabase_migrations.schema_migrations` for versions 006–009 with `executed_at = NOW()`. This marks already-applied migrations as tracked without re-executing their DDL.

2. **Migration 010** (`migrations/010_rpc_revoke_grants.sql`): REVOKE EXECUTE on the 4 SECURITY DEFINER functions from `anon` and `authenticated`. ~8 LOC. Bot always uses `service_role` (confirmed in `bot/core/db/base.py`).

3. **Migration 011** (`migrations/011_ticket_channel_index.sql`): `CREATE INDEX IF NOT EXISTS idx_ticket_channel ON public.ticket ("channelId")`. 1 LOC. Supports `get_ticket_by_channel` and `update_ticket_last_activity`.

4. **Manual**: Enable "Leaked Password Protection" in Supabase Dashboard → Settings → Auth. No code artifact.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `supabase_migrations.schema_migrations` | Modified | 4 new rows marking 006–009 as applied |
| `migrations/010_rpc_revoke_grants.sql` | New | REVOKE EXECUTE from anon/authenticated |
| `migrations/011_ticket_channel_index.sql` | New | Index on ticket.channelId |
| Supabase Dashboard Auth settings | Modified | Leaked password protection toggle |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Migration repair INSERT conflicts with existing rows | Low | Use `ON CONFLICT DO NOTHING` or check first via MCP |
| RPC revoke breaks dashboard if it uses anon key | Low | Verified: dashboard uses `service_role` for DB ops |
| Index creation locks ticket table briefly | Low | `CREATE INDEX` without `CONCURRENTLY` is fine at current row count (<10K) |

## Rollback Plan

- **Migration repair**: DELETE the 4 rows from `supabase_migrations.schema_migrations` WHERE version IN ('006','007','008','009').
- **Migration 010**: `GRANT EXECUTE ON ... TO anon, authenticated;` to restore prior grants.
- **Migration 011**: `DROP INDEX IF EXISTS idx_ticket_channel;`
- **Leaked password toggle**: Re-disable in dashboard.

## Dependencies

- Supabase MCP access for migration repair SQL and verification queries
- Supabase Dashboard access for leaked password toggle

## Success Criteria

- [ ] `supabase_migrations.schema_migrations` contains rows for 006–009
- [ ] Security advisor reports 0 warnings for RPC grant scope (down from 8)
- [ ] `pg_indexes` shows `idx_ticket_channel` on `ticket."channelId"`
- [ ] Leaked Password Protection shows ENABLED in dashboard
- [ ] Zero bot code changes — `git diff bot/` is empty
