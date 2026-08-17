# Live Evidence — Pending (read-only refresh, 2026-08-12)

Read-only evidence refreshed for the `product-artifact-audit` change PR1
slice. Supabase facts were re-probed live on **2026-08-12** via the Supabase
MCP `execute_sql` tool using **SELECT-only** queries. No ticket row was
inserted, updated, or deleted; no Discord state was mutated; no migration was
applied or reversed.

## Schema / Deployment (verified live, read-only)

| Fact | Verified result (2026-08-12) |
|---|---|
| Project status | `ACTIVE_HEALTHY` (ref `vozkcckiybebhcclrasa`, sa-east-1) |
| Migration 015 applied | `supabase_migrations.schema_migrations` → `20260713153020 / 015_ticket_lifecycle_reliability` |
| `ticket.closeReason` nullable | Yes (`is_nullable = YES`) |
| `ticket.channelId` / `guildId` / `status` | NOT NULL |
| Required ticket indexes | `idx_ticket_active_channel`, `idx_ticket_active_slot`, `idx_ticket_channel`, `idx_ticket_guild_number`, `idx_ticket_guild_status`, `idx_ticket_guild_ticket_number`, `idx_ticket_parent` all present |
| Realtime publication (`supabase_realtime`) | `greeting_config`, `guild`, `ticket`, `ticket_note` — exactly the four required tables |
| Active ticket rows | 3 (all `claimed`, all with non-null `channelId`): #3 `c9cb89fa…` channel `1524826303507730563`, #16 `e5d39783…` channel `1527169412849995788`, #17 `62dd4973…` channel `1527174095249215588` (guild `1518709129403695154`) |

This proves **schema readiness only**. It does NOT prove those Discord
channels currently exist.

## Per-ticket Discord corroboration — PENDING

Discord channel existence for tickets #3, #16, #17 is **not verifiable from
the DB alone** and was **not probed from this worker**. A live Discord
gateway login is required for a safe read-only channel check; running it from
the apply worker risks event-driven side effects and is therefore deferred.

- Ticket #3 `channelId=1524826303507730563` — existence UNVERIFIED (pending)
- Ticket #16 `channelId=1527169412849995788` — existence UNVERIFIED (pending)
- Ticket #17 `channelId=1527174095249215588` — existence UNVERIFIED (pending)

**Automatic repair stays disabled** until per-ticket Discord corroboration is
performed and recorded. This file does not claim `resolved`; the G.2 live
gate is `gate_unresolved` for Discord corroboration by design.

## Advisor findings (explicit non-goals)

Security Advisor reported 1 WARN (leaked-password protection) + 9 INFO
(`rls_enabled_no_policy`). These are out of scope for this change: they do
not block schema readiness and never authorize repair (see
`specs/database-layer/spec.md` non-goals).

## SQL probes used (all read-only)

1. `SELECT id, "ticketNumber", "guildId", "channelId", status, "closeReason", "createdAt" FROM ticket WHERE status IN ('open','claimed') ORDER BY "ticketNumber" LIMIT 10;`
2. `SELECT version, name FROM supabase_migrations.schema_migrations WHERE name LIKE '%015%' ORDER BY version DESC LIMIT 3;`
3. `SELECT column_name, is_nullable FROM information_schema.columns WHERE table_name = 'ticket' AND column_name IN ('closeReason','channelId','guildId','status');`
4. `SELECT indexname, tablename FROM pg_indexes WHERE tablename = 'ticket' ORDER BY indexname;`
5. `SELECT tablename FROM pg_publication_tables WHERE pubname = 'supabase_realtime' ORDER BY tablename;`

## Boundary

- No ticket/audit/guild row was written by this refresh.
- No Discord API call was made.
- `evidence_verified_at=2026-08-11` facts remain the recorded snapshot; the
  refreshed facts above supersede them for freshness.
