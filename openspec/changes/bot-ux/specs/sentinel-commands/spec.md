# Delta for Sentinel Commands

## MODIFIED Requirements

### Requirement: Kick command

The `/kick` command MUST remove a member from the guild and create a KICK infraction. Before executing, the command MUST show an ephemeral confirmation dialog (via `ConfirmCancelView`) displaying the target user, reason, and Confirm/Cancel buttons. The kick only proceeds on explicit Confirm.

(Previously: `/kick` executed immediately with no confirmation step)

#### Scenario: Moderator kicks user

- GIVEN a moderator invokes `/kick` with reason "trolling"
- WHEN the moderator clicks Confirm on the ephemeral confirmation dialog
- THEN the member is removed and a KICK infraction is persisted

#### Scenario: Kick confirmation shown before execution

- GIVEN a moderator invokes `/kick` on a user
- WHEN the command is invoked
- THEN an ephemeral embed shows target, reason, and Confirm/Cancel buttons before any action

#### Scenario: Kick cancelled by moderator

- GIVEN a moderator sees the kick confirmation dialog
- WHEN the moderator clicks Cancel
- THEN the kick is not executed and a cancellation message is shown ephemerally

### Requirement: Ban command

The `/ban` command MUST be restricted to administrators, ban a user, and accept optional `delete_days` (0–7, default 0). Before executing, the command MUST show an ephemeral confirmation dialog (via `ConfirmCancelView`) displaying the target user, reason, delete_days, and Confirm/Cancel buttons. The ban only proceeds on explicit Confirm.

(Previously: `/ban` executed immediately with no confirmation step)

#### Scenario: Admin bans user

- GIVEN an administrator invokes `/ban` with reason "harassment"
- WHEN the administrator clicks Confirm on the ephemeral confirmation dialog
- THEN the user is banned and a BAN infraction is created

#### Scenario: Ban with message deletion

- GIVEN an administrator invokes `/ban` with `delete_days` set to 3
- WHEN the administrator clicks Confirm
- THEN the user is banned and up to 3 days of messages are deleted

#### Scenario: Ban confirmation shown before execution

- GIVEN an administrator invokes `/ban` on a user
- WHEN the command is invoked
- THEN an ephemeral embed shows target, reason, delete_days, and Confirm/Cancel buttons before any action

#### Scenario: Ban cancelled by administrator

- GIVEN an administrator sees the ban confirmation dialog
- WHEN the administrator clicks Cancel
- THEN the ban is not executed and a cancellation message is shown ephemerally
