# Delta for confirm-dialog

## MODIFIED Requirements

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
