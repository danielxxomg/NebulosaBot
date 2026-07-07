# Archive Report: default-ticket-categories-and-smoke-fixes

**Status**: SUPERSEDED — do not implement this change as written.

**Archived**: 2026-07-07

## Why superseded

The exploration `exploration.md` contains a **false claim** about the Supabase Realtime publication that was disproved by the `audit-code-arch-tooling` exploration (verified via Supabase MCP):

> "No CDC events received — check that supabase_realtime publication includes the required tables"

The exploration interpreted this warning as evidence that the publication was not configured. **This is false.** The `supabase_realtime` publication IS configured with all 4 required tables (`guild`, `greeting_config`, `ticket`, `ticket_note`). The warning fires because of two real bugs in `bot/core/realtime.py`:

1. `_extract_guild_id` receives `table=None` for `guild` table CDC events (the SDK payload structure differs from what the code assumes) — so events are received but skipped.
2. The watchdog `_event_count` counter only increments for PROCESSED events, not RECEIVED events — so skipped events don't reset the watchdog and it spams every 30s.

Live log evidence: `CDC event for None could not resolve a guild_id — skipping` fires immediately after every `Ticket panel deployed` / PATCH on the `guild` table (timestamps 19:04:01, 19:09:20, 19:09:50, 20:10:37 in mclo.gs/I3SHKmN).

## Scope redistribution

The original exploration's scope has been redistributed across two new SDD changes with corrected findings:

| Original scope item | New change | Corrected finding |
|---|---|---|
| FK XP error (`member.userId_fkey`) | `runtime-bugfixes` (C1) | FK is real (`migrations/001_initial_schema.sql:39`), `user` table is vestigial (bot never writes to it). Fix: drop the FK via migration. |
| Realtime "No CDC events" warning | `runtime-bugfixes` (C2, C3) | Publication IS configured. Bugs are `_extract_guild_id` (table=None) + watchdog counter semantics. |
| Realtime reconnect resilience | `runtime-bugfixes` (C4) | WebSocket 1006 at 20:29:21 — relies on SDK reconnect, no explicit bot-level resilience. |
| Default ticket category seeding | `setup-wizard-and-ticket-ux` | Seeding merged with `/setup` wizard for proactive admin UX. |
| Unique constraint `(guildId, name)` | `setup-wizard-and-ticket-ux` | Same — bundled with seeding. |
| "Not Configured" error message | `setup-wizard-and-ticket-ux` | Fixed by the `/setup` wizard that guides the admin through setting `ticketCategoryId`. |

## Lessons

- **Verify infrastructure claims against the live system before building fixes.** The original exploration assumed the warning text was literal evidence; the audit verified via MCP that the publication was correctly configured.
- **Watchdog counters must track RECEIVED events, not PROCESSED events**, or they produce misleading "no events" warnings when events arrive but fail processing.
