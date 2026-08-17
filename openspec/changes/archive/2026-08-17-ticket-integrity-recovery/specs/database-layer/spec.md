# Delta for Database Layer

## ADDED Requirements

### Requirement: Migration 015 on-disk parity tracking

Migration `015_*` (production-applied) MUST be present and tracked on disk in `migrations/`. The on-disk file MUST be byte-named and schema-matched against the production-applied version before any downstream repair code relies on it. Restoration MUST NOT mark a new migration as applied; it re-establishes parity for a migration production already reports as applied.

The system SHALL verify parity before reliance: filename, declared schema objects, and applied status MUST match production evidence. Until parity is verified, the repair activation gate (G.2) MUST remain unresolved.

#### Scenario: Production-applied migration restored on disk

- GIVEN production reports migration `015_*` as already applied and no `migrations/015_*` file exists on disk
- WHEN migration 015 is restored to `migrations/`
- THEN the file is tracked in git and its content matches the production-applied schema

#### Scenario: Parity checked before reliance

- GIVEN migration 015 was restored on disk
- WHEN the preflight parity check runs
- THEN filename, schema objects, and applied-status match production evidence and the check returns `compatible`

#### Scenario: Parity mismatch blocks reliance

- GIVEN the restored `migrations/015_*` content differs from the production-applied schema
- WHEN the preflight parity check runs
- THEN the check returns `incompatible`, the G.2 gate remains unresolved, and no repair activation is permitted

### Requirement: Deployment/migration preflight evidence (G.2 gate)

Preflight MUST collect deployment and migration compatibility evidence before any automatic repair is activated. Evidence MUST include: migration 015 on-disk/production parity (from the prior requirement), supported Supabase/Postgres deployment mode, and absence of incompatible schema-drift signals. When evidence is missing or incompatible, preflight MUST return `gate_unresolved` and automatic repair MUST stay disabled. This gate is read-only with respect to ticket data — it MUST NOT mutate tickets.

#### Scenario: Evidence present and compatible

- GIVEN migration 015 parity is verified and the deployment mode is supported
- WHEN the G.2 preflight runs
- THEN the gate returns `resolved` and automatic repair activation MAY proceed

#### Scenario: Missing evidence blocks activation

- GIVEN migration 015 parity is unverified
- WHEN the G.2 preflight runs
- THEN the gate returns `gate_unresolved` and automatic repair is disabled

#### Scenario: Incompatible deployment blocks activation

- GIVEN the deployment mode is unsupported or schema-drift is detected
- WHEN the G.2 preflight runs
- THEN the gate returns `gate_unresolved` and automatic repair is disabled

#### Scenario: Preflight does not mutate tickets

- GIVEN any preflight outcome
- WHEN the G.2 preflight runs
- THEN no ticket row is inserted, updated, or deleted by the preflight itself
