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
