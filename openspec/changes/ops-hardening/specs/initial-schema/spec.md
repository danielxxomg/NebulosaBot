# Delta for Initial Schema

## ADDED Requirements

### Requirement: Ticket channelId index

The system MUST create an index on `ticket ("channelId")` to support efficient lookups by `get_ticket_by_channel` and `update_ticket_last_activity`. The index SHALL be named `idx_ticket_channel`.

#### Scenario: Index exists after migration

- GIVEN migration 011 has been applied
- WHEN `pg_indexes` is queried for the `ticket` table
- THEN `idx_ticket_channel` appears on the `"channelId"` column

#### Scenario: Index is idempotent

- GIVEN the index already exists
- WHEN migration 011 runs again (using `CREATE INDEX IF NOT EXISTS`)
- THEN no error occurs and the index remains unchanged

#### Scenario: Query uses index

- GIVEN a ticket table with rows across multiple guilds
- WHEN `get_ticket_by_channel` executes a lookup by `channelId`
- THEN the query plan uses `idx_ticket_channel` (index scan, not sequential scan)
