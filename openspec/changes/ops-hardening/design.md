# Design: ops-hardening

## Technical Approach

Implement this as an operations-only hardening slice: repair Supabase migration tracking for already-applied migrations 006-009, add two forward migrations, and complete one dashboard toggle. This maps to `rpc-least-privilege` by narrowing EXECUTE grants on the four existing member mutation RPCs, and to `initial-schema` by adding the missing `ticket("channelId")` index. No bot Python changes are part of this design.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| Migration drift repair | Insert rows into `supabase_migrations.schema_migrations` via Supabase MCP using `ON CONFLICT DO NOTHING`. | Re-run migrations 006-009; remove dashboard-generated orphan rows. | Production already has the DDL effects. Re-running DDL risks conflicts, and orphan realtime rows are harmless audit history. |
| RPC permission hardening | Add migration 010 that revokes EXECUTE from `anon` and `authenticated`, leaving `service_role`. | Modify migration 009; keep grants as-is. | Forward-only migration preserves history and applies least privilege to SECURITY DEFINER functions exposed through PostgREST. |
| Ticket lookup performance | Add migration 011 with `CREATE INDEX IF NOT EXISTS idx_ticket_channel ON public.ticket ("channelId")`. | Composite `(guildId, channelId)` index; no index. | Existing hot queries filter only by `channelId`; the index directly supports `get_ticket_by_channel` and `update_ticket_last_activity`. |
| Application scope | Zero bot Python changes. | Update database wrapper or service code. | `Database` already uses one Supabase key from env; production bot uses `service_role`, and RPC call signatures remain unchanged. |

## Data Flow

```text
Apply phase
  ├─ Supabase MCP SQL: mark 006-009 as applied
  ├─ migrations/010: revoke anon/authenticated RPC EXECUTE
  ├─ migrations/011: create ticket.channelId index
  └─ Dashboard: enable leaked password protection

Runtime after rollout
Bot service_role key ──→ Supabase RPCs ──→ member table updates
anon/authenticated ──X PostgREST RPC permission denied
Ticket commands/listeners ──→ ticket.channelId lookup ──→ idx_ticket_channel
```

No cache or Realtime CDC behavior changes are required because no bot-facing data model or Python write path changes.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `migrations/010_rpc_revoke_grants.sql` | Create | Revokes EXECUTE on the four member mutation RPCs from `anon` and `authenticated`. |
| `migrations/011_ticket_channel_index.sql` | Create | Adds idempotent index `idx_ticket_channel` on `public.ticket ("channelId")`. |
| `openspec/changes/ops-hardening/design.md` | Create | Technical design for this change. |
| `bot/**` | No change | Runtime code remains untouched. |

## Interfaces / Contracts

Migration repair SQL, executed later via Supabase MCP only:

```sql
INSERT INTO supabase_migrations.schema_migrations (version, name, executed_at)
VALUES
  ('006', '006_drop_user_table', NOW()),
  ('007', '007_realtime_publication', NOW()),
  ('008', '008_ticket_note_rls', NOW()),
  ('009', '009_member_increment_rpc', NOW())
ON CONFLICT (version) DO NOTHING;
```

Migration 010 must use the exact signatures from `migrations/009_member_increment_rpc.sql`:

```sql
REVOKE EXECUTE ON FUNCTION
  public.increment_member_xp(TEXT, TEXT, INTEGER),
  public.increment_member_coins(TEXT, TEXT, BIGINT),
  public.increment_member_warnings(TEXT, TEXT, INTEGER),
  public.set_member_daily(TEXT, TEXT, BIGINT, INTEGER, TIMESTAMPTZ, TIMESTAMPTZ)
FROM anon, authenticated;
```

Migration 011 contract:

```sql
CREATE INDEX IF NOT EXISTS idx_ticket_channel ON public.ticket ("channelId");
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit/structural | New migrations contain exact REVOKE signatures and idempotent index DDL. | Extend `tests/test_migrations.py`; run `uv run pytest tests/test_migrations.py`. |
| Integration/manual DB | Migration table rows, RPC grants, index existence. | Supabase MCP queries against `schema_migrations`, `information_schema.role_routine_grants`/advisor, and `pg_indexes`. |
| Regression | Bot code untouched and existing RPC wrappers still call same function names. | `git diff bot/` must be empty; run `uv run pytest` if code/test files change. |

## Migration / Rollout

1. Do not apply SQL to production during design.
2. During apply, create migrations 010 and 011 in repo.
3. During rollout, first repair `schema_migrations` for 006-009, then apply 010/011.
4. Enable leaked password protection manually in Supabase Dashboard.
5. Verify advisor warnings, index presence, and zero bot diff.

Rollback: delete repaired migration rows if needed, grant EXECUTE back to `anon, authenticated`, drop `idx_ticket_channel`, and disable the dashboard toggle.

## Open Questions

None.
