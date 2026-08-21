# Delta for Ticket Model

Cycle 2 of 3. Adds two additive nullable columns to `ticket` for the `,12h`
scheduled-close timer: `scheduledCloseAt TIMESTAMPTZ` (when the timer fires)
and `scheduledCloseBy TEXT` (the mod who set the timer). Both are nullable,
additive (migration `022+`), and backwards-compatible: pre-migration rows read
back `null` and behave as before (no scheduled close). A partial index
`WHERE status IN ('open','claimed') AND "scheduledCloseAt" IS NOT NULL` MUST
be added to support the 60s loop batch lookup. The columns round-trip through
`Ticket.from_db_row`/`to_db_dict`. The migration MUST be validated against the
live `schema_migrations` table before apply.

## ADDED Requirements

### Requirement: Scheduled-close columns are additive and nullable

The system MUST add optional nullable `scheduledCloseAt TIMESTAMPTZ` and
`scheduledCloseBy TEXT` columns to the `ticket` table via an additive,
backwards-compatible migration numbered `022` or higher. Both columns MUST
default to null. Existing rows MUST remain valid: pre-migration rows read
back `scheduledCloseAt`/`scheduledCloseBy` as null and MUST NOT be auto-closed
(only the existing 48h `AUTO_CLOSE` sweep applies to them). The migration
identity MUST be checked against the live `schema_migrations` table before
apply. Rollback MUST be `DROP COLUMN` for both columns and `DROP INDEX` for
the partial index (additive nullable, reversible).

#### Scenario: Existing rows remain valid after migration

- GIVEN an existing `ticket` row without `scheduledCloseAt`/`scheduledCloseBy`
- WHEN the additive `022+` migration is applied
- THEN the row is preserved, reads back `scheduledCloseAt` and `scheduledCloseBy` as null, and is NOT scheduled for close

#### Scenario: Migration identity checked live

- GIVEN the `022+` migration file is staged
- WHEN the migration is about to apply
- THEN the live `schema_migrations` table is queried and the migration is applied only if its version is not already recorded

#### Scenario: Rollback drops the nullable columns

- GIVEN the `022+` migration was applied
- WHEN the rollback runs (`DROP COLUMN "scheduledCloseAt"`, `DROP COLUMN "scheduledCloseBy"`, `DROP INDEX` the partial index)
- THEN the columns and index are removed, existing rows remain valid, and only the 48h `AUTO_CLOSE` sweep applies

### Requirement: Scheduled-close columns round-trip through the model

The `Ticket` dataclass MUST include `scheduled_close_at: datetime | None =
None` and `scheduled_close_by: str | None = None`. `from_db_row` SHALL map
`row["scheduledCloseAt"]`/`row["scheduledCloseBy"]`; `to_db_dict` SHALL
include `"scheduledCloseAt": self.scheduled_close_at` and
`"scheduledCloseBy": self.scheduled_close_by` (ISO-8601 for the timestamp).
Round-trips MUST preserve a null and a non-null value unchanged.

#### Scenario: Deserialize ticket with scheduled-close set

- GIVEN a DB row with `scheduledCloseAt = "2026-08-20T12:00:00Z"` and `scheduledCloseBy = "mod1"`
- WHEN `Ticket.from_db_row(row)` is called
- THEN `ticket.scheduled_close_at` equals the parsed datetime and `ticket.scheduled_close_by == "mod1"`

#### Scenario: Deserialize ticket without scheduled-close

- GIVEN a DB row with `scheduledCloseAt = null` and `scheduledCloseBy = null`
- WHEN `Ticket.from_db_row(row)` is called
- THEN `ticket.scheduled_close_at is None` and `ticket.scheduled_close_by is None`

#### Scenario: Serialize ticket with scheduled-close set

- GIVEN a `Ticket` with `scheduled_close_at` and `scheduled_close_by` set
- WHEN `ticket.to_db_dict()` is called
- THEN the dict includes `"scheduledCloseAt"` (ISO-8601) and `"scheduledCloseBy"` with the values

#### Scenario: Serialize ticket without scheduled-close

- GIVEN a `Ticket` with both scheduled-close fields `None`
- WHEN `ticket.to_db_dict()` is called
- THEN the dict includes `"scheduledCloseAt": None` and `"scheduledCloseBy": None`

### Requirement: Partial index on scheduled-close candidates

The system MUST create a partial index on `ticket` scoped to scheduled-close
candidates: `WHERE status IN ('open','claimed') AND "scheduledCloseAt" IS NOT
NULL`. The index MUST support the 60s loop batch lookup (batch size 50) that
selects active tickets whose `scheduledCloseAt <= now()` and is NOT a full-
table scan. The index is additive (drop on rollback). It MUST coexist with the
existing partial index `idx_ticket_active_channel` (`WHERE status IN
('open','claimed')`) from `015_ticket_lifecycle_reliability.sql`.

#### Scenario: Partial index exists with the correct predicate

- GIVEN the `022+` migration is applied
- WHEN the `ticket` indexes are inspected
- THEN a partial index exists with predicate `status IN ('open','claimed') AND "scheduledCloseAt" IS NOT NULL`

#### Scenario: Coexists with the existing active-channel partial index

- GIVEN both `015` and `022+` are applied
- WHEN the `ticket` indexes are inspected
- THEN both `idx_ticket_active_channel` (`status IN ('open','claimed')`) and the scheduled-close partial index exist

## MODIFIED Requirements

### Requirement: Ticket dataclass parent_id field

The `Ticket` dataclass MUST include `parent_id: str | None = None`, `subject: str | None = None`, `description: str | None = None`, `custom_fields: dict[str, Any] | None = None`, `scheduled_close_at: datetime | None = None`, and `scheduled_close_by: str | None = None`. `from_db_row` SHALL map `row["parentId"]`, `row["subject"]`, `row["description"]`, `row["customFields"]`, `row["scheduledCloseAt"]`, and `row["scheduledCloseBy"]`. `to_db_dict` SHALL include `"parentId": self.parent_id`, `"subject": self.subject`, `"description": self.description`, `"customFields": self.custom_fields`, `"scheduledCloseAt": self.scheduled_close_at`, and `"scheduledCloseBy": self.scheduled_close_by`.
(Previously: the dataclass included parent_id, subject, description, and custom_fields; it had no scheduled-close fields.)

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

#### Scenario: Deserialize ticket with scheduledCloseAt and scheduledCloseBy

- GIVEN a DB row with `scheduledCloseAt = "2026-08-20T12:00:00Z"` and `scheduledCloseBy = "mod1"`
- WHEN `Ticket.from_db_row(row)` is called
- THEN `ticket.scheduled_close_at` equals the parsed datetime and `ticket.scheduled_close_by == "mod1"`

#### Scenario: Serialize ticket with scheduledCloseAt and scheduledCloseBy

- GIVEN a Ticket with `scheduled_close_at` and `scheduled_close_by` set
- WHEN `ticket.to_db_dict()` is called
- THEN the dict includes `"scheduledCloseAt"` (ISO-8601) and `"scheduledCloseBy"` with the values

## Scope boundary

This delta adds only the scheduled-close columns, model round-trip, and
partial index. The `,12h` listener, the 60s loop, `,cancel`,
`format_remaining`, and the `<2h`/`>5d` confirm are specified in
`ticket-service`, `close-confirmation`, and `close-countdown`. Cycle 3
(voice/moderation, ScheduledAction, has_perm) is OUT OF SCOPE.
