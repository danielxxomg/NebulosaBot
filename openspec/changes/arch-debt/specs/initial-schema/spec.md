# Delta for Initial Schema

## ADDED Requirements

### Requirement: ticket_note RLS migration

A migration file `008_ticket_note_rls.sql` MUST exist that enables Row Level Security on the `ticket_note` table. The migration MUST be idempotent — re-running it SHALL NOT produce an error.

#### Scenario: Migration applied

- GIVEN the database has migrations 001–007 applied
- WHEN migration 008 runs
- THEN RLS is enabled on `ticket_note`

#### Scenario: Idempotent re-run

- GIVEN migration 008 was already applied
- WHEN migration 008 runs again
- THEN no error occurs (ALTER TABLE ENABLE RLS is a no-op when already enabled)

### Requirement: Member increment RPC functions

Migration `009_member_increment_rpc.sql` MUST create Postgres functions for atomic member field increments: `increment_member_xp(guild_id, user_id, amount)`, `increment_member_coins(guild_id, user_id, amount)`, `increment_member_warnings(guild_id, user_id, amount)`, `set_member_daily(guild_id, user_id, ts)`. Each function MUST be atomic (single SQL statement, no separate GET + UPDATE).

#### Scenario: increment_member_xp atomic update

- GIVEN a member with xp=100
- WHEN `increment_member_xp(guild_id, user_id, 25)` is called
- THEN xp becomes 125 in a single DB round trip

#### Scenario: set_member_daily atomic update

- GIVEN a member with lastDaily=null
- WHEN `set_member_daily(guild_id, user_id, '2026-07-08T00:00:00Z')` is called
- THEN lastDaily is set in a single DB round trip

#### Scenario: Upsert on first increment

- GIVEN no member_economy row exists for (guild_id, user_id)
- WHEN `increment_member_xp(guild_id, user_id, 10)` is called
- THEN a row is created with xp=10 (upsert semantics)
