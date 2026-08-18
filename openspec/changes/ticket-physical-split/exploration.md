## Exploration: ticket-physical-split — S3

### Scope and baseline

This exploration covers the S3 physical decomposition of the ticket service, cog, and views, together with guild-total enforcement, ticket foreign-key DDL, index policy, migration parity, and credential-backed live verification. It does not create specifications or a technical design.

Execution context: `auto-chain`, `stacked-to-main`, `800` authored-line review budget per PR slice, strict TDD with `uv run pytest`, baseline `ebe3c7f`.

The requested `ticket_service.py` size of 2,170 lines is a stale pre-S2.4 estimate. The current checkout is 2,108 lines; `tickets.py` remains 1,079 lines and `views/tickets.py` remains 1,011 lines.

### Evidence counts

| Evidence | Current result | Assessment |
|---|---:|---|
| `bot/services/ticket_service.py` | 2,108 lines; `TicketService` spans lines 82–2,108 | S2.4 created a repair coordinator seam, but the facade is still a monolith |
| `bot/cogs/tickets.py` | 1,079 lines; `TicketsCog` spans lines 77–1,071 | Interaction, direct DB lookup, ownership checks, and orchestration are still mixed |
| `bot/views/tickets.py` | 1,011 lines | Three clear view groups already exist, with security-sensitive ephemeral callbacks |
| Full pytest | 1,864 passed, 5 skipped, 89% coverage, 14.01s | Green with the configured `--cov-fail-under=0` override; default focused runs can fail only because they do not load the full coverage surface |
| `uv run mypy bot` | 0 errors, 68 source files | Keep as a hard gate |
| `uv run mypy tests` | 0 errors, 87 source files | The former S2 test typing debt is closed in this checkout |
| `uv run ruff check bot tests` | Clean | No application/test Ruff debt |
| `uv run ruff check .` | 11 errors, all under `scripts/` | 4 `EM102`, 4 `TRY003`, 2 `T201`, 1 `SIM102`; this remains a real project-wide lint failure |
| Local migration files | 17 SQL files | The repository does not mirror the full remote migration ledger |
| Live migration ledger | 19 entries | Includes remote-only `005_rls_secure_default`, two publication entries, and `greeting_onboarding_channel`; does not list local `017_ticket_audit_repaired_outcome` |
| Live Supabase project | `vozkcckiybebhcclrasa`, `ACTIVE_HEALTHY`, PostgreSQL 17.6.1.155 | Read-only MCP SQL evidence is available |

### Current state

#### Ticket service structure

The current `TicketService` has these physical seams, confirmed from the AST and CodeGraph:

- Creation and close: `create_ticket` lines 103–191 and `close_ticket` lines 193–275.
- Repair and integrity: `repair_ticket_from_evidence` lines 277–468, `handle_channel_delete` lines 478–556, `sweep_integrity` lines 565–779, `repair_ticket_by_ref` lines 781–945, and `repair_ticket_manual` lines 947–1,110.
- Lifecycle and ticket state: `claim_ticket` lines 1,148–1,205, `unclaim_ticket` lines 1,207–1,271, and `edit_ticket_category` lines 1,273–1,405.
- Query/cache state: stale-ticket lookup and channel-cache operations lines 1,407–1,450.
- Sub-ticket and lifecycle orchestration: `create_subticket` lines 1,456–1,585, `reopen_ticket` lines 1,587–1,647, and `transfer_ticket` lines 1,717–1,792.
- Notes and Discord orchestration: notes lines 1,798–1,894, channel creation lines 1,900–1,993, and full close/transcript deletion lines 1,995–2,108.

S2.4 already imports the shared `ticket_repair` coordinator under aliases, so repair eligibility has a single logical path. The remaining service body still owns DB access, cache mutation, invariants, audit writes, Discord channel creation, transcript upload, and authorization. A literal file move without an explicit ownership boundary would reproduce the monolith in several files.

#### Tickets cog command boundaries

`TicketsCog` has natural user-facing groups:

- Lifecycle/background: startup cache sync, stale close loop, integrity loop, and message activity (`lines 85–185`).
- Administration/category management: panel deployment, category CRUD, and intake field configuration (`lines 206–485`).
- Ticket lifecycle: sub-ticket creation, reopen, transfer, and unclaim (`lines 496–824`).
- Staff notes: add, list, and delete (`lines 835–944`).
- Integrity: manual sweep and repair commands (`lines 958–1,071`).

There are 14 direct `self.bot.db` references in the cog. The S2-deferred guild-scope callers are confirmed at:

- `tickets.py:568` — resolve the current channel or parent ticket during sub-ticket creation.
- `tickets.py:685` — resolve the current channel before transfer.
- `tickets.py:722` — resolve the current channel before category editing.

These are not cosmetic moves. Each lookup must carry the invoking guild ID or delegate to a service method that performs the ownership check before disclosing or mutating a row. The other direct DB references need the same audit while the administration and notes groups move.

#### View boundaries and IDs

`bot/views/tickets.py` has three physical seams:

1. `TicketIntakeModal` plus `TicketPanelView` (`lines 255–419`) — panel/intake flow.
2. `TicketActionsView` (`lines 422–757`) — persistent per-ticket actions.
3. `_CategorySelectView`, `_CategorySelect`, `_EditCategoryView`, and `_EditCategorySelect` (`lines 760–1,011`) — ephemeral category selection and edit flow.

The persistent views use `timeout=None` and are registered in `NebulosaBot.setup_hook()` with `bot.add_view()`. The four stable custom IDs are `ticket:open`, `ticket:claim`, `ticket:close`, and `ticket:edit-category`. They must not change during extraction. The category selectors use approximately 300-second timeouts and are ephemeral; their callbacks revalidate `is_mod_check` and re-fetch ticket state. That revalidation is an authorization boundary, not incidental UI code.

#### Permission and DRY coupling

The S2 exploration recorded `is_mod`/`is_mod_check` as a 23/21 blast-radius pair. Current CodeGraph/source verification shows 25 decorator applications across `tickets.py` (17) and `sentinel.py` (8), plus inline `is_mod_check` calls in ticket cog/view paths. The current counts should replace the stale 23/21 ledger before proposal acceptance; the behavior must remain a single decision point in `bot/utils/checks.py`.

`GuildService` is the correct DRY reference: `get_config()` is cache-first, `save_config()` invalidates and re-reads through the same path, and greeting configuration delegates to the owning `GreetingService` instead of duplicating fields. Ticket sub-services should use composition/delegation behind `TicketService`, not copy shared state or recreate invariant checks.

### Live schema and migration evidence

The current read-only Supabase checks found:

- Nine public tables with RLS enabled, zero public policies, and seven with forced RLS. The Realtime publication contains exactly `guild`, `greeting_config`, `ticket`, and `ticket_note`.
- Only six live foreign keys, all child-to-`guild` with `ON DELETE CASCADE`: `economy_config`, `greeting_config`, `infraction`, `member`, `ticket`, and `ticket_category`.
- No live FK for `ticket.parentId`, `ticket.categoryId`, `ticket_note.ticketId`, or `ticket_audit.ticketId`/`guildId`.
- Live types remain `ticket.categoryId TEXT` and `ticket_category.id UUID`; `ticket.parentId` and `ticket_note.ticketId` are already UUID.
- Direct SQL counts: 21 tickets, 5 categories, 5 active tickets, 21 non-null category references, all 21 valid UUID-shaped and matching category rows, zero parent references, zero active-slot duplicates, zero active-channel duplicates, and zero guild-number duplicates.
- There are 2 notes with zero orphaned note rows. There are 45 audit rows, including 1 orphaned ticket reference and 1 guild mismatch. Audit FK rollout therefore cannot be treated as a clean mechanical add without a retention/repair decision.
- `pg_stat_user_indexes` shows `idx_ticket_active_channel` at 11 scans, `idx_ticket_guild_ticket_number` at 11, `idx_ticket_channel` at 1, and `idx_ticket_note_ticket_author_created` at 3. The performance advisor reports 12 unused indexes, including ticket, category, note, and unrelated-domain indexes. The database is small, so `idx_scan=0` is evidence for review, not removal proof.
- The live table schema already accepts the `repaired` audit outcome, but the migration ledger does not contain local migration 017. This is schema/history drift that must be recorded and reconciled rather than silently re-applied.

#### DDL ordering recommendation

The migration should be staged as a read-only preflight followed by additive/validated constraints. Do not drop indexes first:

1. Run duplicate, invalid UUID, orphan, and audit-retention preflights. Abort on unapproved rows.
2. Convert `ticket.categoryId` from `TEXT` to `UUID` with an explicit `USING` cast only after the preflight. The current 21/21 data result makes this feasible, but the migration must still be reversible or backed up.
3. Add supporting child-side indexes and retain existing indexes while constraints are introduced. `ticket.parentId` needs an index for parent lookups and delete checks; note/audit ticket references need indexes for cascades or history queries.
4. Add `ticket.parentId -> ticket.id ON DELETE RESTRICT`, enforcing existence while leaving the one-level-depth business invariant in the service.
5. Add `ticket.categoryId -> ticket_category.id` with the product-approved deletion action; `SET NULL` best preserves historical tickets if categories can be hard-deleted.
6. Add `ticket_note.ticketId -> ticket.id ON DELETE CASCADE` after the zero-orphan check.
7. Make `ticket_audit.ticketId` nullable if history must survive ticket deletion, clean/approve the existing orphan, then add `ON DELETE SET NULL`. A guild FK on audit rows requires a separate decision because guild deletion and audit retention conflict.
8. Validate constraints, run the application contract suite, and only then drop a demonstrably redundant index in a later migration. In particular, the non-unique `idx_ticket_guild_number` is shadowed by the unique index and has zero scans, while `idx_ticket_channel` cannot be dropped merely because the partial active-channel index is used: it also covers closed-ticket lookups.

Supabase/PostgreSQL documentation supports explicit `ON DELETE RESTRICT`/`CASCADE` semantics, UUID primary keys, and preflight/backup/low-traffic precautions for destructive changes. The existing `migrations/003_subtickets_notes.sql` claim that Transaction Mode prevents FK enforcement is incorrect: pooler mode does not disable PostgreSQL referential integrity.

### Credential-backed live verification

The repository's current validator only accepts a JWT-shaped key whose decoded payload says `role=service_role`. The local `.env` contains a modern `sb_secret_` key: its live health probe succeeds against `guild` and `ticket`, but `validate_supabase_key()` rejects it as “not a verifiable JWT”. Context7's current Supabase documentation confirms that `sb_secret_` is the server-side replacement for the legacy `service_role` key and is opaque, so it cannot be locally role-decoded as a JWT.

There is a second live gap: `fetch_live_metadata()` attempts to query `public.pg_constraint`, `public.pg_policies`, `public.pg_publication_tables`, and `public.supabase_migrations` through PostgREST. The actual credential-backed run fails with `PGRST205` because `public.pg_constraint` is not in the PostgREST schema cache. The MCP SQL path can read these catalogs, but the application verifier cannot use that tool directly.

Recommended S3 contract:

- Support modern `sb_secret_` as an explicitly server-only credential mode, proving it with a read-only health query against an RLS-enabled table; retain a separate legacy JWT path only if legacy keys remain supported.
- Do not call base64 payload parsing “cryptographic verification”. If legacy JWT signature verification is required, define the signing-key/JWKS source and use PyJWT with an allowlisted algorithm; PyJWT is currently importable transitively but is not a direct project dependency.
- Move catalog evidence to a dedicated read-only database/RPC path with staging-only credentials, or run it through a dedicated verifier process that has catalog access. Do not assume PostgREST exposes system catalogs.
- Keep the default suite credential-independent. The existing `LIVE_SUPABASE=1` tests still bind mocked evidence; they do not prove a network query. Add a separately marked live test that fails closed when credentials are absent and never performs DDL or ticket mutation.

### Context7 findings

- Supabase/PostgreSQL: define FK actions explicitly; self-references are supported, UUID keys are first-class, and destructive schema work should be preflighted and staged.
- Ruff: `[tool.ruff.lint.per-file-ignores]` supports path patterns such as `scripts/**/*.py`. It should not be used to hide fixable `EM102`, `TRY003`, or `SIM102` debt; only intentional CLI output may justify a narrow `T201` exception.
- pytest-asyncio: the project currently uses `asyncio_mode = "auto"`. Split integration tests should still use explicit `pytest.mark.asyncio`/`pytest_asyncio.fixture` loop scopes where live resources are shared, and a dedicated `live` marker for credential-gated tests.

### Approaches

| Approach | Pros | Cons | Effort |
|---|---|---|---|
| **True `git mv` / block relocation** | Best physical end state and history locality; filenames clearly express ownership | Moving 2,108 + 1,079 + 1,011 lines creates a large authored add/delete diff under the review budget; imports, shared state, and circular dependencies surface at once; rollback is coarse | High–Very High |
| **Mixin extraction** | Smallest call-site churn; facade methods remain available; can move method blocks quickly | Hidden `self` contract, MRO coupling, unclear ownership of DB/cache/Discord state, and easy duplication of invariants; physical modules still behave as one god object | Medium initially, High to finish |
| **Facade-preserving composition and incremental moves** | Keeps external `TicketService`, cog, and persistent view names stable; makes each behavior slice testable and reversible; matches `GuildService` delegation pattern; supports stacked PRs | Temporary delegation boilerplate; requires explicit protocols/dependency ownership; old facade can become permanent without a deprecation gate | Medium–High, recommended |

The recommended approach is composition behind compatibility facades. Extract `TicketLifecycleService`, `TicketQueryService`, and `TicketRepairService` with one owner for each invariant/cache mutation. Keep `TicketService` as a thin adapter until all callers migrate. Apply the same flow-aligned split to cog command groups and views, preserving exports, setup wiring, custom IDs, timeout behavior, and callback revalidation.

### Recommended four-slice delivery plan

The four slices below are release-level workstreams. Because physical relocation counts authored additions plus deletions, slices 3 and 4 should be promoted to two child PRs each if their measured diff exceeds 800 lines; pretending a move is cheap because Git detects a rename would violate the cached review guard.

1. **S3.1 — Live and permission guardrails (approximately 450–700 lines)**
   - Replace the stale 23/21 permission ledger with current characterization counts.
   - Close the three deferred cog guild-scope callers and audit the remaining direct DB references.
   - Define the modern `sb_secret_` credential path, PyJWT/JWKS policy for legacy JWTs, and a real opt-in live read-only harness.
   - Fix the 11 script Ruff findings, or document only narrowly justified `T201` script output exceptions.
   - Gate: `uv run pytest`, `uv run mypy bot tests`, `uv run ruff check bot tests scripts`, and a credential-independent live-test skip path.

2. **S3.2 — FK/data preflight and migration parity (approximately 550–800 lines)**
   - Add read-only preflight assertions for the current 21/21 category references, parent depth, note orphans, and audit orphan/mismatch policy.
   - Add the ordered DDL for category UUID conversion and approved FKs; validate before any redundant-index drop.
   - Reconcile local 17-file SQL history, remote 19-entry history, and the already-live repaired outcome.
   - Gate: migration structural tests, live catalog evidence, `pg_constraint`/column/index assertions, and rollback/lock-timeout evidence.

3. **S3.3 — Ticket service physical split (two bounded child PRs likely)**
   - Child A: move query/cache ownership and the lifecycle facade while preserving all public `TicketService` methods.
   - Child B: move repair/integrity orchestration and Discord channel/transcript helpers, retaining one `evaluate_repair_eligibility` path.
   - Gate each child with service contract tests, repair/listener tests, full mypy, and a clean facade import graph. No command/view relocation in this slice.

4. **S3.4 — Cog and view physical split (two bounded child PRs likely)**
   - Child A: move `TicketsCog` administration/lifecycle/notes/integrity groups into flow modules while preserving command names, hybrid registration, and `setup()`.
   - Child B: move panel/intake, persistent actions, and ephemeral category selects while preserving all four custom IDs, `timeout=None`, 300-second ephemeral timeouts, and `is_mod_check` revalidation.
   - Gate with cog/view integration tests, startup persistent-view registration tests, localization tests, and full suite verification.

Dependency chain: `S3.1` → `S3.2` → `S3.3A` → `S3.3B` → `S3.4A` → `S3.4B`. Each child PR must state its start state, finish state, dependency, verification, rollback boundary, and out-of-scope follow-up. No PR should combine DDL, a large relocation, and unrelated lint cleanup.

### Risks

- The physical split can silently duplicate cache mutation, audit writes, or invariant checks unless every rule has one owner and facade methods delegate exactly once.
- Direct cog/view database calls can bypass guild ownership even when service methods are safe; caller migration is part of the security change.
- Changing `categoryId` from text to UUID is feasible on current data but still requires an explicit cast, lock/rollback plan, and tests for legacy malformed values.
- The existing audit orphan and guild mismatch block an unconditional `ticket_audit` FK. Deleting or nulling those rows without a retention decision would destroy evidence.
- `ON DELETE SET NULL` requires `ticket_audit.ticketId` to become nullable; this is a semantic change, not only a constraint declaration.
- Live `sb_secret_` acceptance and legacy JWT verification are different trust paths. A payload decode without signature verification is not proof of credential authenticity.
- PostgREST cannot expose the catalog tables used by the current live binder. A successful API health probe alone does not prove FK, RLS, publication, or migration parity.
- `pg_stat_user_indexes` is cumulative and the live database is small; unused-index advisor results cannot be converted directly into drop commands.
- Persistent view registration, static custom IDs, localization, and ephemeral revalidation can regress while command/service tests remain green.
- The four release-level slices require six likely PRs to stay under the 800-line review guard. Compressing them into four physical PRs would create a deliberate review-budget exception.

### Product questions for proposal

1. What is the authoritative deletion action for each FK: `parentId` (`RESTRICT`), `categoryId` (`SET NULL` versus `RESTRICT`), `ticket_note.ticketId` (`CASCADE`), and `ticket_audit.ticketId`/`guildId` (`SET NULL`, retention, or no FK)?
2. Which indexes are allowed to be removed, and is the policy based on current `pg_stat_user_indexes`, `EXPLAIN` plans, or a minimum staging workload? In particular, should the duplicate non-unique guild-number index be dropped while the general channel index is retained?
3. Should S3 use the six-child stacked order above, or is a larger per-slice review-budget exception explicitly accepted for true physical moves?
4. Should staging verification support the repository's modern `sb_secret_` key through a read-only API probe plus a separate catalog credential, or must deployment continue to require a legacy verifiable `service_role` JWT?
5. Which acceptance gates are mandatory: 1,864/5 full-suite result, 0 mypy, zero Ruff including scripts, zero guild-scope gaps, live FK/RLS/publication/migration parity, and verified persistent-view IDs?

### Recommendation

Proceed to proposal with facade-preserving composition, current-count guild enforcement first, read-only live credential/catalog gates before DDL, and the ordered FK/type migration before index cleanup. Treat the requested four slices as four release workstreams but budget six physical PRs under `auto-chain`; a literal three-monolith `git mv` is not review-safe within the cached 800-line limit.

### Ready for Proposal

**Yes, conditionally.** The code and live evidence are sufficient to write a proposal, but the proposal must record answers to the five product questions—especially audit/category deletion semantics, modern secret-key verification, and whether the six-child chain is accepted as the implementation of the four release slices.
