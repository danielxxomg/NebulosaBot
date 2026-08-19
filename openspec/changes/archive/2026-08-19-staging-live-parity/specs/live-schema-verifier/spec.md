# Delta for Live Schema Verifier

## MODIFIED Requirements

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
