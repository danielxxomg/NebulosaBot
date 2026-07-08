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
