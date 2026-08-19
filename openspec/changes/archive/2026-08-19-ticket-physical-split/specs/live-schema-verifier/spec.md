# Delta for Live Schema Verifier

## ADDED Requirements

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
