# Confirm Dialog Specification

## Purpose

Reusable ephemeral Confirm/Cancel view for destructive moderator actions.

## Requirements

### Requirement: Confirm cancel view

The system MUST provide a `ConfirmCancelView` that sends an ephemeral embed with Confirm and Cancel buttons. Button labels MUST be resolved via `t(guild_id, key)` using the invoking guild's language. The view MUST time out after 30 seconds, disabling both buttons on timeout. The constructor MUST accept a `guild_id` parameter.

(Previously: button labels were hardcoded English "Confirm" and "Cancel")

#### Scenario: User confirms action

- GIVEN an ephemeral confirmation embed is shown
- WHEN the user clicks Confirm
- THEN the provided callback is executed and the original message is updated

#### Scenario: User cancels action

- GIVEN an ephemeral confirmation embed is shown
- WHEN the user clicks Cancel
- THEN a cancellation message is sent ephemerally and no action is taken

#### Scenario: Confirmation times out

- GIVEN an ephemeral confirmation embed is shown
- WHEN 30 seconds elapse with no interaction
- THEN both buttons are disabled and an ephemeral timeout message is sent

#### Scenario: Spanish guild shows Spanish buttons

- GIVEN a guild with language `es`
- WHEN a `ConfirmCancelView` is created with `guild_id`
- THEN the Confirm button label is the Spanish `t()` value and Cancel button label is the Spanish `t()` value

#### Scenario: English guild shows English buttons

- GIVEN a guild with language `en`
- WHEN a `ConfirmCancelView` is created with `guild_id`
- THEN the Confirm button label is the English `t()` value and Cancel button label is the English `t()` value

### Requirement: Confirmation detail embed

The confirmation embed MUST display the action type, target user, and reason so the moderator can verify before confirming.

#### Scenario: Ban confirmation shows details

- GIVEN a moderator invokes `/ban` on a user with reason "harassment"
- WHEN the confirmation dialog is shown
- THEN the embed displays "Ban", the target user mention, and the reason

### Requirement: Only invoker can interact

The Confirm and Cancel buttons MUST only respond to the user who invoked the command. Other users clicking the buttons SHALL receive an ephemeral rejection.

#### Scenario: Different user clicks confirm

- GIVEN moderator A invoked `/ban` and sees the confirmation
- WHEN moderator B clicks Confirm
- THEN an ephemeral message indicates only the invoker can confirm

<!-- BEGIN DELTA: cycle-4-debt-zero (confirm-dialog) -->
## ADDED Requirements

### Requirement: Ephemeral dialog, permanent outcome

`ConfirmCancelView` MUST always render ephemerally at every call site. When the wrapped action belongs to a category whose results are permanent (mod-action per the ephemeral-standard), the calling command MUST deliver the final outcome as a permanent channel message; the ephemeral dialog MUST NOT double as the permanent record. Cancel and timeout outcomes remain ephemeral in all cases.

#### Scenario: Moderation dialog outcome split

- GIVEN `/kick` shows the view and the moderator confirms
- WHEN execution finishes
- THEN a permanent channel embed carries the result and the ephemeral dialog does not serve as the permanent record

#### Scenario: Cancel and timeout stay ephemeral

- GIVEN the view is cancelled or times out
- WHEN feedback is delivered
- THEN it is ephemeral, visible only to the invoking user
<!-- END DELTA: cycle-4-debt-zero (confirm-dialog) -->
