# Unclaim Command Specification

## Purpose

Hybrid `/unclaim` command to release a claimed ticket, available to the claimer or moderators.

## Requirements

### Requirement: Unclaim command exists

The system MUST provide a `/unclaim` hybrid command (prefix + slash) that releases a claimed ticket. The command MUST reset `status` to `open` and `claimedBy` to `null`.

#### Scenario: Claimer unclaims ticket

- GIVEN a ticket claimed by userA with status `claimed`
- WHEN userA runs `/unclaim` in the ticket channel
- THEN `claimedBy` is set to null, `status` becomes `open`, and a confirmation embed is sent

#### Scenario: Mod unclaims another's ticket

- GIVEN a ticket claimed by userA with status `claimed`
- WHEN a mod (not userA) runs `/unclaim` in the ticket channel
- THEN `claimedBy` is set to null, `status` becomes `open`, and a confirmation embed is sent

#### Scenario: Unclaim on unclaimed ticket rejected

- GIVEN a ticket with `claimedBy=null` and status `open`
- WHEN any user runs `/unclaim`
- THEN an ephemeral error embed indicates the ticket is not claimed

### Requirement: Unclaim permission check

The system MUST enforce that only the claimer or users with mod role can unclaim. Non-eligible users SHALL receive an ephemeral rejection.

#### Scenario: Non-claimer non-mod rejected

- GIVEN a ticket claimed by userA
- WHEN userB (not claimer, not mod) runs `/unclaim`
- THEN an ephemeral error embed is sent indicating insufficient permissions

### Requirement: Unclaim audit logging

Unclaim operations MUST be logged via the existing audit mechanism with action `unclaim`.

#### Scenario: Unclaim audited

- GIVEN a successful unclaim operation
- WHEN the unclaim completes
- THEN a `ticket_audit` row is written with action=unclaim, outcome=success
