## Exploration: production-live-close — S5

### Intent

Close S4 `PASS_WITH_WARNINGS` by executing the **real staging**
acceptance gate against `vozkcckiybebhcclrasa` (Supabase project
`nebulosabot`, `sa-east-1`, PostgreSQL 17.6.1.155, `ACTIVE_HEALTHY`).
S4 proved provenance plumbing with a mocked `psycopg.connect`
(`ProvenanceToken(query_count==4)` + `RlsCounts(9,7,0)` binding); S5
must exercise the same gate against a real Postgres connection and
record the receipts. This exploration runs read-only checks only — no
DDL, no 018 apply, no mutation — and surfaces three previously-hidden
correctness issues that only real DB access can reveal.

### Current State

#### Baseline (confirmed this session)

| Check | Result | Note |
|---|---|---|
| `git rev-parse --show-toplevel` | `/home/danielxxomg/Projects/NebulosaBot` | repo root |
| `git log --oneline -1` | `895bb8f chore(sdd): archive staging-live-parity 17/17 — S4 PASS_WITH_WARNINGS, 4 deltas synced` | S4 archived at master |
| `uv run mypy bot tests` | `Success: no issues found in 180 source files` | hard gate green |
| `uv run ruff check bot tests scripts` | `All checks passed!` | hard gate green |
| `uv run pytest -q` | `2070 passed, 7 skipped in 16.14s` — 87.84% coverage | baseline green |
| `uv run pytest -m live --run-live --no-cov -q` | `1 passed, 3 skipped, 2073 deselected` | S4 `PASS_WITH_WARNINGS` synthetic path confirmed |
| Local migrations | 19 SQL files in `migrations/` | `001..018` + `003_subtickets_notes` + `005_rls_secure_default` stub |
| `.codegraph/` | present, auto-sync daemon running | CodeGraph available |
| Supabase CLI | `/usr/bin/supabase` v2.114.0 | **installed locally** — enables tracked `migration up --linked` |
| `supabase/` config dir | absent | no `config.toml`; `migrations/` is NOT CLI-linked yet |
| `.env` | `DISCORD_TOKEN`, `SUPABASE_URL=https://vozkcckiybebhcclrasa.supabase.co`, `SUPABASE_KEY=sb_secret_…` (opaque, 41 chars, 0 dots) | no `DB_URL`, no `LIVE_SUPABASE`, no `JWKS_URL` |

#### Live read-only catalog evidence (collected this session via Supabase MCP `execute_sql`)

| Fact | Live value | S4 expectation | Match? |
|---|---|---|---|
| `rls_enabled` (public, `relrowsecurity`) | **9** | 9 | ✅ |
| `rls_forced` (public, `relforcerowsecurity`) | **7** | 7 | ✅ |
| `policy_count` (`SELECT count(*) FROM pg_policy` unscoped) | **2** | 0 | ❌ **see Issue A** |
| `policy_count` (scoped to `public` schema) | **0** | 0 | ✅ (correct scope) |
| FK count (`pg_constraint WHERE contype='f'` unscoped) | **29** | 6 guild CASCADE | ⚠️ see Issue B |
| FK count where `parent=guild` (public) | **6** CASCADE children (`economy_config`, `greeting_config`, `infraction`, `member`, `ticket`, `ticket_category`) | 6 | ✅ |
| Publication tables (`supabase_realtime`) | **4**: `greeting_config`, `guild`, `ticket`, `ticket_note` | 4 | ✅ |
| Migration ledger count | **19** | 19 | ✅ (count) |
| 018 applied? | **No** — 19 rows, none named `018_*` | not applied | ✅ expected |
| 017 `repaired` outcome CHECK live? | **Yes** — `outcome IN ('success','denied','error','repaired')` | live | ✅ (but 017 migration name absent from ledger — see Issue C) |

#### 018 preflight conditions (live, read-only)

All match S4 documented facts exactly:

| Preflight check | Live value | S4 expected | Pass? |
|---|---|---|---|
| Duplicate active slot | 0 | 0 | ✅ |
| Duplicate active channel | 0 | 0 | ✅ |
| Duplicate guild ticketNumber | 0 | 0 | ✅ |
| Invalid UUID categoryId | 0 | 0 | ✅ |
| Orphan category (UUID without matching `ticket_category.id`) | 0 | 0 | ✅ |
| Missing parent | 0 | 0 | ✅ |
| Parent depth violation (>1 level) | 0 | 0 | ✅ |
| Note orphans | 0 | 0 | ✅ |
| Audit orphans | **1** | 1 (approved retention) | ✅ |
| Audit guild mismatch | **1** | 1 (approved retention) | ✅ |
| Total tickets | **21** | 21 | ✅ |
| Active tickets | **5** | 5 | ✅ |

**Conclusion**: migration 018 preflight passes live — it is safe to
apply when the window opens.

#### Index scan evidence (live, `pg_stat_user_indexes`)

| Index | `idx_scan` | Size | Verdict |
|---|---|---|---|
| `idx_ticket_guild_number` | **0** | 16 kB | shadowed duplicate — drop candidate (EXPLAIN required) |
| `idx_ticket_active_slot` | 0 | 16 kB | partial unique; 0 scans expected (new) |
| `idx_ticket_guild_status` | 0 | 16 kB | keep (S4 design — no DROP) |
| `idx_ticket_channel` | 1 | 16 kB | keep (closed lookups) |
| `ticket_pkey` | 1 | 16 kB | keep |
| `idx_ticket_parent` | 3 | 16 kB | keep (parent FK lookup) |
| `idx_ticket_active_channel` | 11 | 16 kB | keep (zombie detection) |
| `idx_ticket_guild_ticket_number` | 11 | 16 kB | keep (unique invariant) |

`idx_ticket_guild_number` has 0 scans and is shadowed by the unique
`idx_ticket_guild_ticket_number` — the only approved DROP.

#### EXPLAIN (ANALYZE, BUFFERS) capability — PROVEN live

Test query `EXPLAIN (ANALYZE, BUFFERS) SELECT count(*) FROM public.ticket WHERE "guildId"='…' AND "ticketNumber"=…` executed via `execute_sql` and returned a full plan with `Index Only Scan using idx_ticket_guild_ticket_number`, `Heap Fetches: 0`, `Buffers: shared hit=1`, `Planning Time: 1.311 ms`, `Execution Time: 1.116 ms`.

**EXPLAIN gating works through the staging SQL API** — the receipt
can be captured without raw `psql` access.

#### JWKS endpoint — CRITICAL DISCOVERY

`GET https://vozkcckiybebhcclrasa.supabase.co/auth/v1/.well-known/jwks.json` → `HTTP 200`, 240 bytes:

```json
{"keys":[{"alg":"ES256","crv":"P-256","ext":true,"key_ops":["verify"],
"kid":"96e9b570-98ae-4f97-a13f-7f3c3bbda017","kty":"EC","use":"sig",
"x":"…","y":"…"}]}
```

The live staging project uses an **ES256 (EC P-256)** signing key —
NOT RS256. Supabase Auth's `GOTRUE_JWT_KEYS` supports any JWK type
(RSA/EC/OKP); modern projects ship with ES256. The S4
`_verify_jwt_rs256` implementation hard-codes
`algorithms=["RS256"]` and explicitly rejects
`header.get("alg") != "RS256"` — so it would **never succeed** against
this project's actual JWKS. See Issue D.

#### Credential posture

The current `SUPABASE_KEY` is an opaque `sb_secret_…` token (41 chars,
no dots — not a JWT). Per `validate_supabase_key`, the modern
`sb_secret_` prefix bypasses JWT verification and is proven via
`health_check` RLS probes. Therefore **the RS256/JWKS path only matters
for legacy JWT keys**, not the staging service_role key — but the code
is still dead-wrong for any future JWT that uses the live ES256 key.

### Issues Found (only visible with real DB access)

#### Issue A — `fetch_rls_counts_via_db` policy_count query is unscoped (BLOCKER)

`bot/services/live_catalog.py:311-316`:

```python
try:
    cur.execute("SELECT count(*) FROM pg_policy")
    row3 = cur.fetchone()
except Exception:
    cur.execute("SELECT count(*) FROM pg_policies")
    row3 = cur.fetchone()
```

`pg_policy` is a **global** catalog — it includes `cron.job` and
`cron.job_run_details` policies (2 rows live, from `pg_cron`
extension). A real `psycopg` call returns `policy_count=2`, producing
`RlsCounts(9, 7, 2)` which **fails** the 9/7/0 binding
(`rls_970_mismatch`). The mock tests pass because they inject
`RlsCounts(9,7,0)` directly; they never exercise the unscoped query.

**Fix**: scope the count to the `public` namespace:

```sql
SELECT count(*) FROM pg_policy p
  JOIN pg_class c ON c.oid = p.polrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
```

Confirmed live: scoped query returns `0`. This is the single most
important S5 fix — without it, the real-DB gate fails before any other
evidence is considered.

#### Issue B — `_sync_fetch_catalog` FK query is unscoped (latent, currently masked)

`bot/services/live_catalog.py:177-186`:

```python
cur.execute(
    "SELECT conrelid::regclass::text AS child, "
    "confrelid::regclass::text AS parent, "
    "CASE confdeltype ... END AS on_delete "
    "FROM pg_constraint WHERE contype='f'"
)
```

This returns **all 29 FKs** across `auth.*`, `storage.*`, and
`public.*` schemas. The downstream `bind_live_evidence` filter
`r.get("parent") == "guild"` (schema_inventory.py:382) happens to
mask the drift because `auth.users`/`storage.buckets` parents never
equal the string `"guild"`. So the 6-guild-CASCADE check passes
accidentally. But `fk_count` (29) ≠ 6, and any future check that
counts `live_fks` without the parent filter would fail.

**Fix**: scope the FK query to `public`:

```sql
... FROM pg_constraint c
  JOIN pg_class cc ON cc.oid = c.conrelid
  JOIN pg_namespace n ON n.oid = cc.relnamespace
WHERE c.contype='f' AND n.nspname='public'
```

Confirmed live: scoped FKs = exactly 6 guild-CASCADE children. This
makes the evidence truthful rather than accidentally-correct.

#### Issue C — Migration identity mismatch (BLOCKER for `with_remote_names`)

Local 19 stems ≠ remote 19 names:

| In local, not remote (3) | In remote, not local (3) |
|---|---|
| `016_greeting_onboarding_channel` | `greeting_onboarding_channel` |
| `017_ticket_audit_repaired_outcome` | `add_tables_to_realtime_publication` |
| `018_ticket_integrity_fks` | `add_realtime_publication_tables` |

The remote ledger was populated by `supabase db push` / Studio editor
using **non-version-prefixed** names for two Realtime publication
migrations and the greeting onboarding column. The local files use
the repo's `NNN_` naming. The 017 `repaired` outcome constraint IS
live (verified: `outcome IN ('success','denied','error','repaired')`),
but the migration was applied outside the tracked ledger (SQL editor)
and the 017 filename never made it into `schema_migrations`.

`LiveAcceptanceGate.with_remote_names` does a strict
`set(remote_names) != set(local)` set-equality check
(live_catalog.py:153). A real-DB run would append
`migration_identity_mismatch` to `reasons` and the gate would FAIL —
correctly, but in a way S4 never saw because mocked tests supplied a
matching `fake_19` list.

**Resolution options** (product question): (a) accept the documented
3-name drift as historical and relax the identity check to a
documented allowlist, or (b) run `supabase migration repair` to mark
the 3 remote-only names as applied so the ledger reconciles. Option
(b) is the Supabase-supported path and matches the S4 proposal's
"tracked migrations" contract.

#### Issue D — JWKS path is RS256-only but live project uses ES256 (BLOCKER for JWT verification)

`bot/config.py:87`:

```python
if header.get("alg") != "RS256":
    return None
```

and `config.py:105`:

```python
algorithms = (["RS256"],)
```

The live JWKS endpoint returns an **ES256 EC P-256** key. Any legacy
JWT signed by Supabase Auth for this project would carry
`"alg":"ES256"` and be rejected. The S4 verify-report claims
`RS256 one-refresh (2 total)` as compliant — it is compliant with the
S4 spec text, but the spec was written before confirming the live
algorithm.

**Resolution options** (product question): (a) extend the verifier to
accept `["RS256", "ES256"]` and use `PyJWKClient` key-type-agnostic
selection (the client already handles EC keys), or (b) keep RS256-only
and document that the JWKS path is inert for this project (the
`sb_secret_` opaque path is the live credential). Option (a) is more
correct and future-proof; option (b) is smaller but leaves dead code.

#### Issue E — 018 apply via raw `psql` would desync the migration ledger (BLOCKER for live 018)

`scripts/apply_staging_migration.py` runs `psql -f 018_ticket_integrity_fks.sql`
directly. The 018 SQL file does **not** `INSERT INTO
supabase_migrations.schema_migrations`. Applying it via `psql` would
execute the DDL but leave the ledger showing 19 rows (018 untracked) —
exactly the "untracked SQL-editor drift" S4's proposal explicitly
forbade (§Rollback Plan: "No untracked `execute_sql`").

**Resolution options**:
1. **Use `supabase migration up --linked` (or `--db-url`)** after
   moving/copying `migrations/018_ticket_integrity_fks.sql` into a
   `supabase/migrations/` directory and running `supabase link`. The
   CLI inserts into `schema_migrations` automatically. Requires a
   one-time `supabase/` config setup.
2. **Keep `psql` but add an explicit ledger insert** in the 018 SQL
   file (`INSERT INTO supabase_migrations.schema_migrations (version,
   name, statements) VALUES (...)`). Less clean; bypasses CLI repair
   tooling.
3. **Apply via `psql` then run `supabase migration repair
   --status applied`** to mark 018 as applied retroactively. Hybrid
   approach.

Option 1 is the Supabase-sanctioned path and matches the S4 proposal's
"tracked migrations only" contract. It requires creating a
`supabase/config.toml` and `supabase/migrations/` symlink/copy — a
small one-time setup that belongs in S5.

### Affected Areas

- `bot/services/live_catalog.py` — `fetch_rls_counts_via_db` (Issue A:
  scope `pg_policy` to `public`); `_sync_fetch_catalog` (Issue B:
  scope `pg_constraint` to `public`); `evaluate_index_policy` (no
  change — EXPLAIN gating proven executable)
- `bot/config.py` — `_verify_jwt_rs256` (Issue D: extend algorithm
  allowlist to `["RS256", "ES256"]` or rename to `_verify_jwt_jwks`)
- `scripts/apply_staging_migration.py` — Issue E: replace/augment
  `psql` path with `supabase migration up --linked` or add ledger
  insert + `migration repair`
- `migrations/018_ticket_integrity_fks.sql` — no structural change;
  preflight proven safe. May need a companion ledger-insert step.
- `supabase/config.toml`, `supabase/migrations/` — **new** one-time
  CLI linkage setup (if Option 1 chosen for Issue E)
- `tests/test_live_catalog.py` — add a real-DB marker test gated on
  `LIVE_SUPABASE=1` + real `DB_URL`; mock tests must assert the
  scoped queries (regression guard for Issues A/B)
- `tests/test_jwks_verifier.py` — add ES256 case if algorithm
  allowlist extended (Issue D)
- `openspec/changes/2026-08-19-staging-live-parity/verify-report.md` —
  S5 updates the verdict from `pass_with_warnings` to `pass` once
  real-DB receipts are recorded

### Approaches

1. **Single-PR real-DB execution + 4 fixes + docs (recommended)** —
   Fix Issues A/B/D (scoped catalog queries + ES256 allowlist), set up
   `supabase/` CLI linkage (Issue E), run the real live gate against
   staging, capture receipts, update verify-report. 018 apply is a
   separate gated step inside the same PR but behind a manual
   confirmation gate.
   - Pros: closes S4 in one coherent unit; receipts recorded
     alongside the fixes that make them possible; reviewer sees the
     full "mocked → real" transition in one diff
   - Cons: touches 4 distinct concerns; if 018 apply window is not
     available this week, the PR must split
   - Effort: Medium. ~350-500 authored lines (fixes + tests + docs);
     018 apply is execution, not code

2. **Two stacked PRs: code-fixes then live-execution** — PR1 fixes
   Issues A/B/D + scoped-query tests + ES256 tests (code-only,
   ~300 lines). PR2 sets up `supabase/` CLI, runs real gate, records
   receipts, updates verify-report (~200 lines).
   - Pros: PR1 is fully testable without creds; PR2 is evidence-only
   - Cons: PR1's fixes are unproven until PR2 runs the real gate; if
     PR2 reveals another issue, PR1 is already merged
   - Effort: Medium. Same total as Approach 1, split across two
     review windows

3. **Three PRs matching S4's S4.1/S4.2A/S4.2B structure** — PR1
   catalog-scope fixes, PR2 JWKS ES256 + migration identity, PR3
   018 apply + CLI setup + receipts.
   - Pros: finest-grained review
   - Cons: over-engineered for the actual diff size; S4's structure
     existed because each slice had distinct code — S5's fixes are
     tightly coupled (the real gate only passes when ALL four issues
     are resolved)
   - Effort: Medium-High due to coordination overhead

### Recommendation

**Approach 1 (single PR ≤800 lines)** — the four issues are
inseparable: the real-DB gate only passes when Issues A+B are fixed
(scoped queries), Issue C is resolved (migration repair or documented
allowlist), and Issue D is decided (ES256 allowlist or inert-path
documentation). Issue E (018 apply) is the one piece that can be
deferred if the apply window is not available this week, but the
**real-DB catalog receipts** (Issues A+B+C+D) must land to close S4.

Concrete plan:

1. **Fix Issue A** — scope `fetch_rls_counts_via_db` `pg_policy`
   query to `public` schema (3-line SQL change + 1 regression test
   asserting the scoped query is used)
2. **Fix Issue B** — scope `_sync_fetch_catalog` FK query to `public`
   schema (4-line SQL change + 1 regression test)
3. **Resolve Issue C** — run `supabase migration repair --status
   applied` for the 3 remote-only names (`add_tables_to_realtime…`,
   `add_realtime…`, `greeting_onboarding_channel`) so the ledger
   reconciles to local stems; OR document a 3-name allowlist in
   `LiveAcceptanceGate` and relax the identity check. Prefer repair
   (tracked) over allowlist (drift-acceptance)
4. **Resolve Issue D** — extend `_verify_jwt_rs256` algorithm
   allowlist to `["RS256", "ES256"]` and rename to
   `_verify_jwt_jwks`; add ES256 test case; live JWKS proven
   reachable (HTTP 200, `kid` present)
5. **Resolve Issue E (if window available)** — create
   `supabase/config.toml` + `supabase/migrations/` symlink to
   `../migrations/`; run `supabase link`; run `supabase migration up
   --linked` for 018; capture pre/post catalog receipts. If window
   unavailable, record catalog receipts only and leave 018 as a
   documented deferred step (S5.1 follow-up)
6. **Real-DB live test** — add `tests/test_live_catalog.py::
   test_real_db_catalog_parity` gated on `LIVE_SUPABASE=1` + real
   `DB_URL`; asserts `RlsCounts(9,7,0)`, 6 guild CASCADE FKs, 4
   publication tables, 19 reconciled migrations, `ProvenanceToken(4)`
7. **Update verify-report** — change S4 verdict from
   `pass_with_warnings` to `pass`; record real-DB command + output
   hash; attach EXPLAIN receipt for `idx_ticket_guild_number` drop
   justification

**Estimated diff**: ~400-550 authored lines (SQL fixes ~15, tests
~150, JWKS ~30, CLI setup ~20, verify-report + docs ~150, real-DB
test ~50). Well under the 800-line budget.

### Risks

- **Credential window closure** — the staging `sb_secret_` + DB_URL
  access may be revoked before S5 completes. Mitigation: capture all
  read-only receipts first (catalog, EXPLAIN, JWKS) in one session;
  018 apply is the only mutation and can be the last step
- **`supabase migration repair` is destructive to the ledger** —
  marking remote-only names as "applied" when the local file doesn't
  match could mask future drift. Mitigation: only repair the 3
  documented historical names; add a test asserting the reconciled
  identity set
- **ES256 allowlist broadens the attack surface** — accepting EC keys
  means a compromised JWKS endpoint could serve a malicious EC key.
  Mitigation: keep `iss`/`aud`/`exp`/`role` required; do not relax
  claim requirements; `PyJWKClient` key selection is `kid`-bound
- **018 apply failure mid-migration** — `VALIDATE CONSTRAINT` takes
  `SHARE UPDATE EXCLUSIVE` lock; if a long transaction holds a
  conflicting lock, the migration aborts at step 4-7. Mitigation:
  `SET lock_timeout='5s'` (already in 018); `ON_ERROR_STOP=1`;
  backup table `ticket_backup_categoryid_text_20260818` retained;
  documented DOWN section restores TEXT
- **Migration identity check relaxation vs strictness** — if the
  product owner prefers strict set-equality, the 3 remote-only names
  must be repaired (Option 1 for Issue C). If they prefer documented
  allowlist, the check weakens. This is a product decision, not a
  technical one

### Product Questions for Proposal

1. **Credential window scope** — does the staging access window this
   week include a real `DB_URL` (direct Postgres connection string)
   for the live catalog gate, or only the `sb_secret_` PostgREST
   path? The catalog gate (Issues A+B) requires direct `psycopg`
   access; PostgREST cannot read `pg_constraint`/`pg_policy`
   (`PGRST205`). What is the revocation deadline?

2. **018 apply window** — is a low-traffic DDL window approved this
   week for the 8-step migration (preflight proven safe: 21 tickets,
   0 duplicates, 0 invalid UUID, 1/1 approved audit retention)? If
   not, should S5 close with catalog receipts only and defer 018 to
   S5.1, or block S5 closure entirely on 018?

3. **Migration identity reconciliation** — the remote ledger has 3
   names absent locally (`add_tables_to_realtime_publication`,
   `add_realtime_publication_tables`, `greeting_onboarding_channel`)
   and local has 3 names absent remotely (`016_greeting_onboarding_channel`,
   `017_ticket_audit_repaired_outcome`, `018_ticket_integrity_fks`).
   Do we (a) run `supabase migration repair --status applied` to
   mark the remote-only names reconciled (tracked, preferred), or
   (b) document a 3-name historical allowlist and relax the
   `LiveAcceptanceGate` identity check (drift-acceptance)?

4. **JWKS algorithm policy** — the live staging JWKS endpoint returns
   an **ES256** (EC P-256) key, not RS256. Do we (a) extend the
   verifier to accept `["RS256", "ES256"]` (future-proof, matches
   Supabase Auth's `GOTRUE_JWT_KEYS` multi-algorithm support), or
   (b) keep RS256-only and document the JWKS path as inert for this
   project (the `sb_secret_` opaque path is the live credential)?
   Should we also plan for OKP/EdDSA?

5. **EXPLAIN workload definition** — for the `idx_ticket_guild_number`
   drop, is `EXPLAIN (ANALYZE, BUFFERS)` on a single representative
   `WHERE "guildId"=? AND "ticketNumber"=?` query sufficient receipt
   (proven: uses `idx_ticket_guild_ticket_number` Index Only Scan, 0
   heap fetches), or must we capture a multi-query workload
   (open-tickets-by-guild, closed-tickets-by-channel, etc.)? The
   0-scans `pg_stat_user_indexes` evidence is cumulative and
   insufficient alone (per S4 evaluator gate).

6. **Backup retention** — the 018 migration creates
   `ticket_backup_categoryid_text_20260818` (preserves TEXT
   categoryId for rollback). How long should this backup table be
   retained post-apply before `DROP TABLE`? The DOWN section comments
   it out; should S5 set a retention period (e.g., 30 days) and
   schedule a cleanup, or retain indefinitely?

7. **Rollback trigger** — what observable post-018 failure should
   trigger executing the DOWN section (restore TEXT categoryId, drop
   FKs/indexes)? A bot startup health-check failure? A specific test
   suite failure? Manual operator decision? The 018 SQL has
   `ON_ERROR_STOP=1` for apply, but post-apply monitoring is
   undefined.

### Ready for Proposal

**Yes.** The code, live catalog facts, migration structure, JWKS
endpoint behavior, EXPLAIN capability, and the four hidden issues are
fully characterized. The proposal must first record the product
answers to questions 1-4 (credential window, 018 apply timing,
migration identity reconciliation, JWKS algorithm policy) before
implementation begins. Questions 5-7 refine the 018 apply procedure
but do not block the catalog-receipts closure path.

The single most important realization: **S4's `PASS_WITH_WARNINGS`
cannot be closed by simply running the existing gate against real DB —
the gate itself has three latent bugs (Issues A, B, D) that only
manifest under real `psycopg` execution. S5 must fix the gate AND run
it.**
