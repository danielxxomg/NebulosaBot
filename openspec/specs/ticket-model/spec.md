# Ticket Model Specification

## Purpose

Define the `Ticket` and `TicketNote` dataclasses that mirror their respective database tables.

## Requirements

### Requirement: Ticket dataclass parent_id field

The `Ticket` dataclass MUST include `parent_id: str | None = None`, `subject: str | None = None`, `description: str | None = None`, and `custom_fields: dict[str, Any] | None = None`. `from_db_row` SHALL map `row["parentId"]`, `row["subject"]`, `row["description"]`, and `row["customFields"]`. `to_db_dict` SHALL include `"parentId": self.parent_id`, `"subject": self.subject`, `"description": self.description`, and `"customFields": self.custom_fields`.

#### Scenario: Deserialize ticket with parentId

- GIVEN a DB row with `parentId = "abc-123"`
- WHEN `Ticket.from_db_row(row)` is called
- THEN `ticket.parent_id == "abc-123"`

#### Scenario: Deserialize ticket without parentId

- GIVEN a DB row with `parentId = null`
- WHEN `Ticket.from_db_row(row)` is called
- THEN `ticket.parent_id is None`

#### Scenario: Serialize ticket with parentId

- GIVEN a Ticket with `parent_id = "abc-123"`
- WHEN `ticket.to_db_dict()` is called
- THEN the dict includes `"parentId": "abc-123"`

#### Scenario: Serialize ticket without parentId

- GIVEN a Ticket with `parent_id = None`
- WHEN `ticket.to_db_dict()` is called
- THEN the dict includes `"parentId": None`

#### Scenario: Deserialize ticket with subject and description

- GIVEN a DB row with `subject = "Login broken"` and `description = "Cannot access"`
- WHEN `Ticket.from_db_row(row)` is called
- THEN `ticket.subject == "Login broken"` and `ticket.description == "Cannot access"`

#### Scenario: Deserialize ticket without subject and description

- GIVEN a DB row with `subject = null` and `description = null`
- WHEN `Ticket.from_db_row(row)` is called
- THEN `ticket.subject is None` and `ticket.description is None`

#### Scenario: Serialize ticket with subject and description

- GIVEN a Ticket with `subject = "Bug"` and `description = "Details"`
- WHEN `ticket.to_db_dict()` is called
- THEN the dict includes `"subject": "Bug"` and `"description": "Details"`

#### Scenario: Deserialize ticket with custom_fields

- GIVEN a DB row with `customFields = {"player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/..."}`
- WHEN `Ticket.from_db_row(row)` is called
- THEN `ticket.custom_fields == {"player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/..."}`

#### Scenario: Deserialize ticket without custom_fields

- GIVEN a DB row with `customFields = null` or missing
- WHEN `Ticket.from_db_row(row)` is called
- THEN `ticket.custom_fields is None`

#### Scenario: Serialize ticket with custom_fields

- GIVEN a Ticket with `custom_fields = {"player_nick": "DarkSlayer42"}`
- WHEN `ticket.to_db_dict()` is called
- THEN the dict includes `"customFields": {"player_nick": "DarkSlayer42"}`

#### Scenario: Serialize ticket without custom_fields

- GIVEN a Ticket with `custom_fields = None`
- WHEN `ticket.to_db_dict()` is called
- THEN the dict includes `"customFields": None`

### Requirement: TicketNote dataclass

The system MUST provide a `TicketNote` dataclass with fields: `id` (str UUID), `ticket_id` (str), `author_id` (str), `content` (str), `created_at` (datetime). A `from_db_row` classmethod SHALL map camelCase DB keys to snake_case attributes. A `to_db_dict` method SHALL convert back to camelCase.

#### Scenario: Deserialize note

- GIVEN a DB row `{"id": "n1", "ticketId": "t1", "authorId": "s1", "content": "text", "createdAt": "2025-01-01T00:00:00Z"}`
- WHEN `TicketNote.from_db_row(row)` is called
- THEN `note.id == "n1"`, `note.ticket_id == "t1"`, `note.author_id == "s1"`, `note.content == "text"`

#### Scenario: Serialize note

- GIVEN a TicketNote instance
- WHEN `note.to_db_dict()` is called
- THEN the dict uses camelCase keys (`ticketId`, `authorId`, `createdAt`)

<!-- BEGIN DELTA: product-artifact-audit (ticket-model) -->
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

<!-- END DELTA: product-artifact-audit (ticket-model) -->

<!-- BEGIN DELTA: ticket-integrity-recovery (ticket-model) -->
## ADDED Requirements

### Requirement: Integrity evidence dataclass

The system MUST provide an `IntegrityEvidence` dataclass capturing corroborating evidence that a ticket is a zombie (open/claimed ticket whose channel no longer exists). Fields: `ticket_id` (str), `guild_id` (str), `channel_id` (str | None), `status` (str), `channel_exists` (bool), `corroborated` (bool). `corroborated` MUST be `True` only when `status` is `open` or `claimed` AND `channel_exists` is `False`. `from_db_row` SHALL map camelCase DB keys to snake_case; `to_db_dict` SHALL map back. Evidence MUST be derivable from a ticket row plus a channel-existence check and MUST NOT itself mutate state.

#### Scenario: Deserialize evidence

- GIVEN a DB row `{"ticketId":"t1","guildId":"g1","channelId":"c1","status":"open"}` and a channel-existence check returning `False`
- WHEN `IntegrityEvidence.from_db_row(row, channel_exists=False)` is called
- THEN `evidence.ticket_id=="t1"`, `evidence.channel_exists` is `False`, and `evidence.corroborated` is `True`

#### Scenario: Open ticket with existing channel not corroborated

- GIVEN a ticket row with `status="open"` and channel-existence check returning `True`
- WHEN `IntegrityEvidence.from_db_row(row, channel_exists=True)` is called
- THEN `evidence.corroborated` is `False`

#### Scenario: Closed ticket not corroborated regardless of channel

- GIVEN a ticket row with `status="closed"` and channel-existence check returning `False`
- WHEN `IntegrityEvidence.from_db_row(row, channel_exists=False)` is called
- THEN `evidence.corroborated` is `False`

#### Scenario: Serialize evidence

- GIVEN an `IntegrityEvidence` instance
- WHEN `evidence.to_db_dict()` is called
- THEN the dict uses camelCase keys (`ticketId`, `guildId`, `channelId`)

### Requirement: Repair result dataclass

The system MUST provide a `RepairResult` dataclass recording the outcome of a repair attempt so every mutation is auditable and idempotent. Fields: `ticket_id` (str), `guild_id` (str), `action` (str — one of `close`, `no_op`), `outcome` (str — one of `repaired`, `already_closed`, `skipped`, `error`), `reason` (str | None), `evidence_id` (str | None referencing the `IntegrityEvidence` that justified the action), `timestamp` (datetime). A result with `action="no_op"` and `outcome="already_closed"` MUST be produced when the ticket is already closed. Results MUST be deterministic given the same inputs so re-running repair does not duplicate mutations.

#### Scenario: Repaired zombie ticket

- GIVEN an `IntegrityEvidence` with `corroborated=True`
- WHEN repair applies the conditional close
- THEN `RepairResult.action=="close"`, `outcome=="repaired"`, and `evidence_id` references the evidence

#### Scenario: Already-closed ticket is no-op

- GIVEN a ticket row with `status="closed"`
- WHEN repair is attempted
- THEN `RepairResult.action=="no_op"`, `outcome=="already_closed"`, and no DB mutation occurs

#### Scenario: Skipped due to missing evidence

- GIVEN an `IntegrityEvidence` with `corroborated=False`
- WHEN repair is attempted
- THEN `RepairResult.action=="no_op"`, `outcome=="skipped"`, and no DB mutation occurs

#### Scenario: Error outcome records reason

- GIVEN repair raises a transient Discord error during verification
- WHEN the error is caught
- THEN `RepairResult.outcome=="error"` and `reason` contains the exception class name

<!-- END DELTA: ticket-integrity-recovery (ticket-model) -->
