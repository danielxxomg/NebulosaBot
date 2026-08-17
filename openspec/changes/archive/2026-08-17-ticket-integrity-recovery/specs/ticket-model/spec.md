# Delta for Ticket Model

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
