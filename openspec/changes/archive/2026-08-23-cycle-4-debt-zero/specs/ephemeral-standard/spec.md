# Delta for ephemeral-standard

## MODIFIED Requirements

### Requirement: Mod action commands permanent standard

All moderation action commands (warn, unwarn, mute, unmute, kick, ban, lock, unlock) MUST respond permanently so the action is visible to the channel. For commands fronted by a `ConfirmCancelView` (kick, ban), visibility is two-phase: the confirmation dialog and any cancel/timeout feedback stay ephemeral, while the FINAL action result (after execution) MUST be a permanent channel message — it MUST NOT be delivered only as an edit of the ephemeral dialog.

(Previously: kick and ban delivered their final result solely by editing the ephemeral confirmation message, violating this standard in practice.)

#### Scenario: /warn permanent

- GIVEN a moderator invokes `/warn`
- WHEN the command executes
- THEN the confirmation embed is visible to all users in the channel

#### Scenario: /kick final result is permanent

- GIVEN a moderator confirms a `/kick` dialog
- WHEN the kick executes
- THEN the final result embed is posted as a permanent channel message

#### Scenario: /ban final result is permanent

- GIVEN an administrator confirms a `/ban` dialog
- WHEN the ban executes
- THEN the final result embed is posted as a permanent channel message

#### Scenario: Dialog phase remains ephemeral

- GIVEN any moderation command shows its `ConfirmCancelView`
- WHEN the dialog is displayed, cancelled, or times out
- THEN those interactions remain ephemeral (only the executed result becomes permanent)
