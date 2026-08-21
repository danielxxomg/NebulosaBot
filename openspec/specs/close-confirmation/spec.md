# Close Confirmation Specification

## Purpose

Ephemeral Confirm/Cancel dialog before manual ticket close to prevent accidental closures.

## Requirements

### Requirement: Ephemeral close confirmation

When a user with close permission clicks the Close button on a ticket action view, the system MUST send an ephemeral confirmation embed with Confirm and Cancel buttons using `ConfirmCancelView`. Dismissing the ephemeral message SHALL be treated as cancel (no close occurs).

#### Scenario: User confirms close

- GIVEN an open ticket channel with the action view
- WHEN a user with close permission clicks Close and then clicks Confirm on the ephemeral dialog
- THEN the ticket close flow proceeds (transcript, log, DB close, countdown, channel delete)

#### Scenario: User cancels close

- GIVEN an open ticket channel with the action view
- WHEN a user clicks Close and then clicks Cancel
- THEN a cancellation message is shown ephemerally and the ticket remains open

#### Scenario: User dismisses ephemeral message

- GIVEN an open ticket channel with the action view
- WHEN a user clicks Close and dismisses the ephemeral confirmation without clicking either button
- THEN no close occurs and the ticket remains open

#### Scenario: Confirmation times out

- GIVEN a close confirmation dialog is shown
- WHEN 30 seconds elapse with no interaction
- THEN both buttons are disabled and the ticket remains open

### Requirement: Close confirmation only for manual close

The ephemeral confirmation dialog MUST appear ONLY for manual close actions (button click). Auto-close (48h inactivity) SHALL NOT trigger confirmation — it proceeds silently.

#### Scenario: Auto-close bypasses confirmation

- GIVEN a ticket inactive for 48 hours
- WHEN the auto-close task runs
- THEN the ticket is closed silently without any confirmation dialog

### Requirement: Only authorized user can confirm

The Confirm and Cancel buttons MUST only respond to the user who clicked Close. Other users clicking the buttons SHALL receive an ephemeral rejection.

#### Scenario: Different user clicks confirm

- GIVEN modA clicked Close and sees the confirmation dialog
- WHEN modB clicks Confirm
- THEN an ephemeral message indicates only the closer can confirm


<!-- BEGIN DELTA: welcome-neon-timer-banana (close-confirmation) -->

## ADDED Requirements
### Requirement: Timer confirmation under <2h and >5d thresholds

When a mod schedules a close with `,<duration>` in an open/claimed ticket
channel, the system MUST show an ephemeral `ConfirmCancelView` confirmation
when the duration is below 2 hours (`<2h`) or above 5 days (`>5d`). The
confirmation MUST display the requested duration, the proposed
`scheduledCloseAt`, and Confirm/Cancel buttons. Only the mod who issued the
timer MAY confirm (the view is owner-only, same contract as manual close). On
Confirm, the timer is set (the `scheduledCloseAt`/`scheduledCloseBy` write and
the pinned `<t:R>`/`<t:F>` embed). On Cancel or 30s timeout, no timer is set
and the ticket remains unchanged. Durations within `2h..5d` (inclusive) MUST
set the timer immediately without confirmation.

#### Scenario: Duration under 2h requires confirmation

- GIVEN an open ticket channel and a mod who sends `,1h`
- WHEN the parser returns 3600 (below 2h)
- THEN an ephemeral ConfirmCancelView is shown; the timer is set only on Confirm

#### Scenario: Duration over 5d requires confirmation

- GIVEN an open ticket channel and a mod who sends `,10d`
- WHEN the parser returns 864000 (above 5d)
- THEN an ephemeral ConfirmCancelView is shown; the timer is set only on Confirm

#### Scenario: Duration within 2h..5d sets timer immediately

- GIVEN an open ticket channel and a mod who sends `,12h`
- WHEN the parser returns 43200 (within 2h..5d)
- THEN the timer is set immediately with no confirmation dialog

#### Scenario: Confirm sets the timer

- GIVEN an ephemeral timer confirmation is shown for `,1h`
- WHEN the issuing mod clicks Confirm
- THEN `scheduledCloseAt`/`scheduledCloseBy` are set and the pinned `<t:R>`/`<t:F>` embed is posted

#### Scenario: Cancel or timeout leaves the ticket unchanged

- GIVEN an ephemeral timer confirmation is shown for `,1h`
- WHEN the mod clicks Cancel OR 30 seconds elapse with no interaction
- THEN no timer is set, `scheduledCloseAt`/`scheduledCloseBy` remain NULL, and the ticket remains open/claimed

#### Scenario: Only the issuing mod can confirm

- GIVEN modA issued `,1h` and sees the confirmation dialog
- WHEN modB clicks Confirm
- THEN an ephemeral message indicates only the issuing mod can confirm and no timer is set
<!-- END DELTA: welcome-neon-timer-banana (close-confirmation) -->
