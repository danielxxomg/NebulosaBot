# Delta for Ticket Service

## MODIFIED Requirements

### Requirement: Audit logging on ticket operations

Every ticket operation (claim, close, reopen, transfer, subticket create, note add, note list, note delete) MUST write a `ticket_audit` row with ticketId, action, actorId, outcome, reason, timestamp. Audit inserts for claim and close operations MUST be best-effort: failure to write the audit row SHALL NOT abort the UI action (channel delete on close, role assignment on claim). Audit failures MUST be logged at WARNING level. Guild-scoped queries.

(Previously: audit failure on claim/close aborted the entire operation, preventing the UI action from completing even though the DB mutation had already succeeded)

#### Scenario: Claim audited on success

- GIVEN a mod claims ticket #5
- WHEN the claim succeeds
- THEN audit row (action=claim, outcome=success) is written

#### Scenario: Invariant violation audited

- GIVEN a non-mod attempts claim
- WHEN access is denied
- THEN audit row (action=claim, outcome=denied, reason) is written

#### Scenario: Claim succeeds despite audit failure

- GIVEN a mod claims ticket #5
- WHEN the claim mutation succeeds but `insert_audit_row` raises an exception
- THEN the claim UI action (role assignment) proceeds normally
- AND a WARNING log is emitted with the audit failure reason

#### Scenario: Close succeeds despite audit failure

- GIVEN a mod closes ticket #7
- WHEN the close mutation succeeds but `insert_audit_row` raises an exception
- THEN the close UI action (channel delete, transcript upload) proceeds normally
- AND a WARNING log is emitted with the audit failure reason

## ADDED Requirements

### Requirement: Migration parity for ticket_audit

Migration `012_ticket_audit.sql` MUST be tracked in git. Stale migration `005_ticket_audit.sql` (never applied, superseded by 012) MUST be removed from the repository.

#### Scenario: Migration 012 is tracked

- GIVEN `migrations/012_ticket_audit.sql` exists locally and is already applied on production
- WHEN the hotfix is committed
- THEN `012_ticket_audit.sql` is tracked in git via `git add`

#### Scenario: Stale 005 is removed

- GIVEN `migrations/005_ticket_audit.sql` exists but was never applied (different 005 exists remotely)
- WHEN the hotfix is committed
- THEN `005_ticket_audit.sql` is deleted from the repository
