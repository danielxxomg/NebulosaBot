# Delta for Database Layer

Cycle 2 of 3. Completes the security/Supabase carry: `ENABLE ROW LEVEL
SECURITY` on the remaining public tables (`guild`, `member`, `infraction`,
`ticket`, `ticket_category`, `economy_config`, `greeting_config`) so the
service_role client is the only path that reads them; `AsyncClientOptions`
gets `auto_refresh_token=False` and `persist_session=False` flags; the
greeting upsert handles Postgres `23505` (unique violation) idempotently;
bot-side `select("*")` is replaced with explicit columns scoped to the
Cycle-2-touched mixins (greeting, ticket) — economy/infraction are deferred to
Cycle 3. All migrations are additive nullable; the live `schema_migrations`
table MUST be validated before apply.

## ADDED Requirements

### Requirement: RLS enabled on remaining tables

The system MUST `ENABLE ROW LEVEL SECURITY` on the remaining public tables
that lack it: `guild`, `member`, `infraction`, `ticket`, `ticket_category`,
`economy_config`, and `greeting_config` (only `ticket_note` and `ticket_audit`
have RLS today, per `008` and `012`). Enabling RLS with no policies denies
anon/publishable/authenticated access; the bot's `service_role` client is
unaffected (service_role bypasses RLS). The migration is additive (RLS enable
is reversible by `DISABLE ROW LEVEL SECURITY` on rollback). This MUST NOT
break the bot: startup already validates the credential is service-role
(`cleanup-stability` contract) and the health probe reads `guild`+`ticket`.
The migration MUST be validated against the live `schema_migrations` table
before apply (prior staging drift on 2026-08-19).

#### Scenario: RLS enabled on remaining tables

- GIVEN the Cycle 2 migration is applied
- WHEN the table RLS state is inspected
- THEN `guild`, `member`, `infraction`, `ticket`, `ticket_category`, `economy_config`, and `greeting_config` each have `rowsecurity = true`

#### Scenario: Service_role access is unaffected

- GIVEN the bot's service_role client after RLS enable
- WHEN it reads `guild` and `greeting_config`
- THEN reads succeed (service_role bypasses RLS) and the health probe still passes

#### Scenario: Anon access denied

- GIVEN an anon/publishable/authenticated credential after RLS enable
- WHEN it attempts to read any of the RLS-enabled tables
- THEN access is denied and no rows are returned

#### Scenario: Live schema_migrations validated before apply

- GIVEN the RLS migration file is staged
- WHEN the migration is about to apply
- THEN the live `schema_migrations` table is queried and the migration is applied only if its version is not already recorded

### Requirement: AsyncClientOptions auto_refresh and persist_session flags

The async Supabase client MUST be constructed with
`AsyncClientOptions(schema="public", auto_refresh_token=False,
persist_session=False)`. The bot is a server-side service_role client with a
static `sb_secret_` key; it MUST NOT auto-refresh tokens or persist a session
to disk. The existing `schema="public"` and the fail-closed service_role
validation (`cleanup-stability`) MUST remain unchanged. This is a config-only
change: no DB schema mutation, no behavior change to reads/writes.

#### Scenario: Client constructed with both flags

- GIVEN `Database.connect()` runs
- WHEN `acreate_client` is called
- THEN `AsyncClientOptions` is passed with `auto_refresh_token=False` and `persist_session=False` alongside `schema="public"`

#### Scenario: Service_role validation still fail-closed

- GIVEN a non-service-role credential is configured
- WHEN startup validation runs
- THEN startup fails closed (unchanged from `cleanup-stability`) regardless of the new flags

### Requirement: 23505 idempotent handling on greeting upsert

`upsert_greeting_config` MUST handle a Postgres `23505` (unique violation)
that can race on concurrent upserts for the same `guildId`. On `23505`, the
upsert MUST be retried once (re-read-conflict then re-upsert) or treated as a
no-op success (the row already exists with the intended key); it MUST NOT
surface a raw `UniqueViolation`/`duplicate key` traceback to the user or abort
the cache-first read. The greeting config is keyed by `guildId` (unique), so a
`23505` means another writer won the race — the result is the same config.
This handling MUST be added to the greeting upsert path; other upserts are
out of scope for Cycle 2.

#### Scenario: Concurrent upsert races resolve to 23505 no-op

- GIVEN two concurrent `upsert_greeting_config` calls for the same guild
- WHEN one wins and the other receives `23505`
- THEN the loser retries once or treats it as a no-op success and no `UniqueViolation` traceback is surfaced

#### Scenario: 23505 does not abort the cache-first read

- GIVEN a `23505` occurs during upsert
- WHEN the caller next reads the greeting config
- THEN the cache-first read returns the winning row without error

## MODIFIED Requirements

### Requirement: Explicit non-goals for advisor findings

The database layer MUST encode the live `rls_enabled_no_policy` state as an explicit service-role-only contract. All public tables MUST remain RLS-enabled (Cycle 2 completes this by enabling RLS on `guild`, `member`, `infraction`, `ticket`, `ticket_category`, `economy_config`, and `greeting_config`); publishable or authenticated non-service credentials MUST be denied access, while the server-side `service_role` client MAY access required tables. Startup MUST validate that the configured credential is present and service-role-compatible, failing closed otherwise. Advisor findings MAY remain visible as diagnostics, but MUST NOT authorize broader access or replace schema and ownership evidence. This contract changes no DDL beyond the additive `ENABLE ROW LEVEL SECURITY` statements.
(Previously: stated "All nine public tables MUST remain RLS-enabled" but only `ticket_note` and `ticket_audit` actually had RLS; Cycle 2 closes the gap on the remaining seven.)

#### Scenario: Service-role startup validation succeeds

- GIVEN a present credential is verified as `service_role`
- WHEN database startup validation runs
- THEN the database layer becomes available for server-side operations

#### Scenario: Non-service startup fails closed

- GIVEN the credential is missing, unverifiable, or non-service-role
- WHEN database startup validation runs
- THEN startup reports failure and database-dependent commands remain disabled

#### Scenario: Negative non-service access test

- GIVEN an anon, publishable, or authenticated credential
- WHEN it attempts to read any public application table (all now RLS-enabled)
- THEN access is denied and no application rows are exposed

#### Scenario: Advisor findings do not authorize repair

- GIVEN advisor findings remain unresolved
- WHEN ticket-integrity preflight is evaluated
- THEN only verified schema/deployment evidence and fresh Discord evidence determine repair eligibility

## Scope boundary

This delta enables RLS on remaining tables, adds the `AsyncClientOptions`
flags, adds `23505` handling on the greeting upsert, and (in `guards-contracts`)
scopes bot-side `select("*")` to Cycle-2-touched mixins. Economy/infraction
`select("*")` cleanup and all FK/RLS policy authoring are deferred to Cycle 3.
All migrations are additive nullable. Cycle 3 (voice/moderation,
ScheduledAction, has_perm) is OUT OF SCOPE.
