# Live Schema Verifier Specification

## Purpose

Define a credential-gated, read-only binder that connects live Supabase metadata to `SchemaInventory` without applying DDL.

## Requirements

### Requirement: Read-only live parity binder

The verifier MUST bind mocked or explicitly supplied live evidence for RLS, policies, foreign keys, Realtime publication, indexes, and migration IDs into a typed `SchemaInventory`. It MUST report unresolved or incompatible parity instead of inferring compatibility, and MUST issue no INSERT, UPDATE, DELETE, CREATE, ALTER, or DROP operation.

#### Scenario: Mocked baseline binds

- GIVEN mocked metadata representing the accepted live baseline
- WHEN the binder builds `SchemaInventory`
- THEN the inventory is deterministic, typed, and marked resolved only when every required fact matches

#### Scenario: Drift fails closed

- GIVEN a missing, stale, or mismatched live fact
- WHEN parity is evaluated
- THEN the inventory is unresolved with a reason and no schema or ticket mutation occurs

### Requirement: Accepted live evidence is measurable

The inventory MUST expose evidence for nine RLS-enabled tables with zero policies, six child-to-guild foreign keys using `ON DELETE CASCADE`, four CDC publication tables, 19 live migration entries, and the 12 on-disk `GUILD_SCOPE_GAPS` names. It MUST distinguish observed facts from S2 code enforcement and future DDL.

#### Scenario: Baseline counts match

- GIVEN the mocked evidence contains 9 zero-policy RLS tables, 6 guild CASCADE FKs, 4 CDC tables, 19 migrations, and 12 scope gaps
- WHEN the inventory is asserted
- THEN each count and named set matches without a corrective SQL statement

#### Scenario: RLS role semantics remain explicit

- GIVEN a listed table has RLS enabled and no policy
- WHEN access is evaluated for `anon` or `publishable` versus `service_role`
- THEN non-service access is denied and service-role access is treated as server-side only

### Requirement: Opt-in live integration marker

Live Supabase verification MUST run only behind an explicit integration marker and credential gate. The default mocked test suite MUST remain runnable without live credentials; missing credentials MUST skip the live test rather than fail unrelated tests.

#### Scenario: Default suite is credential-independent

- GIVEN live credentials are absent
- WHEN the default `uv run pytest` suite runs
- THEN mocked verifier tests execute and live tests are skipped

#### Scenario: Opt-in check is read-only

- GIVEN valid opt-in Supabase credentials
- WHEN the live marker is selected
- THEN the verifier reads metadata, compares the expected evidence, and performs no DDL
