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

<!-- BEGIN DELTA: ticket-physical-split S3 -->

### Requirement: Modern secret-key probe is explicit and read-only

The verifier MUST support an opaque `sb_secret_` credential as a server-only mode only after a successful read-only health probe against the RLS-enabled `guild` and `ticket` tables. It MUST NOT decode or describe that key as a JWT. A legacy JWT path MAY remain, but signature verification MUST use PyJWT with an allowlisted algorithm and an explicitly configured signing-key/JWKS source.

#### Scenario: Secret key probe succeeds

- GIVEN a configured `sb_secret_` key can read `guild` and `ticket`
- WHEN the credential gate runs
- THEN the key is accepted for read-only server-side verification

#### Scenario: Secret key probe fails closed

- GIVEN an `sb_secret_` key is missing, rejected, or cannot read either table
- WHEN the credential gate runs
- THEN live verification is unresolved and no DDL or application mutation occurs

#### Scenario: Legacy JWT remains a separate path

- GIVEN a legacy JWT credential is supplied
- WHEN its role is verified
- THEN PyJWT/JWKS signature verification is used rather than payload decoding alone

### Requirement: Catalog-backed parity evidence

The verifier MUST obtain catalog evidence through a read-only database or staging RPC path, not assume PostgREST exposes system catalogs. It MUST compare live and local migration history (19 live entries versus 17 local files), approved foreign keys, RLS parity `(9/7/0)` for enabled/forced/policy counts, and four Realtime publication tables. Missing, stale, or mismatched evidence MUST remain unresolved.

#### Scenario: Catalog parity is measurable

- GIVEN the staging catalog path returns the accepted live facts
- WHEN parity is evaluated
- THEN the verifier records the named counts and migration reconciliation without applying SQL changes

#### Scenario: PostgREST catalog gap fails closed

- GIVEN system catalogs are unavailable through the ordinary API schema cache
- WHEN the verifier cannot obtain an approved catalog source
- THEN it reports unresolved parity rather than claiming success from a health probe

#### Scenario: Migration drift is surfaced

- GIVEN remote and local migration ledgers differ or an FK action is incompatible
- WHEN parity is evaluated
- THEN the result identifies drift and blocks DDL/repair activation

<!-- END DELTA: ticket-physical-split S3 -->

