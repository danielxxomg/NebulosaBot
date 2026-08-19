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

The inventory MUST expose 9 enabled RLS tables, 7 forced tables, 0 policies, six child-to-guild `CASCADE` FKs (`economy_config`, `greeting_config`, `infraction`, `member`, `ticket`, `ticket_category`), four CDC tables (`guild`, `greeting_config`, `ticket`, `ticket_note`), and 19 reconciled migration identities. The 12 names MUST be `GUILD_SCOPE_GAP_HISTORY`, historical rather than unresolved.
(Previously: count-only ledger.)

#### Scenario: Baseline counts match

- GIVEN catalog evidence contains 9/7/0, six named FKs, four CDC tables, and 19 identities
- WHEN evaluated
- THEN sets match without SQL

#### Scenario: RLS semantics remain explicit

- GIVEN a listed table has RLS and no policy
- WHEN `anon` and `service_role` access are evaluated
- THEN anon is denied and service stays server-side

### Requirement: Opt-in live integration marker

Live acceptance MUST require `LIVE_SUPABASE=1` and real staging credentials, including `DB_URL` and Supabase/JWKS credentials. Mocks MAY support the default suite but MUST NOT produce S4 PASS. Missing marker or credentials MUST fail acceptance with a gate reason, not substitute a fake client.
(Previously: skips hid acceptance failure.)

#### Scenario: Default suite remains independent

- GIVEN live credentials are absent
- WHEN the default suite runs
- THEN mocks may run, but live coverage is unavailable

#### Scenario: Real opt-in is read-only

- GIVEN the marker and valid credentials are present
- WHEN acceptance runs
- THEN real health and catalog evidence are compared without mutation

#### Scenario: Missing credentials fail acceptance

- GIVEN `LIVE_SUPABASE=1` is requested without required credentials
- WHEN S4 acceptance runs
- THEN it fails clearly and cannot report `PASS_WITH_WARNINGS`

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

<!-- BEGIN DELTA: staging-live-parity S4 -->

### Requirement: Modern secret-key probe is explicit and read-only

The verifier MUST accept `sb_secret_` credentials only after sequential read-only probes of `guild` and `ticket`; it MUST NOT decode them as JWTs. Legacy JWTs MUST retain `algorithms=["HS256"]`. RS256 JWTs MUST use `PyJWKClient` with `jwks_uri`, `algorithms=["RS256"]`, and required `role`, `iss`, `aud`, and `exp`. An unknown `kid` MAY trigger one bounded refresh; unresolved keys or algorithms MUST fail closed.
(Previously: no RS256 rotation.)

#### Scenario: Secret key probe succeeds

- GIVEN both probes succeed
- WHEN the credential gate runs
- THEN the key is accepted for read-only verification

#### Scenario: Secret key probe fails closed

- GIVEN either probe fails
- WHEN the credential gate runs
- THEN verification is unresolved and no mutation occurs

#### Scenario: RS256 rotation is bounded

- GIVEN a token has an unknown `kid` after lookup
- WHEN verification runs
- THEN one JWKS refresh may find the key; otherwise verification fails without fallback

#### Scenario: Claims and algorithm confusion are rejected

- GIVEN a token lacks a required claim or presents a disallowed algorithm
- WHEN verification runs
- THEN it is rejected without HS256 or payload-only fallback

#### Scenario: Legacy JWT remains a separate path

- GIVEN a service-role JWT uses the configured secret and HS256
- WHEN verification runs
- THEN PyJWT accepts it only after HS256 signature and claim validation

### Requirement: Catalog-backed parity evidence

The verifier MUST use a direct read-only staging Postgres connection (`psql`/`DB_URL`) for acceptance, never PostgREST system-catalog reads. It MUST reconcile 19 local files to 19 remote migrations by version/name, aliases explicit; count equality alone MUST NOT pass. Missing or mismatched evidence MUST remain unresolved.
(Previously: future DB/RPC path.)

#### Scenario: Direct catalog parity succeeds

- GIVEN direct queries return accepted RLS, FK, publication, and migration facts
- WHEN evaluated
- THEN 9/7/0, six FK shapes, four publications, and 19↔19 identity are recorded without DDL

#### Scenario: `PGRST205` fails closed

- GIVEN PostgREST cannot expose system catalogs and no approved source exists
- WHEN parity runs
- THEN it remains unresolved rather than using a health probe as proof

#### Scenario: Migration drift blocks acceptance

- GIVEN a remote version/name is missing or unmapped
- WHEN reconciliation runs
- THEN drift is reported and live acceptance is blocked

### Requirement: Opt-in live integration marker

Live acceptance MUST require `LIVE_SUPABASE=1` and real staging credentials, including `DB_URL` and Supabase/JWKS credentials. Mocks MAY support the default suite but MUST NOT produce S4 PASS. Missing marker or credentials MUST fail acceptance with a gate reason, not substitute a fake client.
(Previously: skips hid acceptance failure.)

#### Scenario: Default suite remains independent

- GIVEN live credentials are absent
- WHEN the default suite runs
- THEN mocks may run, but live coverage is unavailable

#### Scenario: Real opt-in is read-only

- GIVEN the marker and valid credentials are present
- WHEN acceptance runs
- THEN real health and catalog evidence are compared without mutation

#### Scenario: Missing credentials fail acceptance

- GIVEN `LIVE_SUPABASE=1` is requested without required credentials
- WHEN S4 acceptance runs
- THEN it fails clearly and cannot report `PASS_WITH_WARNINGS`

<!-- END DELTA: staging-live-parity S4 -->
