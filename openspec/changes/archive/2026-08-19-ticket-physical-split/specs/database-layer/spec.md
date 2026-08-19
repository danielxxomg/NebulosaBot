# Delta for Database Layer

## ADDED Requirements

### Requirement: Read-only preflight before ticket type conversion

The database layer MUST run a read-only preflight before any cast or constraint DDL. It MUST verify 21/21 non-null `ticket.categoryId` values are valid UUIDs matching categories, parent references obey one-level depth, note orphans equal zero, and the current one-ticket-audit-orphan/one-guild-mismatch result is reconciled or explicitly approved by the retention policy. Any unapproved invalid, orphaned, duplicate, or retention row MUST abort the migration before the cast.

#### Scenario: Clean preflight permits staging

- GIVEN all category, parent, note, duplicate, and audit policy checks pass
- WHEN the preflight runs
- THEN it returns ready and performs no ticket mutation or type cast

#### Scenario: Invalid data blocks the cast

- GIVEN a malformed category UUID, orphan note, invalid parent, or unapproved audit row
- WHEN the preflight runs
- THEN it returns unresolved and no `USING` cast or constraint is attempted

### Requirement: Ordered validated ticket DDL

The migration MUST apply, in order: preflight; explicit `ticket.categoryId TEXT` to `UUID` `USING` cast; supporting child-side indexes; approved foreign keys; constraint validation; and only then removal of the redundant duplicate index. It MUST define `parentId → ticket.id ON DELETE RESTRICT`, `categoryId → ticket_category.id ON DELETE SET NULL`, `ticket_note.ticketId → ticket.id ON DELETE CASCADE`, and nullable `ticket_audit.ticketId → ticket.id ON DELETE SET NULL` after retention handling. The one allowed index drop is `idx_ticket_guild_number`; `idx_ticket_channel` and all other indexes MUST remain.

#### Scenario: DDL ordering is enforced

- GIVEN the migration is evaluated structurally
- WHEN its statements are inspected
- THEN preflight and cast precede constraints, validation precedes the sole duplicate-index drop, and rollback/lock evidence is present

#### Scenario: Foreign-key actions preserve ticket history

- GIVEN an approved migration is applied
- WHEN parent, category, note, or audit references are deleted
- THEN the declared RESTRICT, SET NULL, CASCADE, and SET NULL actions occur respectively

#### Scenario: Extra index removal is rejected

- GIVEN a migration proposes dropping `idx_ticket_channel` or any non-duplicate index
- WHEN the index policy is checked
- THEN validation fails and only `idx_ticket_guild_number` remains eligible for removal

### Requirement: Guild-scoped ticket database entries

Ticket, category, note, and audit database entry points MUST require or establish guild ownership before returning or changing data. The boundary MUST cover `get_ticket`, `get_ticket_by_channel`, `update_ticket`, `get_tickets_by_parent`, category access/deletion, note CRUD/dedup, and audit insert/read paths. Cross-guild identifiers MUST return no eligible row or an explicit denial and MUST NOT mutate data.

#### Scenario: Guild isolation is enforced

- GIVEN equivalent ticket or channel identifiers exist in guilds A and B
- WHEN guild A queries or mutates one identifier
- THEN only guild A data is eligible and guild B remains unchanged

#### Scenario: Audit denial retains a reason

- GIVEN a cross-guild note or audit operation is denied
- WHEN the denial is recorded
- THEN its audit reason is non-empty and the target row is not changed
