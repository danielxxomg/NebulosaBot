# Delta for Ticket Service

## ADDED Requirements

### Requirement: Zombie auto-close writes an audit entry

When ANY automatic path (48h inactivity sweep, channel-delete repair, or scheduled-close loop) closes a ticket whose Discord channel is missing (zombie), the system MUST write a best-effort `ticket_audit` row recording the automated closure: `action="zombie_autoclose"`, `actorId="system"`, the applied close reason (e.g. `zombie:channel_missing`), and outcome. The audit insert MUST be best-effort: failure to write it MUST NOT abort or roll back the closure — the failure is logged at WARNING and the close stands.

#### Scenario: Sweep-closed zombie is audited

- GIVEN a corroborated zombie ticket is closed by the automatic sweep
- WHEN the closure completes
- THEN a `ticket_audit` row (`zombie_autoclose`, actorId=system) exists with the zombie close reason

#### Scenario: Channel-delete path audit

- GIVEN an active ticket whose channel is deleted externally
- WHEN the authoritative channel-delete repair closes it
- THEN the same `zombie_autoclose` audit row is written

#### Scenario: Audit failure does not block the close

- GIVEN the audit insert raises during a zombie autoclose
- WHEN the failure is caught
- THEN the ticket remains closed, no exception propagates to the sweep loop, and a WARNING is logged
