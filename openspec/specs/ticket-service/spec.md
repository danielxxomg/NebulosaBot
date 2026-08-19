# Ticket Service Specification

## Purpose

Define ticket lifecycle management: creation, claim, close, and automatic closure after inactivity.

## Requirements

### Requirement: Ticket creation

The system MUST create a new ticket channel with a sequential ticket number per guild. `create_ticket()` SHALL accept optional `subject: str | None`, `description: str | None`, and `custom_fields: dict | None` parameters and persist them to the database. Channel names MUST use `sanitize_channel_name()` format (`{category}-{username}-{number}`).

#### Scenario: Successful creation

- GIVEN a guild with ticket category configured
- WHEN a user opens a ticket
- THEN a channel is created with `sanitize_channel_name()` format and a Ticket row is inserted with status `open`

#### Scenario: Sequential numbering

- GIVEN the highest existing ticket number in the guild is 12
- WHEN a new ticket is created
- THEN the new ticket number is 13

#### Scenario: Race condition retry

- GIVEN two tickets are created simultaneously and both read ticket number 13
- WHEN the first insert succeeds
- THEN the second attempt MUST retry with ticket number 14 within 3 attempts

#### Scenario: Creation with subject and description

- GIVEN subject="Login broken" and description="Cannot access since Monday"
- WHEN `create_ticket(subject=..., description=...)` is called
- THEN the Ticket row includes subject="Login broken" and description="Cannot access since Monday"

#### Scenario: Creation without subject and description

- GIVEN no subject or description arguments
- WHEN `create_ticket()` is called
- THEN the Ticket row has subject=null and description=null

#### Scenario: Creation with custom_fields

- GIVEN `custom_fields = {"player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/..."}`
- WHEN `create_ticket(custom_fields=...)` is called
- THEN the Ticket row includes `customFields` with the provided dict

#### Scenario: Creation without custom_fields

- GIVEN no custom_fields argument
- WHEN `create_ticket()` is called
- THEN the Ticket row has `customFields = {}`

### Requirement: Unclaim ticket method

`TicketService.unclaim_ticket(ticket_id)` MUST set `claimedBy=null` and `status='open'`. The method SHALL validate that the ticket is currently claimed before proceeding. On success, an audit row with action=unclaim MUST be written.

#### Scenario: Unclaim a claimed ticket

- GIVEN ticket #5 claimed by userA with status `claimed`
- WHEN `unclaim_ticket(5)` is called
- THEN `claimedBy=null`, `status='open'`, and audit row is written

#### Scenario: Unclaim unclaimed ticket rejected

- GIVEN ticket #6 with `claimedBy=null` and status `open`
- WHEN `unclaim_ticket(6)` is called
- THEN `ValueError` is raised (ticket is not claimed)

### Requirement: Close countdown flow

After manual close confirmation, `close_ticket_full()` MUST post ONE message to the channel and edit it counting from 5 to 1 (one edit per second), then delete the channel. The `CHANNEL_DELETE_DELAY` silent sleep MUST be replaced by this countdown for manual close only.

#### Scenario: Countdown replaces silent delay

- GIVEN a manually confirmed ticket close
- WHEN `close_ticket_full()` executes
- THEN ONE message is posted and edited 5→4→3→2→1, then the channel is deleted

#### Scenario: Auto-close uses silent delete

- GIVEN the auto-close task for a 48h stale ticket
- WHEN `close_ticket_full()` is called from auto-close context
- THEN the channel is deleted silently without countdown messages

### Requirement: Channel naming in service

`create_ticket_channel()` and `reopen_ticket()` MUST use `sanitize_channel_name()` from `ticket_helpers.py` to generate channel names in `{category}-{username}-{number}` format.

#### Scenario: create_ticket_channel uses new naming

- GIVEN a ticket creation request with category "Soporte" and user "Daniel"
- WHEN `create_ticket_channel()` is called
- THEN the channel name is generated via `sanitize_channel_name("Soporte", "Daniel", number)`

#### Scenario: reopen_ticket uses new naming

- GIVEN ticket #42 being reopened
- WHEN `reopen_ticket()` creates a new channel
- THEN the channel name uses `sanitize_channel_name()` with the original category and username

### Requirement: Channel creation extracted to service

`create_ticket_channel()` SHALL accept optional `subject: str | None`, `description: str | None`, and `custom_fields: dict | None` parameters and pass them through to `create_ticket()`. This supports both the modal intake flow (with subject/description/custom_fields) and the sub-ticket flow (without them).

#### Scenario: create_ticket_channel called

- GIVEN guild config, author, category_id, and mod_role
- WHEN `TicketService.create_ticket_channel()` is called
- THEN a Discord channel is created with correct overwrites and a Ticket row is inserted

#### Scenario: create_ticket_channel with subject and description

- GIVEN subject and description from modal intake
- WHEN `TicketService.create_ticket_channel(subject=..., description=...)` is called
- THEN the values are passed through to `create_ticket()`

#### Scenario: create_ticket_channel without subject and description

- GIVEN no subject or description (sub-ticket flow)
- WHEN `TicketService.create_ticket_channel()` is called
- THEN `create_ticket()` is called with subject=None and description=None

#### Scenario: create_ticket_channel with custom_fields

- GIVEN custom_fields from modal intake
- WHEN `TicketService.create_ticket_channel(custom_fields=...)` is called
- THEN the dict is passed through to `create_ticket()`

#### Scenario: create_ticket_channel without custom_fields

- GIVEN no custom_fields (sub-ticket flow)
- WHEN `TicketService.create_ticket_channel()` is called
- THEN `create_ticket()` is called with custom_fields=None

### Requirement: Ticket claim

The system MUST allow staff to claim an open ticket. Claim on an already-claimed ticket MUST be rejected — reassignment SHALL use `transfer_ticket`.

(Previously: scenario described rejection but requirement text did not mandate no-overwrite explicitly)

#### Scenario: Staff claims ticket

- GIVEN an open ticket
- WHEN a staff member clicks the claim button
- THEN the ticket status becomes `claimed` and `claimedBy` is set to the staff user ID

#### Scenario: Already claimed rejected

- GIVEN a ticket already claimed by another staff member
- WHEN a staff member clicks claim
- THEN the action is rejected and the existing claim is preserved

#### Scenario: Same-user re-claim rejected

- GIVEN a ticket claimed by userA
- WHEN userA clicks claim again
- THEN the action is rejected

### Requirement: Ticket close

The system MUST close a ticket, generate a transcript, and delete the channel. Manual close MUST use a countdown (5→1 edited message) before channel deletion. Auto-close MUST delete silently. `close_ticket()` MUST accept an optional `close_reason: str | None` parameter and persist it to the Ticket row when provided; when the channel is already missing (zombie repair path), `close_ticket()` MUST skip channel deletion and transcript generation, set `status="closed"`, and persist `close_reason` if supplied. When `close_reason` is `None`, the field MUST NOT be overwritten. The conditional close MUST be idempotent: closing an already-closed ticket MUST raise `ValueError` and perform no mutation.

(Previously: close handled manual countdown and silent auto-close but lacked a conditional `close_reason` transition and a channel-missing zombie path; auto-close silently skipped missing channels without recording a repair)

#### Scenario: Close with transcript

- GIVEN an open ticket with messages
- WHEN the close action is triggered
- THEN a transcript is generated, uploaded to the log channel, the Ticket row status becomes `closed`, and the channel is deleted after countdown

#### Scenario: Close unclaimed ticket

- GIVEN an unclaimed open ticket
- WHEN close is triggered
- THEN the ticket is closed normally and `claimedBy` remains null

#### Scenario: Close records close_reason when provided

- GIVEN an open ticket and `close_reason="channel deleted externally"`
- WHEN `close_ticket(ticket_id, close_reason="channel deleted externally")` is called
- THEN the Ticket row persists `closeReason="channel deleted externally"` and status becomes `closed`

#### Scenario: Close without close_reason leaves field unchanged

- GIVEN an open ticket whose `closeReason` is null
- WHEN `close_ticket(ticket_id)` is called
- THEN status becomes `closed` and `closeReason` remains null

#### Scenario: Close zombie ticket skips channel and transcript

- GIVEN an open ticket whose Discord channel no longer exists
- WHEN `close_ticket(ticket_id, close_reason="zombie:channel_missing")` is called
- THEN `status` becomes `closed`, `closeReason` is persisted, and no channel deletion or transcript generation is attempted

#### Scenario: Re-closing a closed ticket is rejected

- GIVEN a ticket with `status="closed"`
- WHEN `close_ticket(ticket_id)` is called
- THEN `ValueError` is raised and no mutation occurs

### Requirement: Auto-close stale tickets

The system MUST automatically close tickets that have been inactive for 48 hours.

#### Scenario: Stale ticket

- GIVEN a ticket with `lastActivity` older than 48 hours
- WHEN the hourly auto-close task runs
- THEN the ticket is closed silently without warning and the channel is deleted

#### Scenario: Active ticket

- GIVEN a ticket with `lastActivity` within 48 hours
- WHEN the hourly auto-close task runs
- THEN the ticket remains open

### Requirement: create_ticket accepts parentId

`create_ticket` MUST accept an optional `parentId` parameter. When set, the service SHALL validate the parentId (exists, not self-ref, not sub-of-sub, same guild) before insert. When set, the "one open ticket per user per category" check MUST be skipped.

#### Scenario: Create with valid parentId

- GIVEN parent ticket (id=abc, guildId=G) exists and is not itself a child
- WHEN `create_ticket(guildId=G, parentId=abc, ...)` is called
- THEN a new ticket is created with `parentId=abc` and no duplicate-check error

#### Scenario: Create without parentId

- GIVEN no parentId argument
- WHEN `create_ticket(guildId=G, ...)` is called
- THEN a ticket is created with `parentId=null` and the one-open-ticket check runs normally

#### Scenario: Invalid parentId raises

- GIVEN parentId references a non-existent ticket
- WHEN `create_ticket(parentId=xyz, ...)` is called
- THEN a `ValueError` MUST be raised before any DB insert

### Requirement: reopen_ticket method

`TicketService.reopen_ticket(ticket_id, guild)` MUST reject calls when the ticket status is not `closed` by raising `ValueError`. When status is `closed`, the service SHALL: (1) load the closed ticket, (2) create a new Discord channel with the same category/permissions (fallback to default category if original deleted), (3) update `channelId`, set `status=open`, clear `closedAt`, (4) update `_ticket_channel_cache`.

(Previously: no status guard — `reopen_ticket` proceeded on any status, creating duplicate channels for open/claimed tickets)

#### Scenario: Reopen creates new channel

- GIVEN closed ticket #3 (original channel deleted)
- WHEN `reopen_ticket` is called
- THEN a new channel is created and ticket is updated to `open` with new channelId

#### Scenario: Reopen rejected on non-closed ticket

- GIVEN ticket #4 with status `open` or `claimed`
- WHEN `reopen_ticket(4, guild)` is called
- THEN `ValueError` is raised (defense-in-depth; cog layer sends error embed to user)

#### Scenario: Category deleted fallback

- GIVEN closed ticket whose `categoryId` channel no longer exists
- WHEN `reopen_ticket` is called
- THEN the guild's default ticket category is used. If none configured, raise error

#### Scenario: Cache updated

- GIVEN a ticket being reopened
- WHEN the new channel is created
- THEN `_ticket_channel_cache.add(new_channel_id)` is called

### Requirement: transfer_ticket method

`TicketService.transfer_ticket(ticket_id, new_staff_id)` MUST update `claimedBy`, set `status='claimed'`, and insert an audit log row.

(Previously: transfer only set `claimedBy`, did not normalize `status`)

#### Scenario: Transfer updates claimedBy and status

- GIVEN ticket #4 claimed by userA with status `claimed`
- WHEN `transfer_ticket(4, userB)` is called
- THEN `claimedBy` = userB, `status` = `claimed`, and an audit log row exists

#### Scenario: Transfer unclaimed ticket sets status

- GIVEN ticket with `claimedBy=null` and status `open`
- WHEN `transfer_ticket` is called
- THEN `claimedBy` is set and `status` becomes `claimed`

### Requirement: Note CRUD methods

The service MUST provide `create_note(ticket_id, author_id, content)`, `get_notes(ticket_id)`, `delete_note(note_id, author_id)`. Notes are capped at 50 per ticket.

#### Scenario: Create note

- GIVEN a valid ticket
- WHEN `create_note(ticket_id, staff_id, "text")` is called
- THEN a `ticket_note` row is inserted and returned

#### Scenario: Notes cap enforced

- GIVEN ticket has 50 notes
- WHEN `create_note` is called
- THEN `ValueError` is raised with limit message

#### Scenario: Delete own note

- GIVEN note owned by staffA
- WHEN `delete_note(note_id, staffA)` is called
- THEN the row is deleted

#### Scenario: Delete other's note rejected

- GIVEN note owned by staffA
- WHEN `delete_note(note_id, staffB)` is called
- THEN a `ValueError` is raised

### Requirement: Note dedup enforcement

The service MUST reject duplicate notes. Dedup hash = SHA256 of `trim(content).lower().collapse_whitespace()`. Compared against notes from same `authorId` within a 2-second window. On duplicate, `ValueError` SHALL be raised.

#### Scenario: Duplicate note within window

- GIVEN note "Hello World" by authorA created 1s ago
- WHEN `create_note(ticket_id, authorA, "  hello world  ")` is called
- THEN `ValueError` is raised (duplicate)

#### Scenario: Same content outside window

- GIVEN note "Hello" by authorA created 5s ago
- WHEN `create_note(ticket_id, authorA, "hello")` is called
- THEN the note is created

#### Scenario: Different author same content

- GIVEN note "Hello" by authorA created 1s ago
- WHEN `create_note(ticket_id, authorB, "hello")` is called
- THEN the note is created (different author, no dedup)

### Requirement: Audit logging on ticket operations

Every ticket operation (claim, close, reopen, transfer, subticket create, note add, note list, note delete) MUST write a `ticket_audit` row with ticketId, action, actorId, outcome, reason, timestamp. Audit inserts for claim and close operations MUST be best-effort: failure to write the audit row SHALL NOT abort the UI action (channel delete on close, role assignment on claim). Audit failures MUST be logged at WARNING level. Guild-scoped queries.

(Previously: audit failure on claim/close aborted the entire operation, preventing the UI action from completing even though the DB mutation had already succeeded)

#### Scenario: Claim audited on success

- GIVEN a mod claims ticket #5
- WHEN the claim succeeds
- THEN audit row (action=claim, outcome=success) is written

#### Scenario: Invariant violation audited

- GIVEN a non-mod attempts claim
- WHEN access is denied
- THEN audit row (action=claim, outcome=denied, reason) is written

#### Scenario: Claim succeeds despite audit failure

- GIVEN a mod claims ticket #5
- WHEN the claim mutation succeeds but `insert_audit_row` raises an exception
- THEN the claim UI action (role assignment) proceeds normally
- AND a WARNING log is emitted with the audit failure reason

#### Scenario: Close succeeds despite audit failure

- GIVEN a mod closes ticket #7
- WHEN the close mutation succeeds but `insert_audit_row` raises an exception
- THEN the close UI action (channel delete, transcript upload) proceeds normally
- AND a WARNING log is emitted with the audit failure reason

### Requirement: Migration parity for ticket_audit

Migration `012_ticket_audit.sql` MUST be tracked in git. Stale migration `005_ticket_audit.sql` (never applied, superseded by 012) MUST be removed from the repository.

#### Scenario: Migration 012 is tracked

- GIVEN `migrations/012_ticket_audit.sql` exists locally and is already applied on production
- WHEN the hotfix is committed
- THEN `012_ticket_audit.sql` is tracked in git via `git add`

#### Scenario: Stale 005 is removed

- GIVEN `migrations/005_ticket_audit.sql` exists but was never applied (different 005 exists remotely)
- WHEN the hotfix is committed
- THEN `005_ticket_audit.sql` is deleted from the repository

### Requirement: Ticket creation per-user-per-category guard

`create_ticket()` SHALL enforce a one-open-ticket-per-user-per-category limit before inserting a new ticket. An open ticket is one with status `open` or `claimed`. The guard MUST be skipped when `parentId` is not None (subticket carve-out) or when `categoryId` is null (unlimited uncategorized tickets). On limit violation, `ValueError` MUST be raised.

#### Scenario: Second ticket in same category blocked

- GIVEN userA has an open ticket in category "Support" (status=open)
- WHEN `create_ticket(guildId=G, authorId=userA, categoryId="Support")` is called
- THEN `ValueError` is raised (one open ticket per user per category)

#### Scenario: Ticket in different category allowed

- GIVEN userA has an open ticket in category "Support"
- WHEN `create_ticket(guildId=G, authorId=userA, categoryId="Billing")` is called
- THEN a new ticket is created successfully

#### Scenario: Closed ticket frees the slot

- GIVEN userA has a closed ticket in category "Support"
- WHEN `create_ticket(guildId=G, authorId=userA, categoryId="Support")` is called
- THEN a new ticket is created successfully

#### Scenario: Subticket bypasses limit

- GIVEN userA has an open ticket in category "Support"
- WHEN `create_ticket(guildId=G, authorId=userA, categoryId="Support", parentId=abc)` is called
- THEN a subticket is created successfully (limit skipped)

#### Scenario: Null categoryId bypasses limit

- GIVEN userA has an open ticket with categoryId=null
- WHEN `create_ticket(guildId=G, authorId=userA, categoryId=null)` is called
- THEN a new ticket is created successfully (limit skipped)

### Requirement: Edit ticket category

`TicketService.edit_ticket_category(ticket_id, new_category_id, *, channel, actor_id, is_mod=False)` MUST update `categoryId` in the database and rename the ticket channel via `sanitize_channel_name()`. The method is the security boundary: it MUST call `check_can_edit_category(actor_id, ticket, is_mod=is_mod)` BEFORE any DB mutation (the view re-validates UX but the service is authoritative; remote callers without the view must still be gated). The method MUST reject edit on a closed ticket (`edit_category` is valid only for `open`/`claimed`; closed tickets must be reopened first) by raising `ValueError`. The method MUST call `check_one_ticket_per_user_per_category(author_id, new_category_id, None, count_fn)` for the ticket's author against the NEW category BEFORE the DB update, counting the author's other `open`/`claimed` tickets in that category and excluding the ticket being edited from the count by passing `exclude_ticket_id=ticket_id` to `count_user_open_tickets_in_category(guild_id, author_id, new_category_id, exclude_ticket_id=ticket_id)` (`new_category_id` is non-null in this path); on violation it MUST raise `ValueError`. If the channel rename raises `discord.HTTPException` (rate limit), the system SHALL log a warning and proceed — the DB update MUST still succeed. The method MUST write an `audit_log` row on success.

#### Scenario: Edit category updates DB and renames channel

- GIVEN ticket #5 with categoryId="Support" and channel name "support-daniel-5"
- WHEN `edit_ticket_category(5, "Billing", channel=..., actor_id=modUser)` is called
- THEN categoryId is "Billing" in DB and channel is renamed to "billing-daniel-5"

#### Scenario: Channel rename failure does not block DB update

- GIVEN ticket #5 and Discord rate limit active
- WHEN `edit_ticket_category(5, "Billing", channel=..., actor_id=modUser)` is called and channel rename raises `HTTPException`
- THEN categoryId is updated to "Billing" in DB and a warning is logged

#### Scenario: Audit row written on success

- GIVEN a valid category edit
- WHEN `edit_ticket_category` succeeds
- THEN an audit row (action=edit_category, outcome=success) is written

#### Scenario: Service enforces mod permission

- GIVEN a ticket and an actor that lacks mod/admin
- WHEN `edit_ticket_category(5, "Billing", channel=..., actor_id=userA, is_mod=False)` is called
- THEN the operation is rejected before any DB mutation and an audit row (outcome=denied) is written

#### Scenario: Edit on closed ticket rejected

- GIVEN ticket #5 with status="closed"
- WHEN `edit_ticket_category(5, "Billing", channel=..., actor_id=modUser)` is called
- THEN `ValueError` is raised and no DB mutation happens

#### Scenario: Edit into category where author has open ticket rejected

- GIVEN ticket #7 (author=userA, category="Support") and userA already has another open ticket in "Billing"
- WHEN `edit_ticket_category(7, "Billing", channel=..., actor_id=modUser)` is called
- THEN `ValueError` is raised (one open ticket per user per category) and no DB mutation happens

#### Scenario: Edit into empty category allowed

- GIVEN ticket #7 (author=userA) and userA has no open/claimed tickets in "Billing"
- WHEN `edit_ticket_category(7, "Billing", channel=..., actor_id=modUser)` is called
- THEN categoryId is updated to "Billing" and the channel is renamed

#### Scenario: Edit excludes the edited ticket from the count

- GIVEN ticket #7 (author=userA, category="Billing") is the author's only open ticket in "Billing" and is being edited to a new category
- WHEN `edit_ticket_category(7, "Support", channel=..., actor_id=modUser)` is called
- THEN the count for "Billing" excludes ticket #7 and no false violation is raised

#### Scenario: Same-category no-op edit does not self-block

- GIVEN ticket #7 (author=userA, category="Support") is the author's only open ticket in "Support"
- WHEN `edit_ticket_category(7, "Support", channel=..., actor_id=modUser)` is called (no-op same category)
- THEN `count_user_open_tickets_in_category(G, userA, "Support", exclude_ticket_id=7)` is called, ticket #7 is excluded, the count is 0, and no `ValueError` is raised; `categoryId` remains "Support"

<!-- BEGIN DELTA: product-artifact-audit (ticket-service) -->
## ADDED Requirements

### Requirement: Shared idempotent evidence repair path

The ticket service MUST expose one repair path used by channel-delete events, periodic sweeps, and manual fallback. The path MUST use a conditional lifecycle transition and MUST return a reviewable result. Automatic event and sweep mutation requires BOTH a resolved live schema/deployment preflight and fresh, per-ticket Discord corroboration that the channel is absent. Missing, ambiguous, stale, or transient evidence MUST produce quarantine/report/no-op without mutation.

#### Scenario: Corroborated automatic repair

- GIVEN preflight is resolved and fresh evidence proves an active ticket's channel is absent
- WHEN a channel-delete event invokes repair
- THEN exactly one conditional close occurs and the result identifies the evidence

#### Scenario: Ambiguous evidence quarantines

- GIVEN channel existence is unknown, stale, or contradictory
- WHEN any entry point evaluates the ticket
- THEN it returns a reviewable quarantine/report result and performs no ticket mutation

#### Scenario: Duplicate event is idempotent

- GIVEN two delete events target the same active ticket
- WHEN both use the shared repair path
- THEN one closes the ticket and the other returns a deterministic no-op without a second transition


<!-- BEGIN DELTA: refactor-ticket-domain (ticket-service) -->
## ADDED Requirements

### Requirement: Guild-scoped ticket facade

The `TicketService` compatibility facade MUST require guild ownership for S2 ticket reads, mutations, and repair entry points. A request targeting another guild MUST NOT disclose or mutate that guild's ticket. Existing public service names and persistent view custom IDs MUST remain compatible.

#### Scenario: Numeric reference is guild-scoped

- GIVEN guild A and guild B may use the same ticket number
- WHEN guild A resolves a numeric repair reference
- THEN only guild A's ticket is eligible

#### Scenario: Channel deletion cannot cross guilds

- GIVEN a deleted channel event belongs to guild A
- WHEN the service looks up an active ticket
- THEN only the guild A and channel A pair is considered

#### Scenario: Public facade remains compatible

- GIVEN existing cogs, listeners, and views call `TicketService`
- WHEN the S2 repair seam is enabled
- THEN those callers continue using the facade without a parallel repair API

### Requirement: Single repair eligibility seam

`TicketService` MUST route channel-delete handling, integrity sweeps, and manual/reference repair through one `evaluate_repair_eligibility` decision and one conditional guild-scoped transition. Adapters MUST NOT duplicate gate/evidence decisions or mutate ticket rows directly. Denied decisions MUST return reviewable no-op results.

#### Scenario: Unresolved preflight fails closed

- GIVEN live preflight is unresolved and evidence reports a missing channel
- WHEN any repair entry point evaluates the ticket
- THEN it returns `skipped` with `gate_unresolved` and performs no transition

#### Scenario: Unknown evidence is quarantined

- GIVEN preflight is resolved but channel evidence is unknown or stale
- WHEN a repair entry point evaluates the ticket
- THEN it returns `skipped` with `evidence_unresolved` and performs no mutation

#### Scenario: Corroborated repair has one winner

- GIVEN resolved preflight and corroborated evidence for an active ticket
- WHEN event, sweep, or manual paths race
- THEN exactly one conditional close succeeds and later attempts return `already_closed`

## MODIFIED Requirements

### Requirement: Shared idempotent evidence repair path

The ticket service MUST expose one repair path used by channel-delete events, periodic sweeps, and manual fallback. The path MUST use `evaluate_repair_eligibility`, a guild-scoped conditional lifecycle transition, and a reviewable result. Automatic event and sweep mutation requires BOTH resolved live schema/deployment preflight and fresh, per-ticket Discord corroboration. Missing, ambiguous, stale, or transient evidence MUST produce quarantine/report/no-op without mutation.
(Previously: the shared path required a conditional close and evidence gate but did not explicitly define the single eligibility seam and guild-scoped facade contract.)

#### Scenario: Corroborated automatic repair

- GIVEN preflight is resolved and fresh evidence proves an active ticket's channel is absent
- WHEN a channel-delete event invokes repair
- THEN exactly one guild-scoped conditional close occurs and the result identifies the evidence

#### Scenario: Ambiguous evidence quarantines

- GIVEN channel existence is unknown, stale, or contradictory
- WHEN any entry point evaluates the ticket
- THEN it returns a reviewable quarantine/report result and performs no ticket mutation

#### Scenario: Duplicate event is idempotent

- GIVEN two delete events target the same active ticket
- WHEN both use the shared repair path
- THEN one closes the ticket and the other returns a deterministic no-op without a second transition

<!-- END DELTA: refactor-ticket-domain (ticket-service) -->

### Requirement: Bounded sweeps and explicit manual authority

Integrity sweeps MUST process finite batches, honor backoff on transient Discord failures, and repair only corroborated safe cases. A failed or retried candidate MUST be reported for review without duplicate state transitions. Manual fallback MUST use the same path, require fresh corroboration, and record the initiating authority. Guild administrators MUST be restricted to their guild; bot operators MAY diagnose globally but MUST have an explicit, auditable mutation grant.

#### Scenario: Sweep defers a transient failure

- GIVEN a sweep candidate returns a Discord timeout or rate limit
- WHEN the candidate is evaluated
- THEN backoff and a reviewable skipped result are recorded, with no mutation

#### Scenario: Guild isolation denies cross-guild repair

- GIVEN a guild admin for guild A requests repair for a ticket in guild B
- WHEN manual fallback authorizes the request
- THEN the request is denied, an audit reason is recorded, and ticket B is unchanged

#### Scenario: Operator mutation is explicit

- GIVEN a bot operator diagnoses tickets globally without mutation authority
- WHEN the operator requests repair
- THEN diagnosis may be returned, but mutation is denied until an explicit authority is present and auditable

### Requirement: Canonical recovery lifecycle

`ticket-integrity-recovery` MUST remain the canonical lifecycle. Useful reconciliation contracts, including `CloseResult`, close-reason mapping, close ordering, localization, and evidence semantics, MUST be ported into this lifecycle before the conflicting active change is superseded or archived. This change MUST NOT introduce a parallel repair capability. Disabling the repair gate MUST preserve existing close behavior and deletion logging.

#### Scenario: Rollback is a no-op

- GIVEN repair activation is disabled or preflight is unresolved
- WHEN a candidate is detected
- THEN reports are retained, the ticket is untouched, and deletion-only logging continues

<!-- END DELTA: product-artifact-audit (ticket-service) -->

<!-- BEGIN DELTA: ticket-integrity-recovery (ticket-service) -->
## ADDED Requirements

### Requirement: Authoritative channel-delete repair

On the authoritative `on_guild_channel_delete` event, the system MUST perform a conditional active-ticket lookup keyed by the deleted channel's `guild_id` and `channel_id`. An active ticket is one with `status` `open` or `claimed`. When an active ticket maps to the deleted channel, the system MUST repair it via `close_ticket` with `close_reason="zombie:channel_deleted"`, producing a `RepairResult`. When no active ticket maps to the deleted channel, the system MUST do nothing (no provenance). Repair via this path is permitted only after the G.2 deployment/migration preflight gate (see database-layer delta) returns `resolved`. Until then, the event handler MUST log the detection and skip repair.

#### Scenario: Authoritative event repairs active zombie

- GIVEN the G.2 gate is `resolved` and an open ticket maps to channel `c1` in guild `g1`
- WHEN `on_guild_channel_delete` fires for channel `c1`
- THEN the ticket is conditionally closed with `closeReason="zombie:channel_deleted"` and a `RepairResult(action="close", outcome="repaired")` is produced

#### Scenario: No active ticket means no-op

- GIVEN the G.2 gate is `resolved` and no open/claimed ticket maps to channel `c2`
- WHEN `on_guild_channel_delete` fires for channel `c2`
- THEN no `close_ticket` call is made and no ticket mutation occurs

#### Scenario: Gate unresolved blocks automatic repair

- GIVEN the G.2 gate is `gate_unresolved` and an open ticket maps to deleted channel `c1`
- WHEN `on_guild_channel_delete` fires for channel `c1`
- THEN the handler logs detection of the zombie but does not call `close_ticket`

#### Scenario: Duplicate close race resolves to no-op

- GIVEN the G.2 gate is `resolved` and two `on_guild_channel_delete` events fire for the same channel concurrently
- WHEN both attempt to close the same active ticket
- THEN exactly one `RepairResult(action="close", outcome="repaired")` is produced and the second attempt produces `RepairResult(action="no_op", outcome="already_closed")`

### Requirement: Evidence-gated reconciliation sweep

The system MUST support startup and hourly reconciliation sweeps that detect and report zombie tickets. Sweeps MUST be evidence-gated: they MUST collect `IntegrityEvidence` per candidate and act only on `corroborated=True` evidence. Repair mutation within a sweep is permitted ONLY when the G.2 gate is `resolved`. When the gate is unresolved, the sweep MUST produce a dry-run report only — no mutations. Sweeps MUST be bounded (a maximum batch size per run) and rate-limit safe: cooperation with Discord API limits, backoff on transient errors, and no unbounded iteration over all guild tickets. A sweep that cannot complete verification for a candidate MUST mark that candidate `outcome="skipped"` rather than mutating.

#### Scenario: Dry-run report when gate unresolved

- GIVEN the G.2 gate is `gate_unresolved` and guild `g1` has two open tickets whose channels are missing
- WHEN the hourly sweep runs
- THEN a dry-run report lists both candidates with `corroborated=True` and no ticket mutation occurs

#### Scenario: Sweep repairs corroborated zombies when gate resolved

- GIVEN the G.2 gate is `resolved` and guild `g1` has one corroborated zombie ticket
- WHEN the hourly sweep runs
- THEN the sweep closes that ticket with `closeReason="zombie:sweep"` and emits `RepairResult(action="close", outcome="repaired")`

#### Scenario: Bounded batch size enforced

- GIVEN guild `g1` has 250 zombie candidates and the batch size is 50
- WHEN the sweep runs
- THEN at most 50 candidates are processed this run and the remainder are left for the next run

#### Scenario: Rate-limit safe backoff

- GIVEN the sweep is running and Discord returns a 429 rate-limit error
- WHEN the error is caught
- THEN the sweep backs off, marks the current candidate `outcome="skipped"`, and proceeds without exceeding Discord rate limits

#### Scenario: Missing evidence means no mutation

- GIVEN a candidate ticket whose channel-existence check could not complete (transient error)
- WHEN the sweep evaluates it
- THEN the candidate is marked `outcome="skipped"` and no mutation occurs

### Requirement: Manual repair fallback

The system MUST provide a manual repair entry point (command/service call) allowing a moderator to trigger repair for a specific ticket or guild without depending on the automatic gate. Manual repair MUST still collect `IntegrityEvidence` and act only on `corroborated=True`, preserving false-positive safety. Manual repair MUST write an audit row with `actorId` set to the triggering mod and `action="manual_repair"`. Manual repair is NOT subject to the G.2 automatic-activation gate, but MUST respect idempotency and bounds.

#### Scenario: Mod repairs a specific zombie manually

- GIVEN mod `userM` triggers manual repair for ticket `t9` which is a corroborated zombie
- WHEN manual repair runs
- THEN the ticket is closed with `closeReason="zombie:manual_repair"`, a `RepairResult(action="close")` is produced, and an audit row records `actorId=userM`

#### Scenario: Manual repair on non-zombie is no-op

- GIVEN mod `userM` triggers manual repair for ticket `t10` whose channel still exists
- WHEN manual repair runs
- THEN `RepairResult(action="no_op", outcome="skipped")` is produced and no mutation occurs

#### Scenario: Manual repair is idempotent

- GIVEN ticket `t9` was already repaired in the same window
- WHEN manual repair is triggered again for `t9`
- THEN `RepairResult(action="no_op", outcome="already_closed")` is produced and no mutation occurs

### Requirement: Repair idempotency, bounds, and auditability

Every repair — automatic, sweep, or manual — MUST be idempotent: applying the same repair twice MUST NOT produce two close mutations. Repairs MUST be bounded: each run processes a finite batch and backs off on rate limits. Every repair attempt MUST emit a `RepairResult` and a `ticket_audit` row with `action`, `actorId` (system for automatic/sweep, mod for manual), and `outcome`. Audit rows for repair are best-effort: a failure to write the audit row MUST NOT block the documented repair mutation but MUST be logged at WARNING level. Re-running repair after `already_closed` MUST be a deterministic no-op.

#### Scenario: Idempotent re-run after repair

- GIVEN ticket `t1` was repaired and closed
- WHEN repair is triggered again for `t1`
- THEN the second run produces `RepairResult(action="no_op", outcome="already_closed")` and writes no second close mutation

#### Scenario: Audit row written on automatic repair

- GIVEN an automatic or sweep repair closes ticket `t1`
- WHEN the repair completes
- THEN a `ticket_audit` row with `action="repair"`, `actorId="system"`, and `outcome="repaired"` is written

#### Scenario: Audit row written on manual repair

- GIVEN mod `userM` manually repairs ticket `t1`
- WHEN the manual repair completes
- THEN a `ticket_audit` row with `action="manual_repair"`, `actorId="userM"`, and `outcome="repaired"` is written

#### Scenario: Audit failure does not block repair

- GIVEN repair closes ticket `t1` but the audit insert raises
- WHEN the audit insert is caught
- THEN the close mutation persists and a WARNING log is emitted

#### Scenario: Bounded run processes finite batch

- GIVEN a sweep with batch size 50 and 120 candidates
- WHEN the run completes
- THEN exactly 50 or fewer candidates are mutated and the run terminates without unbounded iteration

### Requirement: False-positive safe channel verification

Before any repair mutation, the system MUST verify corroborating evidence that the channel truly does not exist. The channel-existence check MUST tolerate transient Discord errors (network, 5xx, 429) by treating them as `channel_exists=unknown` and skipping that candidate rather than mutating. The system MUST NOT close a ticket based solely on a single transient Discord error. Corroboration requires a DB-backed active-ticket mapping AND a channel-existence check; absence of either means no mutation.

#### Scenario: Transient Discord error skips candidate

- GIVEN an active ticket `t2` and the channel-existence check raises a transient `discord.HTTPException`
- WHEN repair evaluates `t2`
- THEN `RepairResult(action="no_op", outcome="skipped")` is produced and no mutation occurs

#### Scenario: Rate-limit error treated as skip

- GIVEN the channel-existence check returns a 429 response
- WHEN repair evaluates the candidate
- THEN the candidate is skipped and no mutation occurs

#### Scenario: DB mapping but no channel check means no mutation

- GIVEN an active ticket `t3` whose channel-existence check never ran
- WHEN repair evaluates `t3`
- THEN no close mutation occurs and `Outcome="skipped"` is recorded

### Requirement: Rollback and no-op behavior

When the repair slice is disabled (gate unresolved or feature flag off), the system MUST revert to prior close and channel-delete behavior and MUST NOT rely on migration 015 until parity returns. Existing reports MUST be retained, tickets MUST be left untouched, and the prior `on_guild_channel_delete` audit-logging behavior (deletion only logged) MUST continue. A no-op repair run MUST return without side effects and without claiming completion.

#### Scenario: Disabled slice leaves tickets untouched

- GIVEN the repair gate is disabled and guild `g1` has corroborated zombies
- WHEN the sweep would run
- THEN no ticket mutation occurs and prior close/channel-delete behavior is preserved

#### Scenario: Audit logging of channel delete continues

- GIVEN the repair slice is disabled and a channel is deleted
- WHEN `on_guild_channel_delete` fires
- THEN the prior audit-logging behavior (deletion logged) continues unchanged

#### Scenario: No-op run returns without side effects

- GIVEN a sweep finds no corroborated zombies
- WHEN the run completes
- THEN no audit rows for repair are written and no `RepairResult(action="close")` is emitted

<!-- END DELTA: ticket-integrity-recovery (ticket-service) -->

<!-- BEGIN DELTA: ticket-physical-split S3 -->

### Requirement: Facade-preserving service composition

`TicketService` MUST remain the stable public facade while composing `TicketQueryService`, `TicketLifecycleService`, and `TicketRepairService`. Query/cache reads, lifecycle mutations, and repair/channel orchestration MUST each have one owner. The facade MUST delegate each operation once and MUST NOT duplicate cache, audit, or invariant mutation.

#### Scenario: Existing callers remain compatible

- GIVEN cogs, listeners, and views import `TicketService`
- WHEN the physical split is enabled
- THEN existing public method calls and return contracts continue to work through the facade

#### Scenario: Query ownership is singular

- GIVEN a caller requests a guild-scoped ticket or cache lookup
- WHEN the request passes through `TicketService`
- THEN `TicketQueryService` performs the read and exactly one owner updates the cache

#### Scenario: Lifecycle ownership is singular

- GIVEN a caller claims, closes, reopens, or transfers a ticket
- WHEN the facade delegates the operation
- THEN `TicketLifecycleService` owns the transition and no facade or sibling repeats it

### Requirement: Single repair eligibility seam after extraction

Channel-delete events, bounded sweeps, and manual or reference repairs MUST delegate to `TicketRepairService`, which MUST use one `evaluate_repair_eligibility` decision and one guild-scoped conditional transition. Adapters MUST NOT decide evidence eligibility or mutate ticket rows directly.

#### Scenario: All repair entry points share one decision

- GIVEN an event, sweep, and manual request target the same ticket
- WHEN each request is evaluated
- THEN all use the same eligibility seam and produce reviewable results

#### Scenario: Repair race remains idempotent

- GIVEN two corroborated repair requests race for one active ticket
- WHEN both reach persistence
- THEN one closes the ticket and the other returns a deterministic no-op without a second transition

#### Scenario: Unresolved evidence remains safe

- GIVEN preflight or channel evidence is unresolved
- WHEN any extracted repair path evaluates the ticket
- THEN it reports a skipped/quarantined result and performs no mutation

<!-- END DELTA: ticket-physical-split S3 -->


<!-- BEGIN DELTA: staging-live-parity S4 -->

### Requirement: Optional bounded S4 error-path polish

If the optional S4 polish slice is included, the ticket repair and panel test suites MUST raise line coverage for `ticket_repair_service.py` and `ticket_panel.py` from the 73% baseline to at least 80% per file. Tests MUST target only the identified error, fallback, no-op, and Discord-exception branches, preserve existing user-visible behavior, and MUST NOT use fake coverage as proof of live Supabase parity.

#### Scenario: Target coverage reaches the bounded goal

- GIVEN both changed files begin at the 73% baseline
- WHEN the focused S4 polish suite runs
- THEN each file reports at least 80% line coverage

#### Scenario: Error paths remain reviewable

- GIVEN a repair or panel operation encounters a configured failure, missing resource, no-op, or Discord exception
- WHEN the focused tests exercise that branch
- THEN the documented error handling is asserted and no uncaught traceback reaches the user

#### Scenario: Polish stays out of scope

- GIVEN unrelated Sentinel or pre-existing coverage debt exists
- WHEN S4 polish coverage is measured
- THEN it is excluded from the target and no unrelated behavior is changed

<!-- END DELTA: staging-live-parity S4 -->
