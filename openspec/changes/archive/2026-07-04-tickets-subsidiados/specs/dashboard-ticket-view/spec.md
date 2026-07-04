# Delta for Dashboard Ticket View

## ADDED Requirements

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

Clicking the Reopen button MUST call the `reopenTicket` server action. On success, the ticket list refreshes to show the reopened ticket as `open`.

#### Scenario: Reopen via dashboard

- GIVEN admin clicks Reopen on closed ticket #3
- WHEN the server action completes successfully
- THEN the ticket status changes to `open` in the list and a success toast appears

### Requirement: Transfer action

Clicking Transfer MUST prompt for a staff member selection, then call `transferTicket` server action. On success, `claimedBy` updates in the list.

#### Scenario: Transfer via dashboard

- GIVEN admin selects a new staff member and confirms transfer
- WHEN the server action completes
- THEN `claimedBy` updates to the new staff member in the list
