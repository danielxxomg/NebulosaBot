# Delta for ephemeral-standard

> Change: `cycle-5-quality-zero`. Scope: slash-only reality (whois→userinfo rename, stale command count dropped, Prefix-DM-fallback replaced). Archive note (non-normative): the Purpose line's stale "24 hybrid commands" count and "hybrid" wording MUST be reworded to "all registered slash commands" when merging this delta.

## ADDED Requirements

### Requirement: Slash-only error visibility

With the prefix surface disabled (see `bot-core`), no prefix-invocation error path exists. Application (slash) command error responses MUST be ephemeral — visible only to the invoking user. The former DM-fallback protection for admin prefix commands is obsolete: admin/config commands invoked via slash are already ephemeral by classification, so no response can pollute a public channel.

(Previously: admin prefix commands in public channels relied on a DM-first fallback with an ephemeral channel note when DMs failed.)

#### Scenario: Admin slash error stays ephemeral

- GIVEN an admin invokes `/config` and the command raises a handled error
- WHEN the error response is produced
- THEN the embed is ephemeral (no DM is sent, nothing is posted permanently)

#### Scenario: Prefix invocation produces no output

- GIVEN a user types `nb!ticket_panel` in #general
- WHEN the message is processed
- THEN no command executes and the bot posts no response (the prefix surface is inert)

## MODIFIED Requirements

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

### Requirement: Personal/info commands ephemeral standard

Personal or informational commands (ping, status, help, modlogs, userinfo) MUST respond ephemerally.

(Previously: the list named `whois`; the implemented command is `userinfo`.)

#### Scenario: /ping ephemeral

- GIVEN a user invokes `/ping`
- WHEN the command executes
- THEN the latency response is visible only to the invoking user

#### Scenario: /userinfo ephemeral

- GIVEN a user invokes `/userinfo`
- WHEN the command executes
- THEN the profile response is visible only to the invoking user

## REMOVED Requirements

### Requirement: Prefix DM fallback for admin commands

(Reason: the approved slash-only decision retires the prefix command surface (`nb!` retired; `GuildConfig.prefix` unread at runtime). With zero text-invocable commands, the DM-first fallback for admin prefix commands has no caller and its contract is replaced by "Slash-only error visibility".)
(Migration: delete the DM-first branch from the error-handling contract and adapt the 8 DM-first locking tests to assert the new slash-only behavior instead.)
