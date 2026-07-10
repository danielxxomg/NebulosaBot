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

The system MUST close a ticket, generate a transcript, and delete the channel. Manual close MUST use a countdown (5→1 edited message) before channel deletion. Auto-close MUST delete silently.

#### Scenario: Close with transcript

- GIVEN an open ticket with messages
- WHEN the close action is triggered
- THEN a transcript is generated, uploaded to the log channel, the Ticket row status becomes `closed`, and the channel is deleted after countdown

#### Scenario: Close unclaimed ticket

- GIVEN an unclaimed open ticket
- WHEN close is triggered
- THEN the ticket is closed normally and `claimedBy` remains null

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
