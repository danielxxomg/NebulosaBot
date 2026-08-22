# ephemeral-standard Specification

## Purpose

Classify all 24 hybrid commands by visibility behavior (ephemeral vs permanent) and define DM fallback for admin prefix commands that would otherwise pollute channels.

## Requirements

### Requirement: Command visibility classification

Every hybrid command MUST be classified as either ephemeral (visible only to the invoking user) or permanent (visible to all) based on its category.

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

All moderation action commands (warn, unwarn, mute, unmute, kick, ban, lock, unlock) MUST respond permanently so the action is visible to the channel.

#### Scenario: /warn permanent

- GIVEN a moderator invokes `/warn`
- WHEN the command executes
- THEN the confirmation embed is visible to all users in the channel

### Requirement: Personal/info commands ephemeral standard

Personal or informational commands (ping, status, help, modlogs, whois) MUST respond ephemerally.

#### Scenario: /ping ephemeral

- GIVEN a user invokes `/ping`
- WHEN the command executes
- THEN the latency response is visible only to the invoking user

### Requirement: Prefix DM fallback for admin commands

When an administrative command is invoked via prefix in a public channel, the bot MUST send the response as a DM to the invoking user instead of the channel.

#### Scenario: Admin prefix command DM response

- GIVEN an admin invokes `nb!ticket_panel` in #general
- WHEN the command executes successfully
- THEN the confirmation embed is sent as a DM to the admin

#### Scenario: Admin prefix DM failure

- GIVEN an admin invokes `nb!ticket_panel` in #general
- WHEN the bot cannot DM the user (DMs disabled)
- THEN the response is sent ephemerally in the channel with a note to enable DMs

### Requirement: Fun commands permanent standard

Fun/economy commands (balance, daily, work, leaderboard) MUST respond permanently.

#### Scenario: /balance permanent

- GIVEN a user invokes `/balance`
- WHEN the command executes
- THEN the balance embed is visible to all users in the channel

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
