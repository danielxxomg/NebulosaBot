# Ticket Subsidiados Specification

## Purpose

Sub-ticket derivation, reopen, transfer, and staff notes.

## Requirements

### Requirement: Sub-ticket creation

The system MUST allow staff (`@is_mod()`) to create a child ticket via `/subticket create`. Child SHALL have own channel, `parentId` set, own `ticketNumber`, independent lifecycle.

#### Scenario: Successful sub-ticket creation

- GIVEN open ticket #5 (id=abc)
- WHEN staff invokes `/subticket create` targeting #5
- THEN ticket #6 is created with `parentId=abc`, new channel, status `open`

#### Scenario: Sub-ticket inherits guild

- GIVEN a parent ticket in guild G
- WHEN a sub-ticket is created
- THEN the sub-ticket's `guildId` MUST equal the parent's `guildId`

### Requirement: Parent ID validation

The system MUST reject invalid `parentId` at the service layer (no DB FK in Supabase Transaction Mode).

#### Scenario: Self-reference rejected

- GIVEN ticket #5 (id=abc)
- WHEN `create_ticket(parentId=abc)` targets same ticket
- THEN validation error MUST be raised

#### Scenario: Sub-of-sub rejected

- GIVEN ticket #6 already has `parentId` (is a child)
- WHEN `create_ticket` targets #6 as parent
- THEN validation error MUST be raised

#### Scenario: Cross-guild rejected

- GIVEN parent in guild A
- WHEN `create_ticket(parentId=abc, guildId=B)`
- THEN validation error MUST be raised

#### Scenario: Non-existent parent rejected

- GIVEN no ticket with id=xyz
- WHEN `create_ticket(parentId=xyz)`
- THEN validation error MUST be raised

### Requirement: One-open-ticket carve-out

The system MUST exempt sub-tickets from the "one open ticket per user per category" constraint when `parentId` is set.

#### Scenario: Sub-ticket bypasses duplicate check

- GIVEN user U has an open ticket in category C
- WHEN staff creates a sub-ticket (parentId set) for U in C
- THEN sub-ticket is created without error

### Requirement: Ticket reopen

The system MUST allow staff to reopen a closed ticket via `/reopen`. A NEW channel is created, `channelId` updated, `status` → `open`, `closedAt` cleared.

#### Scenario: Successful reopen

- GIVEN closed ticket #3
- WHEN `/reopen` is invoked
- THEN new channel created, status → `open`, `channelId` updated, `closedAt` = null

#### Scenario: Category deleted fallback

- GIVEN closed ticket whose original category was deleted
- WHEN `/reopen` is invoked
- THEN guild's default category is used; if none, raise error

#### Scenario: Cache updated on reopen

- GIVEN ticket being reopened
- WHEN new channel is created
- THEN `_ticket_channel_cache` includes the new channel ID

### Requirement: Ticket transfer

The system MUST allow `/transfer @staff`. `claimedBy` mutated, audit log row inserted.

#### Scenario: Transfer claimed ticket

- GIVEN ticket #4 claimed by userA
- WHEN `/transfer @userB`
- THEN `claimedBy` = userB, audit log row inserted

#### Scenario: Transfer unclaimed ticket

- GIVEN ticket with `claimedBy=null`
- WHEN `/transfer @userB`
- THEN `claimedBy` = userB (implicit claim)

### Requirement: Staff notes

The system MUST provide `/note add`, `/note list`, `/note delete` (staff-only via `@is_mod()`). Notes in `ticket_note` table. NOT visible to opener. Cap: 50/ticket.

#### Scenario: Add note

- GIVEN staff on open ticket
- WHEN `/note add "Customer escalated"`
- THEN `ticket_note` row inserted with authorId, content, createdAt

#### Scenario: List notes

- GIVEN ticket with 3 notes
- WHEN `/note list` by staff
- THEN all 3 returned with author and timestamp

#### Scenario: Delete own note

- GIVEN note owned by staffA
- WHEN staffA `/note delete {noteId}`
- THEN note row deleted

#### Scenario: Non-staff rejected

- GIVEN non-mod user
- WHEN `/note add`
- THEN rejected with permission error

#### Scenario: Notes cap enforced

- GIVEN ticket with 50 notes
- WHEN `/note add`
- THEN rejected with limit error
