# Delta for live-schema-verifier

## MODIFIED Requirements

### Requirement: Modern secret-key probe is explicit and read-only

The verifier MUST accept `sb_secret_` credentials only after sequential read-only probes of `guild` and `ticket`; it MUST NOT decode them as JWTs. JWT verification MUST follow this contract:

| Credential | Algorithm | Key source | Claims |
|------------|-----------|------------|--------|
| `sb_secret_` | n/a (opaque) | RLS health probes | n/a |
| Legacy service JWT | `HS256` | configured secret | `role`,`iss`,`aud`,`exp` |
| JWKS JWT | `["RS256","ES256"]` | `PyJWKClient` `jwks_uri`, `kid`-bound | `role`,`iss`,`aud`,`exp` |

The live JWKS ships an ES256 EC P-256 key; RS256-only is invalid. An unknown `kid` MAY trigger one bounded refresh; unresolved keys MUST fail without fallback. Algorithm confusion MUST be rejected.
(Previously: RS256-only allowlist; live ES256 key would never verify.)

#### Scenario: Secret key probe succeeds

- GIVEN both `guild` and `ticket` probes succeed
- WHEN the credential gate runs
- THEN the opaque key is accepted for read-only verification

#### Scenario: Secret key probe fails closed

- GIVEN either probe fails
- WHEN the credential gate runs
- THEN verification is unresolved and no mutation occurs

#### Scenario: ES256 live key verifies

- GIVEN the live JWKS endpoint returns an ES256 EC P-256 key with a known `kid`
- WHEN a legacy ES256 JWT is verified
- THEN PyJWKClient selects the key by `kid` and verification succeeds with required claims enforced

#### Scenario: RS256 rotation is bounded

- GIVEN a token has an unknown `kid` after lookup
- WHEN verification runs
- THEN one JWKS refresh may find the key; otherwise it fails without fallback

#### Scenario: Algorithm confusion rejected

- GIVEN a token presents an algorithm not in `["RS256","ES256"]` or lacks a required claim
- WHEN verification runs
- THEN it is rejected without HS256 or payload-only fallback

#### Scenario: Legacy JWT remains separate

- GIVEN a service-role JWT uses the configured secret and HS256
- WHEN verification runs
- THEN PyJWT accepts it only after HS256 signature and claim validation

### Requirement: Catalog-backed parity evidence

The verifier MUST use a direct read-only staging Postgres connection (`psycopg`/`DB_URL`) for acceptance, never PostgREST system-catalog reads (`PGRST205`). Catalog queries MUST scope `pg_policy` and `pg_constraint` to the `public` namespace via `JOIN pg_class`/`pg_namespace WHERE n.nspname='public'` — unscoped queries return cross-schema rows (`pg_cron` policies, `auth`/`storage` FKs) that falsely fail the 9/7/0 and six-guild-CASCADE bindings. It MUST reconcile 19 local files to 19 remote migrations by version/name; count equality alone MUST NOT pass. The three documented historical desync names MUST be reconciled via `supabase migration repair --status applied` — NOT via a drift-acceptance allowlist and NOT via an untracked `psql`/SQL-editor bypass. Mismatched evidence MUST remain unresolved.
(Previously: direct DB path required, but query scoping and tracked repair unspecified; unscoped queries accidentally passed.)

#### Scenario: Direct scoped catalog parity succeeds

- GIVEN direct `psycopg` queries scoped to `public` return 9/7/0, six guild-CASCADE FKs, four CDC tables, 19 reconciled identities
- WHEN evaluated
- THEN 9/7/0, six FK shapes, four publications, and 19↔19 identity are recorded without DDL

#### Scenario: Unscoped query is rejected

- GIVEN a catalog query omits the `public` namespace filter and returns cross-schema rows
- WHEN parity is evaluated
- THEN the result is unresolved and the gate reports an unscoped-catalog reason

#### Scenario: `PGRST205` fails closed

- GIVEN PostgREST cannot expose system catalogs and no approved `psycopg` source exists
- WHEN parity runs
- THEN it remains unresolved rather than using a health probe as proof

#### Scenario: Migration drift blocks acceptance

- GIVEN a remote version/name is missing or unmapped after `repair --status applied`
- WHEN reconciliation runs
- THEN drift is reported and live acceptance is blocked

#### Scenario: Untracked psql bypass is rejected

- GIVEN 018 or any migration is applied via raw `psql` without a ledger insert or `repair --status applied`
- WHEN reconciliation runs
- THEN the migration is untracked and live acceptance is blocked

## ADDED Requirements

### Requirement: Provenance token binds real psycopg evidence

The verifier MUST exercise the four-query provenance binding against a real `psycopg` connection and record the receipts. A mocked `ProvenanceToken(query_count==4)` synthetic path (`1p3s`) MUST NOT close acceptance — it MAY run in the default suite but MUST NOT produce a `PASS` verdict. The real receipt MUST bind 9/7/0, six named CASCADE FKs, four publication tables, and 19 reconciled migrations to the live `DB_URL` execution.

#### Scenario: Real psycopg binds four queries

- GIVEN `LIVE_SUPABASE=1` and a real `DB_URL` are present
- WHEN the provenance binding runs against staging
- THEN exactly four read-only queries execute and the receipt records their live results

#### Scenario: Synthetic path cannot close acceptance

- GIVEN only mocked evidence is available (no real `DB_URL`)
- WHEN S5 acceptance is requested
- THEN the gate fails with a missing-live-receipt reason and MUST NOT report `PASS`

#### Scenario: Provenance query count is bounded

- GIVEN the provenance binding runs against a real connection
- WHEN the queries execute
- THEN exactly four queries are issued — no ad-hoc fifth query MAY inflate the binding
