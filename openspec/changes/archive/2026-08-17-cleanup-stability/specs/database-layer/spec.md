# Delta for database-layer

## MODIFIED Requirements

### Requirement: Explicit non-goals for advisor findings

The database layer MUST encode the live `rls_enabled_no_policy` state as an explicit service-role-only contract for S1. All nine public tables MUST remain RLS-enabled; publishable or authenticated non-service credentials MUST be denied access, while the server-side `service_role` client MAY access required tables. Startup MUST validate that the configured credential is present and service-role-compatible, failing closed otherwise. Advisor findings MAY remain visible as diagnostics, but MUST NOT authorize broader access or replace schema and ownership evidence. This contract changes no DDL.

(Previously: RLS no-policy and leaked-password advisor findings were explicitly out of scope.)

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
- WHEN it attempts to read any public application table
- THEN access is denied and no application rows are exposed

#### Scenario: Advisor findings do not authorize repair

- GIVEN advisor findings remain unresolved
- WHEN ticket-integrity preflight is evaluated
- THEN only verified schema/deployment evidence and fresh Discord evidence determine repair eligibility

## ADDED Requirements

### Requirement: Read-only schema and FK retention inventory

S1 MUST inventory live and on-disk schema state before any schema change. The retained contract is `ticket_note` `ON DELETE CASCADE` and `ticket_audit` `ON DELETE SET NULL`; the inventory MUST record whether each live and disk definition matches. Migration `015_*` filename, objects, and applied status MUST be compared before any future DDL is considered. This change MUST apply no DDL.

#### Scenario: Inventory records matching state

- GIVEN live metadata, migration history, disk files, and migration 015 are available
- WHEN the read-only inventory runs
- THEN FK actions and 015 parity are reported without changing the database

#### Scenario: Drift blocks schema work

- GIVEN live and disk FK actions or migration 015 parity differ
- WHEN the inventory evaluates the state
- THEN it reports unresolved drift and no DDL is created or applied

### Requirement: Guild-scoped database boundary inventory

The database layer MUST inventory and contract guild ownership for ID-only or channel-only paths, including ticket, parent-ticket, category, note, and audit operations. A read or mutation MUST establish `guild_id` ownership before returning or changing a row; S1 MAY record an uncovered path, but MUST NOT hide it with a service-only assumption or split `TicketService`.

#### Scenario: Cross-guild access is denied

- GIVEN equivalent identifiers exist in guilds A and B
- WHEN a guild A request targets the identifier
- THEN only guild A data is eligible and guild B data is neither returned nor mutated

#### Scenario: Unscoped path is reported

- GIVEN an inventory finds an ID-only database method
- WHEN the S1 contract check runs
- THEN the method is recorded as a scoping gap for remediation and the check does not claim full guild isolation
