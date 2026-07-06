# Delta for Dashboard Ticket View

## MODIFIED Requirements

### Requirement: Reopen action

The dashboard Reopen button MUST show a "Reopen in Discord" guidance modal with the ticket number (copyable) and the exact command to run (`/reopen ticket:#<number>`). The dashboard MUST NOT perform a DB-only status flip (which creates zombie tickets with no Discord channel). The bot's `/reopen` command accepts a ticket-id argument so it can be invoked from any channel (the original ticket channel is deleted on close).

(Previously: reopen was a DB-only status flip creating zombie tickets with no Discord channel. A `discord://channels/...` deeplink was considered but rejected — deleted ticket channels 404, and slash-command deeplinks cannot invoke commands.)

#### Scenario: Reopen guidance shown

- GIVEN admin clicks Reopen on closed ticket #3
- WHEN the action triggers
- THEN a guidance modal is shown with ticket number `#0003` (copyable) and the command `/reopen ticket:#0003`

#### Scenario: No ticketCategoryId error

- GIVEN guild has no `ticketCategoryId` configured
- WHEN admin clicks Reopen
- THEN an error message is shown indicating category not configured (the bot `/reopen` would fail without it)

### Requirement: Transfer action

Clicking Transfer MUST prompt for a staff member selection, then call `transferTicket` server action. On success, both `claimedBy` AND `status` update in the list.

(Previously: transfer set `claimedBy` only, leaving `status` inconsistent)

#### Scenario: Transfer via dashboard

- GIVEN admin selects a new staff member and confirms transfer
- WHEN the server action completes
- THEN `claimedBy` updates to the new staff member AND `status` becomes `claimed`

## ADDED Requirements

### Requirement: Notes cap enforcement

The notes panel MUST enforce a maximum of 50 notes per ticket. When the cap is reached, the add-note form SHALL be disabled with a message.

#### Scenario: Note added under cap

- GIVEN ticket #5 has 30 notes
- WHEN admin submits a note
- THEN the note is persisted

#### Scenario: Note rejected at cap

- GIVEN ticket #5 has 50 notes
- WHEN admin submits a note
- THEN the submission is rejected with a cap-reached message

### Requirement: Notes delete author-only

The delete action on a note MUST verify the session user matches the note's `authorId`. Non-owners SHALL be rejected.

#### Scenario: Author deletes own note

- GIVEN note created by userA
- WHEN userA (same session) clicks delete
- THEN the note is deleted

#### Scenario: Non-author delete rejected

- GIVEN note created by userA
- WHEN userB (different session) clicks delete
- THEN the action is rejected

### Requirement: Audit view

The dashboard MUST display `ticket_audit` rows for the viewed guild. Columns: action, actorId, outcome, reason, createdAt. Guild-scoped, paginated.

#### Scenario: Audit rows displayed

- GIVEN guild A has 200 audit entries
- WHEN admin visits the audit tab
- THEN paginated audit rows for guild A are shown

#### Scenario: No cross-guild leak

- GIVEN audit rows exist for guilds A and B
- WHEN admin of guild A views audit
- THEN only guild A rows appear
