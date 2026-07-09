# Ticket Service Specification

## Purpose

Define ticket lifecycle management: creation, claim, close, and automatic closure after inactivity.

## Requirements

### Requirement: Ticket creation

The system MUST create a new ticket channel with a sequential ticket number per guild. `create_ticket()` SHALL accept optional `subject: str | None` and `description: str | None` parameters and persist them to the database.

#### Scenario: Successful creation

- GIVEN a guild with ticket category configured
- WHEN a user opens a ticket
- THEN a channel is created under the ticket category and a Ticket row is inserted with status `open`

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

### Requirement: Channel creation extracted to service

`create_ticket_channel()` SHALL accept optional `subject: str | None` and `description: str | None` parameters and pass them through to `create_ticket()`. This supports both the modal intake flow (with subject/description) and the sub-ticket flow (without them).

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

The system MUST close a ticket, generate a transcript, and delete the channel.

#### Scenario: Close with transcript

- GIVEN an open ticket with messages
- WHEN the close action is triggered
- THEN a transcript is generated, uploaded to the log channel, the Ticket row status becomes `closed`, and the channel is deleted

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
