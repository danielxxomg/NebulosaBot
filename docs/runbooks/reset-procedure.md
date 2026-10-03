# Runbook: Application Data Reset & Cleanup Procedure

> **DISCLAIMER: NO-EXECUTION SPECIFICATION**
> This document specifies procedures and SQL/inspection queries for documentation and runbook purposes only.
> **DO NOT EXECUTE THESE PROCEDURES DIRECTLY.**
> Any actual reset must proceed through explicit human sign-off, staging rehearsal, and coordinated maintenance windows.
> Zero statements or queries in this runbook have been executed during its creation.

---

## 1. Context and Scope

This runbook defines the controlled procedure for resetting application data in NebulosaBot while preserving:
1. **Project Schema & Migrations:** All tables, foreign key constraints (such as `018_ticket_integrity_fks`), triggers, indexes, and migration ledger rows (`supabase_migrations.schema_migrations`).
2. **Discord Application Identity:** Bot application credentials, tokens, OAuth configurations, and slash command tree registrations.

### Open Decision: Exact-Tables Candidate List
The decision on which exact tables are truncated or reset is **STILL OPEN** and pending stakeholder approval.
Candidate tables for application data reset:
- `tickets`
- `ticket_notes`
- `ticket_audit_logs`
- `ticket_categories`
- `infractions`
- `member_levels`
- `guild_configs` (requires explicit review due to panel and channel mappings)
- `crash_reports`

---

## 2. Phase 1: Pre-Reset Inventory (Read-Only)

Before any destructive operation, inspect and inventory bot-owned Discord channels and panels across all active guilds.

### 2.1 Discord Panel & Channel Inventory Queries (Read-Only)
Run read-only inspection queries against the database to identify active tickets, open channels, and deployed setup/ticket panels:

```sql
-- Inventory active guild configurations with deployed panels
SELECT
    guild_id,
    ticket_panel_channel_id,
    ticket_panel_message_id,
    ticket_category_id,
    log_channel_id,
    welcome_channel_id
FROM guild_configs
WHERE active = true;

-- Inventory open and active tickets
SELECT
    id,
    guild_id,
    channel_id,
    ticket_number,
    status,
    category_id,
    claimed_by
FROM tickets
WHERE status IN ('open', 'claimed');

-- Inventory ticket categories
SELECT
    id,
    guild_id,
    name,
    discord_category_id
FROM ticket_categories;
```

### 2.2 Discord UI Verification
Confirm in the Discord client:
- Which ticket channels exist and require archiving/closing.
- Which messages host active persistent components (`TicketPanelView`, `SetupPanelView`).

---

## 3. Phase 2: Explicit Human Approval Gate

A destructive reset **MUST NEVER** be automated or executed without an explicit, signed human approval document.

### Approver Checklist & Sign-Off Gate
The human operator must complete and sign this checklist before proceeding:

- [ ] **Guild ID Verification:** Exact list of targeted Discord Guild IDs confirmed:
      - Target Guild IDs: `____________________________________`
- [ ] **Panel Message Inventory:** Exact panel message IDs to be deleted or re-rendered:
      - Panel Message IDs: `____________________________________`
- [ ] **Active Ticket Channels:** Open ticket channels identified and archived or slated for deletion:
      - Channel IDs: `____________________________________`
- [ ] **Pre-Reset Backup Completed:** Verified that a fresh encrypted backup (`supabase-dump-encrypted`) exists and is retrievable within the 30-day retention window.
- [ ] **Exact Tables List Approved:** Human owner signed off on the exact subset of candidate tables to truncate/clear.
- [ ] **Maintenance Window Announced:** Bot taken offline or set to maintenance mode so background tasks (`@tasks.loop`) and listeners do not race against reset queries.

**Approver Name / Role:** `________________________________________`
**Date / Timestamp:** `________________________________________`
**Signature / Decision Reference:** `________________________________________`

---

## 4. Phase 3: Fresh-Guild Verification & Bot Re-Initialization

After database reset, verify system re-initialization and bot readiness.

### 4.1 `ensure_guild_exists` Semantics and `active = true`
- NebulosaBot relies on `GuildService.ensure_guild_exists(guild_id)` to initialize guild configuration rows.
- The `active` flag must be set to `true`.
- **Consequence of Skipping:** If `ensure_guild_exists` does not execute or fails to create/activate the configuration row, the web dashboard will throw `404 Not Found` errors when fetching guild configuration, and bot commands will fail closed.

### 4.2 Bot Startup & Background Backfill (`bot.py` `on_ready:710`)
During bot startup, `NebulosaBot.on_ready()` executes backfill of guild configs:
```python
# on_ready backfill pattern:
# asyncio.gather(*tasks, return_exceptions=True)
```
- **Gotcha / Critical Inspection:** Note that `return_exceptions=True` is used in `asyncio.gather(*tasks, return_exceptions=True)` at `on_ready:710` to prevent a single failing guild from aborting backfill for other guilds.
- **Verification Rule:** Operators must inspect the bot startup logs specifically for individual task exceptions within the gather result, ensuring that every connected guild successfully completes config backfill without silent exceptions.
- Following guild backfill, `_validate_panels()` inspects and self-heals stored panel messages.
