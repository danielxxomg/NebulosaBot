# Unclaim Command Specification

## Purpose

Slash-only `/unclaim` command to release a claimed ticket, available to the claimer or moderators. Bot core is slash-only (`get_prefix -> []`).

## Requirements

### Requirement: Unclaim command exists

The system MUST provide a slash-only `/unclaim` command via `@app_commands.command()` (MUST NOT use `hybrid_command`; prefix inert via `get_prefix -> []`) that releases a claimed ticket. The command MUST reset `status` to `open` and `claimedBy` to `null`. Confirmation and error embeds MUST use `t()`. Authorization is via `TicketService.check_can_unclaim` (claimer-or-mod via service, not a `can_check` matrix key; no new matrix key) as specified in `permission-model`.

(Previously: hybrid `/unclaim` command (prefix + slash))

#### Scenario: Claimer unclaims ticket

- GIVEN a ticket claimed by userA with status `claimed`
- WHEN userA runs `/unclaim` via slash in the ticket channel
- THEN `claimedBy` is set to null, `status` becomes `open`, and a confirmation embed is sent via `t()`

#### Scenario: Mod unclaims another's ticket

- GIVEN a ticket claimed by userA with status `claimed`
- WHEN a mod (not userA) runs `/unclaim` via slash in the ticket channel
- THEN `claimedBy` is set to null, `status` becomes `open`, and a confirmation embed is sent via `t()`

#### Scenario: Unclaim on unclaimed ticket rejected

- GIVEN a ticket with `claimedBy=null` and status `open`
- WHEN any user runs `/unclaim` via slash
- THEN an ephemeral error embed via `t()` indicates the ticket is not claimed

#### Scenario: Prefix inert

- GIVEN a user sends `nb!unclaim` as text
- WHEN the message is processed
- THEN no command is invoked (`get_prefix -> []`)

### Requirement: Unclaim permission check

The system MUST enforce that only the claimer or users with mod role can unclaim via the service check `TicketService.check_can_unclaim`. Non-eligible users SHALL receive an ephemeral rejection via `t()`. The check MUST remain service-gated (claimer-or-mod) and MUST NOT be replaced by a matrix `can_check` decorator; the 7-key matrix is reused without a new key.

(Previously: described as hybrid permission; now slash-only service-gated)

#### Scenario: Non-claimer non-mod rejected

- GIVEN a ticket claimed by userA
- WHEN userB (not claimer, not mod) runs `/unclaim` via slash
- THEN an ephemeral error embed via `t()` is sent indicating insufficient permissions

### Requirement: Unclaim audit logging

Unclaim operations MUST be logged via the existing audit mechanism with action `unclaim` using `t()` for display strings where applicable.

#### Scenario: Unclaim audited

- GIVEN a successful unclaim operation via slash
- WHEN the unclaim completes
- THEN a `ticket_audit` row is written with action=unclaim, outcome=success
