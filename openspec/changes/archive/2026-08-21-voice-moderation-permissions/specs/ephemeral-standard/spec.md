# Delta for Ephemeral Standard

## ADDED Requirements

### Requirement: Tempban confirmation is ephemeral and action is permanent

The `/tempban` command MUST follow the moderation action visibility standard: the confirmation dialog (`ConfirmCancelView` with target, duration, reason, Confirm/Cancel buttons) and the invalid-duration error MUST be ephemeral (visible only to the invoking moderator), while the final action confirmation (after `member.ban()` + `tempban()` insert) MUST be permanent (visible to the channel). The `/unban` command MUST send a permanent confirm embed when an active BAN is deactivated and lifted, and an ephemeral info embed when no active BAN exists (idempotent no-op). Both commands MUST be gated by `@can_check("moderation.ban")` so denial is surfaced via the standard prefix/slash error mapping.

#### Scenario: Tempban confirmation is ephemeral/permanent

- GIVEN a moderator invokes `/tempban @user 24h spam`
- WHEN the command is invoked
- THEN the `ConfirmCancelView` is shown ephemerally; after Confirm, the action confirm embed is permanent in the channel

#### Scenario: Unban confirmation is permanent

- GIVEN a moderator invokes `/unban <user_id>` and an active BAN is deactivated
- WHEN the command completes
- THEN a permanent confirm embed is sent to the channel (visible to all)

#### Scenario: Unban idempotent info is ephemeral

- GIVEN a moderator invokes `/unban <user_id>` and no active BAN exists
- WHEN the command completes
- THEN an ephemeral info embed is sent (no error, idempotent)
