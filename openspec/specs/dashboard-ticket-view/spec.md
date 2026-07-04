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
