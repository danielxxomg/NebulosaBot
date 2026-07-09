## Exploration: ops-hardening — Migration Drift, RPC Security, Minor Index

### Current State

NebulosaBot has 10 repo migrations (001–009), 4 SECURITY DEFINER RPCs, and 8
tables with RLS enabled but no policies (by design — bot uses `service_role`).
Prior audits (`audit-infra-pending`, `audit-supabase-practices`,
`audit-docs-gaps`) identified overlapping ops/security gaps. This exploration
synthesizes only the **actionable, low-risk** items into one focused cycle.

### Supersedes / Consume

| Audit Folder | Lines Consumed | Lines NOT Consumed |
|---|---|---|
| `audit-infra-pending` | §1.1 (migration drift), §1.2 (RPC security + leaked pw), §1.3 (unused indexes — informational only) | §2 (bot config/deploy), §3 (dashboard), §4 (deferred features), §5 (half-finished cycles), §6 (tech debt) |
| `audit-supabase-practices` | §17 (RPC grant scope), §6 (channelId index) | §1–5, §8–16, §18–20 (all other checklist items — future cycles) |
| `audit-docs-gaps` | None directly — deploy/security bits overlap with infra-pending | Full file — UX, specs, deferred features, critical bugs |

**Not consumed** (out of scope, parked for future cycles):
- `audit-bot-ux-qa` — UX features, not ops
- `audit-git-hygiene` — branch cleanup, already clean
- `audit-test-ci-quality` — CI/test layering, separate concern

---

### Migration Sync Matrix

| # | Repo File | Supabase Migration Table | Applied in Prod? | Action |
|---|-----------|--------------------------|------------------|--------|
| 001 | `001_initial_schema.sql` | ✅ `20260703175331` | ✅ | None |
| 002 | `002_ticket_categories.sql` | ✅ `20260703175351` | ✅ | None |
| 003 | `003_economy_config.sql` | ✅ `20260703175355` | ✅ | None |
| 003b | `003_subtickets_notes.sql` | ✅ `20260704070621` | ✅ | None |
| 004 | `004_greeting_config.sql` | ✅ `20260703175357` | ✅ | None |
| 005 | `005_ticket_audit.sql` | ✅ `20260703175501` (name: `005_rls_secure_default`) | ✅ | **Name mismatch** — repo says `ticket_audit`, table says `rls_secure_default`. Cosmetic only; no action. |
| 006 | `006_drop_user_table.sql` | ❌ Not tracked | ✅ (user table dropped) | **Repair**: `supabase migration repair --status applied 006` or reconciliation INSERT |
| 007 | `007_realtime_publication.sql` | ❌ Not tracked | ✅ (publication live) | **Repair**: `supabase migration repair --status applied 007` |
| 008 | `008_ticket_note_rls.sql` | ❌ Not tracked | ✅ (RLS on ticket_note) | **Repair**: `supabase migration repair --status applied 008` |
| 009 | `009_member_increment_rpc.sql` | ❌ Not tracked | ✅ (4 RPCs exist) | **Repair**: `supabase migration repair --status applied 009` |

**Orphan entries** (in Supabase table but NOT in repo):
- `20260705033007` — `add_tables_to_realtime_publication`
- `20260705033822` — `add_realtime_publication_tables`

These are Supabase dashboard-generated migrations from enabling Realtime on
tables via the UI. They duplicate migration 007's intent. **Action**: leave
them — they don't conflict and removing them risks migration table corruption.

**Repair plan for 006–009**:
```bash
# Option A: CLI repair (requires supabase CLI linked to project)
supabase migration repair --status applied 006 007 008 009

# Option B: Direct SQL if CLI not linked
INSERT INTO supabase_migrations.schema_migrations (version, name, executed_at)
VALUES
  ('006', '006_drop_user_table', NOW()),
  ('007', '007_realtime_publication', NOW()),
  ('008', '008_ticket_note_rls', NOW()),
  ('009', '009_member_increment_rpc', NOW());
```

---

### RPC Security — Current State (verified via MCP)

All 4 SECURITY DEFINER functions are callable by `anon` and `authenticated`
roles via PostgREST (`/rest/v1/rpc/*`). Security advisors confirm 8 WARN
findings (4 anon + 4 authenticated).

**Functions**: `increment_member_xp`, `increment_member_coins`,
`increment_member_warnings`, `set_member_daily`

**Current GRANT** (migration 009, lines 106–111):
```sql
GRANT EXECUTE ON FUNCTION ... TO anon, authenticated, service_role;
```

**Proposed REVOKE** (new migration 010):
```sql
REVOKE EXECUTE ON FUNCTION
    public.increment_member_xp(TEXT, TEXT, INTEGER),
    public.increment_member_coins(TEXT, TEXT, BIGINT),
    public.increment_member_warnings(TEXT, TEXT, INTEGER),
    public.set_member_daily(TEXT, TEXT, BIGINT, INTEGER, TIMESTAMPTZ, TIMESTAMPTZ)
FROM anon, authenticated;
```

After this, only `service_role` can call the RPCs. The bot always uses
`service_role` (confirmed in `bot/core/db/base.py`). No code changes needed.

---

### Leaked Password Protection

**Status**: DISABLED (verified via MCP security advisor `auth_leaked_password_protection`).

**Fix**: Supabase Dashboard → Settings → Auth → Enable "Leaked Password
Protection". One toggle, no code change. Low priority since the dashboard is
single-user (bot owner), but still a best-practice gap.

---

### Index: `ticket.channelId` — Missing (verified via MCP)

`get_ticket_by_channel` and `update_ticket_last_activity` filter by
`channelId` (TEXT column, no FK — confirmed in migration 001). No index exists
(verified via `pg_indexes` query — empty result).

**Proposed migration** (3 LOC):
```sql
CREATE INDEX IF NOT EXISTS idx_ticket_channel ON public.ticket ("channelId");
```

This is <50 LOC and high-value for ticket resolution performance. Included in
this cycle.

---

### Out of Scope (parked for future cycles)

| Item | Why Out of Scope |
|------|-----------------|
| `updated_at` columns on guild/greeting_config | Requires trigger + schema change — medium effort, low urgency |
| N+1 elimination (update_member_xp 2-step) | Code change + RPC modification — separate SDD cycle |
| SELECT * optimization | High maintenance cost, low impact at current scale |
| RLS policies on core tables | Needs dashboard access model verification first |
| `.env.example` WEBHOOK_* vars | Config docs, not ops hardening |
| openspec/config.yaml stale coverage | Config hygiene, not ops |
| Pterodactyl redeploy | Requires user action (no API access) |
| Deferred UX features | Product decisions, not ops |
| jscpd / git branch cleanup | Already clean per audit-git-hygiene |
| Cog layering / test quality | audit-test-ci-quality scope |

---

### Affected Areas

- `migrations/010_rpc_revoke_grants.sql` — NEW: revoke EXECUTE from anon/authenticated
- `migrations/011_ticket_channel_index.sql` — NEW: add channelId index
- Supabase migration table — repair 006–009 tracking
- Supabase Dashboard — toggle leaked password protection

---

### Approaches

1. **Single migration (010) combining RPC revoke + index** — One file, ~15 LOC
   - Pros: Minimal file count, one review pass
   - Cons: Mixes security and index concerns
   - Effort: Low

2. **Two separate migrations (010 + 011)** — RPC revoke in 010, index in 011
   - Pros: Clean separation of concerns, atomic rollback
   - Cons: Two files instead of one
   - Effort: Low

3. **Migration repair + new migrations** — Repair 006–009 tracking AND add 010/011
   - Pros: Fixes drift AND adds security/index fixes in one cycle
   - Cons: Migration repair requires CLI access or direct SQL
   - Effort: Low–Medium

### Recommendation

**Approach 3** — Full reconciliation. The migration drift (006–009 untracked)
is the root cause; fixing it prevents future `supabase db push` surprises.
Combined with the RPC security fix and channelId index, this is a tight
~30-line change set with zero code impact.

The leaked password protection toggle is a manual dashboard action — include
it as a task in the proposal but it has no code artifact.

### Risks

- **Migration repair requires CLI access**: If `supabase` CLI isn't linked,
  direct SQL INSERT into `supabase_migrations.schema_migrations` is the
  fallback. Both paths are well-documented.
- **Orphan migration entries**: The two dashboard-generated Realtime
  migrations (`add_tables_to_realtime_publication`,
  `add_realtime_publication_tables`) are left as-is. Removing them could
  break the migration table sequence.
- **RPC revoke is immediate**: After the REVOKE, any code path using anon or
  authenticated keys to call these RPCs will fail. Verified: bot always uses
  `service_role`. Dashboard uses `service_role` for DB operations.

### Ready for Proposal

**Yes**. This is a low-risk, high-value ops hardening cycle:

1. Repair migration tracking for 006–009 (SQL or CLI)
2. New migration 010: REVOKE EXECUTE on 4 RPCs from anon/authenticated
3. New migration 011: CREATE INDEX on ticket.channelId
4. Manual task: Enable leaked password protection in Supabase Dashboard

Total estimated effort: ~30 LOC + 1 dashboard toggle. Zero code changes to
the bot or dashboard. The orchestrator should tell the user:

> "Prior audits found 3 ops gaps: (1) migrations 006–009 applied manually but
> not tracked in the migration table, (2) 4 RPC functions callable by anon and
> authenticated roles when only service_role needs access, (3) missing index
> on ticket.channelId. All are low-risk fixes with zero bot code changes.
> Ready to propose."
