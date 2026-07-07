# Dashboard Ticket View Specification

## Purpose

Read-only ticket overview page for the web dashboard. Admins monitor per-guild ticket status and browse a ticket list without switching to Discord. Auth-gated by `verifyGuildAdmin`, hard-limited to 50 rows.

## Requirements

### Requirement: Per-guild ticket stats

The page MUST display counts of open, claimed, and closed tickets for the viewed guild.

#### Scenario: Stats with mixed statuses

- GIVEN a guild has 5 open, 3 claimed, and 12 closed tickets
- WHEN an admin visits `/guilds/{id}/tickets`
- THEN the page shows open=5, claimed=3, closed=12

#### Scenario: Stats with no tickets

- GIVEN a guild has zero tickets
- WHEN an admin visits the page
- THEN all stat counts show 0

### Requirement: Ticket list rendering

The page MUST render a list showing each ticket's number, status badge, author id, created_at, and claimed_by, capped at 50 rows.

#### Scenario: Tickets exist

- GIVEN a guild has 10 tickets
- WHEN the page loads
- THEN a table shows 10 rows with ticketNumber, status, authorId, createdAt, claimedBy columns

#### Scenario: Null claimed_by

- GIVEN a ticket with `claimedBy` set to null
- WHEN the row renders
- THEN claimedBy displays a dash or empty indicator

### Requirement: Status badge mapping

Each ticket status MUST render as a color-coded Badge: open → green, claimed → yellow, closed → gray.

#### Scenario: All statuses

- GIVEN tickets with statuses open, claimed, and closed
- WHEN the list renders
- THEN open shows a green Badge, claimed shows yellow, closed shows gray

#### Scenario: Unknown status fallback

- GIVEN a ticket with an unrecognized status value
- WHEN the Badge renders
- THEN it falls back to the default Badge variant (no crash)

### Requirement: Auth gating

`getTicketsForGuild` MUST verify the caller is a guild admin before returning data. Unauthenticated or non-admin callers receive an auth error with no data leaked.

#### Scenario: Non-admin rejected

- GIVEN a user who is not an admin of guild X
- WHEN they call `getTicketsForGuild("X")`
- THEN the function returns an auth error and no ticket data

#### Scenario: Unauthenticated rejected

- GIVEN no authenticated session
- WHEN `getTicketsForGuild` is called
- THEN the function returns an auth error

### Requirement: Guild isolation

`getTicketsForGuild` MUST filter by `guildId`. Tickets from other guilds MUST NOT appear in results.

#### Scenario: Only matching guild returned

- GIVEN guild A has 5 tickets and guild B has 3 tickets
- WHEN an admin of guild A calls `getTicketsForGuild("A")`
- THEN exactly 5 tickets are returned, all with `guildId` = "A"

#### Scenario: No cross-guild leak

- GIVEN guild B has tickets
- WHEN a guild A admin queries
- THEN zero guild B tickets appear in the result set

### Requirement: Empty state

The page MUST handle zero tickets gracefully with a helpful message. No crash or blank screen.

#### Scenario: Zero tickets

- GIVEN a guild with no tickets
- WHEN the page loads
- THEN an empty state message is shown (e.g., "No tickets yet")

### Requirement: Hard limit 50

`getTicketsForGuild` MUST return at most 50 rows. Pagination is out of scope for v1.

#### Scenario: Over 50 tickets

- GIVEN a guild has 80 tickets
- WHEN `getTicketsForGuild` is called
- THEN exactly 50 tickets are returned

#### Scenario: Under 50 tickets

- GIVEN a guild has 12 tickets
- WHEN `getTicketsForGuild` is called
- THEN exactly 12 tickets are returned

### Requirement: Sidebar link

The authenticated sidebar MUST include a "Tickets" link navigating to `/guilds/{id}/tickets` with active state when on that route.

#### Scenario: Link present

- GIVEN an authenticated user viewing a guild's sidebar
- WHEN the sidebar renders
- THEN a "Tickets" link to `/guilds/{id}/tickets` is visible

#### Scenario: Active state

- GIVEN the user is on `/guilds/{id}/tickets`
- WHEN the sidebar renders
- THEN the Tickets link shows its active/highlighted style

### Requirement: Sub-ticket tree rendering

The ticket list MUST render parent→child hierarchy. Child tickets SHALL appear indented under their parent. Parent tickets with no children render normally.

#### Scenario: Parent with children

- GIVEN ticket #5 (parent) has two children (#6, #7)
- WHEN the ticket list renders
- THEN ticket #5 appears as a top-level row and #6, #7 appear indented below it

#### Scenario: Orphan child (parent deleted)

- GIVEN a ticket with `parentId` referencing a non-existent ticket
- WHEN the list renders
- THEN the ticket renders as a top-level row (graceful degradation, no crash)

#### Scenario: No sub-tickets

- GIVEN a guild with only flat tickets (no parentId set)
- WHEN the list renders
- THEN all tickets render as top-level rows (same as current behavior)

### Requirement: Action buttons (client components)

The ticket row MUST display action buttons: Reopen (if closed), Transfer (if open/claimed), Notes (always). Buttons SHALL be React client components (`'use client'`) to handle interactivity. Auth-gated: buttons only render for admins via `verifyGuildAdmin`.

#### Scenario: Closed ticket shows Reopen button

- GIVEN a closed ticket row
- WHEN the row renders for an admin
- THEN a "Reopen" button is visible

#### Scenario: Open ticket hides Reopen button

- GIVEN an open ticket row
- WHEN the row renders
- THEN no "Reopen" button is shown

#### Scenario: Transfer button on claimed ticket

- GIVEN a claimed ticket row
- WHEN the row renders for an admin
- THEN a "Transfer" button is visible

#### Scenario: Notes button always present

- GIVEN any ticket row
- WHEN the row renders for an admin
- THEN a "Notes" button is visible

#### Scenario: Non-admin sees no action buttons

- GIVEN a non-admin user viewing the ticket page
- WHEN ticket rows render
- THEN no action buttons are displayed

### Requirement: Notes panel

A collapsible notes panel MUST appear per ticket when the Notes button is clicked. It SHALL list existing notes (author, content, timestamp) and provide an add-note form. Staff-only: gated by `verifyGuildAdmin`.

#### Scenario: Open notes panel

- GIVEN an admin clicks the Notes button on ticket #5
- WHEN the panel expands
- THEN existing notes are fetched and displayed with author, content, timestamp

#### Scenario: Add note from panel

- GIVEN the notes panel is open
- WHEN admin submits a note via the form
- THEN the note is persisted and the list refreshes

#### Scenario: Non-admin cannot access notes

- GIVEN a non-admin user
- WHEN the page loads
- THEN no Notes button or panel is rendered

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
