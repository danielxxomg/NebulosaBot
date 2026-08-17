# Delta for Ticket Model

## ADDED Requirements

### Requirement: Integrity evidence contract

The system MUST provide an immutable `IntegrityEvidence` contract containing an evidence ID, ticket ID, guild ID, channel ID, active status, `channel_exists: bool | None`, observation time, source, and derived corroboration. Corroboration MUST be true only for an active ticket with `channel_exists=False` and evidence within the configured freshness window. Unknown, missing, ambiguous, or stale channel evidence MUST remain explicitly unresolved and MUST NOT be coerced to false. Evidence construction MUST NOT mutate ticket state.

#### Scenario: Fresh absence corroborates

- GIVEN an active ticket and a fresh Discord check returning channel absent
- WHEN evidence is constructed
- THEN corroboration is true and the evidence has a unique ID

#### Scenario: Unknown evidence remains unresolved

- GIVEN a timeout, missing channel ID, or `channel_exists=None`
- WHEN evidence is constructed
- THEN corroboration is unknown/unresolved and no mutation decision is implied

#### Scenario: Existing channel is safe

- GIVEN an active ticket and a fresh Discord check returning channel present
- WHEN evidence is constructed
- THEN corroboration is false and repair is not authorized

### Requirement: Repair and quarantine result contracts

The system MUST provide immutable `RepairResult` and `CloseResult` contracts. `RepairResult` MUST distinguish `repaired`, `already_closed`, `quarantined`, and `error`; a quarantined or denied result MUST carry non-empty review evidence/reason. A successful repair MUST carry the evidence ID. `CloseResult` MUST distinguish success, denied, and error while preserving close reason, transcript URL, and optional evidence ID. Results MUST be serializable and MUST NOT claim mutation for no-op or quarantine outcomes.

#### Scenario: Safe repair result is auditable

- GIVEN corroborated evidence authorizes a conditional close
- WHEN repair completes
- THEN the result says repaired and references a non-empty evidence ID

#### Scenario: Quarantine is not mutation

- GIVEN evidence is ambiguous or stale
- WHEN repair is attempted
- THEN the result says quarantined or no-op with a non-empty reason and no mutation claim

#### Scenario: Duplicate close is deterministic

- GIVEN the ticket is already closed
- WHEN repair runs again
- THEN the result says no-op/already-closed and contains no second success transition
