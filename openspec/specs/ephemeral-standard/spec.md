# ephemeral-standard Specification

## Purpose

Classify all registered slash commands by visibility behavior (ephemeral vs permanent). With the prefix surface inert (`bot-core`), application-command error responses are always ephemeral, so no response can pollute a public channel.

## Requirements

### Requirement: Slash-only error visibility

With the prefix surface disabled (see `bot-core`), no prefix-invocation error path exists. Application (slash) command error responses MUST be ephemeral — visible only to the invoking user. Permission-denial branches (`CheckFailure`, `MissingPermissions`) MUST produce an ephemeral localized reply through the global handler — they MUST NOT surface as unhandled errors and MUST NOT post publicly, even for commands whose normal response is permanent.

#### Scenario: Admin slash error stays ephemeral

- GIVEN an admin invokes `/config` and the command raises a handled error
- WHEN the error response is produced
- THEN the embed is ephemeral (no DM is sent, nothing is posted permanently)

#### Scenario: Prefix invocation produces no output

- GIVEN a user types `nb!ticket_panel` in #general
- WHEN the message is processed
- THEN no command executes and the bot posts no response (the prefix surface is inert)

#### Scenario: CheckFailure denial is ephemeral on a permanent command

- GIVEN a user without the required matrix grant invokes a permanent-response guarded command
- WHEN `CheckFailure` is raised
- THEN an ephemeral localized denial reply is sent and nothing is posted publicly

### Requirement: Command visibility classification

Every registered slash command MUST be classified as either ephemeral (visible only to the invoking user) or permanent (visible to all) based on its category.

#### Scenario: Admin command is ephemeral

- GIVEN a command classified as `admin`
- WHEN a user invokes it via slash
- THEN the response is ephemeral

#### Scenario: Mod action is permanent

- GIVEN a command classified as `mod-action`
- WHEN a moderator invokes it via slash
- THEN the response is permanent in the channel

#### Scenario: Fun command is permanent

- GIVEN a command classified as `fun`
- WHEN a user invokes it via slash
- THEN the response is permanent

### Requirement: Admin commands ephemeral standard

All administrative/configuration commands (ticket_panel, create_category, list_categories, delete_category, setup, config) MUST respond ephemerally via slash commands.

#### Scenario: /ticket_panel ephemeral

- GIVEN an admin invokes `/ticket_panel`
- WHEN the command executes
- THEN the confirmation embed is visible only to the invoking user

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

### Requirement: Personal/info commands ephemeral standard

Personal or informational commands (ping, status, help, modlogs, userinfo) MUST respond ephemerally.

#### Scenario: /ping ephemeral

- GIVEN a user invokes `/ping`
- WHEN the command executes
- THEN the latency response is visible only to the invoking user

#### Scenario: /userinfo ephemeral

- GIVEN a user invokes `/userinfo`
- WHEN the command executes
- THEN the profile response is visible only to the invoking user

### Requirement: Fun commands permanent standard

Fun/economy commands (balance, daily, work, leaderboard) MUST respond permanently. Ocio fun commands `/dice`, `/8ball`, and `/banana` MUST also respond permanently — the prior ocio-ephemeral exception is REMOVED from this standard. Their cooldown-error replies remain ephemeral (error feedback).

#### Scenario: /balance permanent

- GIVEN a user invokes `/balance`
- WHEN the command executes
- THEN the balance embed is visible to all users in the channel

#### Scenario: Ocio fun responses are permanent

- GIVEN users invoke `/dice`, `/8ball`, or `/banana`
- WHEN each command executes successfully
- THEN each reply is permanent and visible to all users in the channel

#### Scenario: Ocio cooldown errors stay ephemeral

- GIVEN a user re-invokes an ocio command inside its cooldown window
- WHEN the cooldown handler replies
- THEN that retry-after feedback is ephemeral, not public

<!-- BEGIN DELTA: voice-moderation-permissions (ephemeral-standard) -->
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
<!-- END DELTA: voice-moderation-permissions (ephemeral-standard) -->
