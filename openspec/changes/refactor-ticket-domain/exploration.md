## Exploration: refactor-ticket-domain — S2

### Scope and Baseline

This exploration covers the proposed S2 ticket-domain decomposition, guild-scope enforcement, live Supabase FK/RLS parity, Sentinel permission impact, and the remaining test typing debt. It does not create specifications or a technical design.

Execution context: `auto-chain`, `stacked-to-main`, `800` authored-line review budget per slice, strict TDD with `uv run pytest`, baseline `ddec186` on `master`.

### Current State

#### Live repository verification

| Check | Result |
|---|---|
| `ticket_service.py` | 2,170 lines |
| `tickets.py` | 1,079 lines (one line above the stated 1,078 estimate) |
| `views/tickets.py` | 1,011 lines |
| `sentinel.py` | 965 lines |
| `uv run pytest -q` | 1,814 passed, 3 skipped; 88.61% coverage; 13.05s |
| `uv run ruff format --check .` | Clean; 153 files already formatted |
| `uv run ruff check bot tests --statistics` | Clean |
| `uv run ruff check . --statistics` | 11 errors, all in `scripts/`: 4 `EM102`, 4 `TRY003`, 2 `T201`, 1 `SIM102` |
| `uv run mypy bot` | Clean; 67 source files |
| `uv run mypy tests` | 28 errors across 7 test files |
| `uv run pytest --collect-only -q` | 1,817 tests collected |

The 28 test typing errors are concentrated in `test_verify_remediation_5_findings.py`, `test_ticket_views.py`, `test_embeds.py`, `test_core_help_builder.py`, `test_sentinel_cog.py`, `test_sentinel_behavior.py`, and `test_tickets_cog.py`. They are mostly optional-value narrowing, mock return annotations, and command-object `None` narrowing. They are independent of the runtime ticket behavior and are a good first bounded work unit.

#### Ticket service structure and call paths

`TicketService` starts at `bot/services/ticket_service.py:179` and has 31 dependent callers according to CodeGraph. The current file already exposes natural behavior seams:

- Lines 59–168: pure repair helpers (`backoff_delay`, sweep planning, fresh channel probing, and the shared fail-closed eligibility decision).
- Lines 200–372: normal creation and conditional close, including cache mutation and audit writes.
- Lines 374–565: the shared evidence-gated repair coordinator.
- Lines 575–876: channel-delete, bounded sweep, and evidence adapters.
- Lines 878–1244: reference resolution, manual repair, authority checks, and repair audit fallback.
- Lines 1245–1523: claim, unclaim, category edit, stale queries, and channel-cache operations.
- Lines 1529–1854: sub-ticket creation, reopen, transfer, and Discord channel construction.
- Lines 1860–2170: staff notes, channel creation orchestration, transcript upload, countdown, and deletion.

Important call paths:

- `TicketPanelView` → `TicketIntakeModal` → `create_ticket_channel` → `create_ticket` or `create_subticket`.
- `TicketActionsView` → `claim_ticket`, `transfer_ticket`, or `close_ticket_full`.
- `_EditCategorySelect` → `edit_ticket_category`.
- `TicketsCog.repair_ticket` → `repair_ticket_by_ref` → guild-scoped `get_ticket_by_number` for numeric references.
- `AuditListener`/integrity loops → `handle_channel_delete` or `sweep_integrity` → `repair_ticket_from_evidence`.

Method-level blast radius from CodeGraph includes 15 internal callers of `close_ticket`, 11 internal callers of `create_subticket`, 8 view callers of `claim_ticket`, 19 cog callers of `reopen_ticket`, 17 callers of `get_ticket`, 11 callers of `get_ticket_by_channel`, 7 callers of `get_ticket_by_number`, and 5 callers of `get_notes`. The service is not only a CRUD wrapper: it owns Discord channel orchestration, cache state, invariants, audit semantics, and repair authorization.

#### Tickets cog and views

`TicketsCog` is already a thin-ish interaction layer, but it still contains several direct DB lookups and lifecycle decisions. Its command groups are:

- Lines 85–186: cache synchronization, stale auto-close loop, integrity sweep loop, and `on_message` activity updates.
- Lines 187–486: panel deployment, category CRUD, and `configure_fields set`.
- Lines 487–825: sub-ticket creation, reopen, transfer, and unclaim.
- Lines 826–945: staff note group (`add`, `list`, `delete`).
- Lines 946–1071: manual integrity sweep and repair commands.

CodeGraph reports 16 cog-local callers and test coverage in `test_tickets_cog.py`, `test_ephemeral_standard.py`, and `test_tickets_i18n.py`. The integrity commands are already delegators; the category and sub-ticket commands still combine interaction handling, guild ownership checks, DB access, and service orchestration.

`bot/views/tickets.py` has three strong seams:

- Lines 31–420: panel deployment, intake flow, and `TicketIntakeModal`.
- Lines 422–758: persistent `TicketActionsView` with claim, transfer confirmation, close confirmation, and category-edit entry.
- Lines 760–1011: category and edit-category selects, including revalidation of moderator access and fresh ticket reads.

The persistent views use `timeout=None` and static custom IDs, so extraction must preserve `TicketPanelView`, `TicketActionsView`, `ticket:open`, `ticket:claim`, `ticket:close`, and `ticket:edit-category` registration. The ephemeral select callbacks are a security boundary because they re-check `is_mod_check` after a 300-second window.

#### Invariant and permission coupling

`bot/services/ticket_invariants.py` is 437 lines of pure logic mirrored by dashboard TypeScript and contract tests. `TicketService` imports the status, note, category, subticket, reference-parser, and repair-authority rules directly. `TicketRef` has no dedicated covering test reported by CodeGraph, although the broader contract suite exists. The parser documentation still describes cog-owned UUID resolution, while the current implementation correctly makes repair reference resolution service-owned; that wording should be corrected as part of the seam work rather than creating a second parser.

`is_mod` has 23 decorator callers in `sentinel.py` and `tickets.py`. `is_mod_check` has 21 callers, including the ticket buttons and category selects in `views/tickets.py`. The decorator path registers both slash and prefix checks; the inline predicate path is used by persistent/ephemeral views. `GuildService._sync_mod_role_cache()` is the cache owner, and `bot/utils/checks.py` is the single permission decision point. Any change to role resolution or context typing must keep both paths and their tests intact.

`GreetingService` and `GuildService` are a useful DRY reference, not an S2 ticket target: `GreetingService` has 5 service/bot callers, `GuildService` has 17, and `GuildService.get_greeting_config()`/`save_greeting_config()` delegate to the owning greeting service instead of duplicating fields. The same ownership pattern should be used for ticket sub-services behind a compatibility facade.

#### Context typing

`NebulosaContext` already subclasses `commands.Context["NebulosaBot"]` in `bot/core/context.py`. `tickets.py` uses it, but `utility.py` and `sentinel.py` still annotate callbacks and helpers as `commands.Context[Any]`. Context7's discord.py documentation supports a typed custom `Context` subclass and confirms that hybrid commands expose the interaction through `Context.interaction`. The low-risk direction is to use `NebulosaContext` consistently for the remaining bot cogs, or `commands.Context[NebulosaBot]` where a generic context is intentionally required; do not move decorators or add broad ignores.

### Live Supabase and PostgreSQL Evidence

Live project `vozkcckiybebhcclrasa` is `ACTIVE_HEALTHY`, PostgreSQL `17.6.1.155`, region `sa-east-1`. Read-only MCP and SQL checks were run against `public`.

| Inventory fact | On-disk constant | Live result | Assessment |
|---|---:|---:|---|
| RLS/no-policy tables | 9 | 9 tables have RLS enabled and zero policies | Matches; all publishable/authenticated access is denied unless policy/role behavior changes |
| Realtime CDC tables | 4 | `guild`, `greeting_config`, `ticket`, `ticket_note` | Matches `CDC_TABLES` |
| Unused indexes | 12 | All 12 named indexes exist with `idx_scan = 0`; performance advisor reports 12 | Matches, but the database is nearly empty, so this is not removal proof |
| Guild-scope ledger | 12 methods | 12 names in `GUILD_SCOPE_GAPS` | Requires API/ownership review; the ledger is not proof that every method still lacks a guild parameter |
| FK retention policy | `ticket_note=CASCADE`, `ticket_audit=SET NULL` | No corresponding note/audit FKs live | Policy is documented but unenforced |

The live `pg_constraint` query returned only six foreign keys, all child-to-`guild` with `ON DELETE CASCADE`: `economy_config`, `greeting_config`, `infraction`, `member`, `ticket`, and `ticket_category`. There are no live FKs for `ticket.parentId`, `ticket.categoryId`, ticket actor/author identifiers, `ticket_note.ticketId`, or `ticket_audit.ticketId`/`guildId`. The local `migrations/003_subtickets_notes.sql` explicitly says Transaction Mode prevents FK enforcement; that premise must be corrected before choosing a migration policy because pooler mode is not a PostgreSQL referential-integrity switch.

The live `pg_policies` check found zero policies on all nine RLS-enabled tables. Seven tables are also marked `relforcerowsecurity=true`; `ticket_note` and `ticket_audit` are RLS-enabled but not forced. Supabase's current documentation confirms that RLS without policies blocks publishable-key access, while service-role access bypasses RLS and must remain server-side. The security advisor reports nine `rls_enabled_no_policy` INFO findings plus a separate leaked-password-protection WARN.

The live Realtime publication exactly matches the four on-disk CDC tables. The live migration ledger has 19 entries, including `005_rls_secure_default`, two additional publication migrations, and `greeting_onboarding_channel`; the repository has no local `migrations/005_rls_secure_default.sql`. This is migration-parity debt, not evidence that a new RLS policy should be added blindly.

`SchemaInventory.build()` currently sets `fk_live_verified=False` and `rls_live_verified=False` and performs no DDL. Its on-disk-only parity result is unresolved because live evidence is not bound. S2 should add a read-only evidence binder/test path before any migration changes.

### Guild-Scope Gap Map

The 12 inventory names span four DB mixins:

- `ticket_db.py`: `get_ticket`, `get_ticket_by_channel`, `update_ticket`, `get_tickets_by_parent`.
- `ticket_category_db.py`: `get_ticket_category`, `delete_ticket_category`.
- `ticket_note_db.py`: `insert_ticket_note`, `get_ticket_notes`, `delete_ticket_note`, `get_recent_notes_for_dedup`.
- `ticket_audit_db.py`: `insert_audit_row`, `get_audit_rows`.

The gap is mixed rather than uniform. `get_audit_rows` already requires and filters by `guild_id`; `insert_audit_row` accepts `guild_id` but does not validate that the ticket belongs to that guild. Category deletion and field updates currently rely on a post-fetch guild check in the cog or a guild-filtered update. Ticket and note methods remain ID-only at the DB boundary. The safe contract is to add guild-aware methods or ownership-checked service wrappers, migrate callers one behavior slice at a time, and retain compatibility only where it cannot bypass guild isolation.

### Tool Guidance Applied

- **Supabase/PostgreSQL:** use read-only `pg_constraint`, `pg_policies`, `pg_publication_tables`, and `pg_stat_user_indexes` queries for evidence. Do not treat `RLS enabled + no policy` as harmless until the service-role-only versus authenticated-client contract is explicit.
- **discord.py:** use the existing typed `NebulosaContext` for hybrid callbacks; preserve `Context.interaction` behavior and both prefix/slash decorator registrations.
- **pytest-asyncio:** the project currently uses `asyncio_mode = "auto"`. Context7 recommends explicit asyncio markers and `pytest_asyncio.fixture` loop scopes for integration fixtures. Live Supabase tests should be separately marked, environment-gated, and excluded from the default mocked suite when credentials are absent.

### Approaches

#### A. Split by lifecycle, queries, and repair

Extract behavior slices from the existing service seams: lifecycle transitions and channel orchestration, query/cache adapters, and repair/integrity coordination. Split cog commands and views along the same user-visible flows, while preserving `TicketService`, `TicketsCog`, and public view names as compatibility facades during migration.

- **Pros:** follows the code's existing boundaries; keeps repair evidence and invariant tests together; minimizes API churn; supports vertical tests and independent rollback.
- **Cons:** query ownership and Discord concerns remain partially coupled; guild-scope enforcement crosses service and DB slices; the lifecycle slice is still large.
- **Effort:** Medium-High.

#### B. Split by domain, application, and infrastructure

Move pure invariants/models into domain modules, command/view orchestration into application modules, and Supabase/Realtime/FK/RLS work into infrastructure adapters with typed protocols.

- **Pros:** strongest long-term architecture; makes domain rules independently testable; gives guild ownership and live schema evidence explicit ports.
- **Cons:** introduces interfaces and dependency inversion across 31 service callers, 23 `is_mod` decorators, 21 inline permission callers, dashboard mirrors, and Discord views; risks mixing a security-policy decision with mechanical refactoring; the physical diff is far above the review budget.
- **Effort:** High-Very High.

### Recommendation

Use **A for the delivery order, with B as the destination**: create explicit domain/application/infrastructure seams, but extract one behavior slice at a time behind compatibility facades. Do not attempt a literal relocation of all 2,170 service lines, 1,079 cog lines, and 1,011 view lines inside a 1,200–1,500-line forecast. A full physical split necessarily produces several thousand authored additions/deletions and should be a larger chain.

#### Bounded S2 chain recommended under the current budget

| Slice | Boundary | Estimated authored change | Verification |
|---|---|---:|---|
| S2.1 | Typed command surface: migrate Sentinel/Utility context annotations, fix the 28 test Mypy errors, and add/retain `is_mod` dual-path characterization tests. No permission behavior change. | 250–300 | `uv run mypy bot tests`; focused cog/check tests; `uv run ruff check bot tests` |
| S2.2 | Guild-scoped ticket DB contract: add ownership-safe ticket/category/note/audit entry points, update callers in one vertical path, and add cross-guild denial tests. Keep old methods only when they cannot mutate or disclose across guilds. | 300–400 | DB mixin tests, ticket invariant tests, cross-guild service/view tests, full pytest |
| S2.3 | Live parity evidence: read-only verifier for FKs, RLS/policies, Realtime publication, indexes, and migration IDs; bind the result into `SchemaInventory`; add an opt-in live integration marker. No DDL or policy creation in this slice. | 300–400 | mocked evidence tests; opt-in Supabase integration command; default `uv run pytest` remains credential-independent |
| S2.4 | First physical domain seam: extract the shared repair coordinator/adapter boundary (channel delete, sweep, and manual/reference entry points) while keeping `TicketService` as a facade. Preserve the single `evaluate_repair_eligibility` path. | 350–400 | repair/integrity contract tests, listener tests, full pytest, Mypy |

Target total: approximately 1,200–1,500 authored lines, with every slice below the 800-line review budget. If the lower end of the estimate is mandatory, defer the physical repair extraction and land S2.1–S2.3 first; do not hide the move in a “refactor-only” diff.

#### Explicit follow-up for the remaining monoliths

The remaining lifecycle/query extraction, cog command-group relocation, and view relocation should be separate chained work units:

1. Lifecycle transitions and cache/query facade (`create`, `close`, `claim`, `unclaim`, `edit`, subticket, reopen, transfer, notes).
2. Ticket command groups: administration/categories, lifecycle operations, notes, and integrity commands.
3. Ticket views: intake/panel, persistent actions, and ephemeral category selects.

Each follow-up needs its own ≤800-line slice or a consciously expanded chain budget. `git mv` or a mixin extraction is not automatically small under this project’s authored additions-plus-deletions rule.

### Risks

- A change to `is_mod` or `_guild_mod_role_cache` can silently alter both slash/prefix commands and persistent view callbacks; the 23/21 caller blast radius requires characterization tests before edits.
- Direct DB calls in `TicketsCog` and `views/tickets.py` can bypass a new guild-safe service boundary unless caller migration is part of the same work unit.
- Adding the missing FKs is not mechanical: `ticket.categoryId` is text while `ticket_category.id` is UUID, and actor IDs are Discord snowflakes with no live user table after migration 006.
- Self-referential `ticket.parentId` needs an explicit deletion/depth policy; a normal FK enforces existence but not the one-level business rule.
- `ticket_note` and `ticket_audit` currently have no live FK despite documented retention semantics. Choosing `CASCADE`, `SET NULL`, or retention without product approval can destroy audit history or leave orphans.
- All nine live tables have RLS with zero policies. Adding policies without a client authorization model could expose cross-guild data; removing RLS would be a worse regression.
- Live migration history is not reproducible from local files because `005_rls_secure_default.sql` is absent locally and publication migrations differ.
- The project’s full Ruff command still fails in scripts even though `bot/` and `tests/` are clean; do not claim a project-wide zero-Ruff gate without resolving the scope.
- Mypy fixes in tests may expose real contract weaknesses around optional Discord command objects; suppressing the 28 errors would preserve the debt rather than close it.
- Persistent view extraction can break startup registration, custom IDs, localized labels, or the 300-second revalidation window even when command tests remain green.

### Product Questions for Proposal Refinement

1. Does S2 require the full physical relocation of all three ticket monoliths, or is the bounded S2 chain above (seams plus repair first slice) the intended deliverable? The former needs a larger chain and budget.
2. Is NebulosaBot intentionally service-role-only, including dashboard server actions, or must authenticated/publishable clients receive guild-scoped RLS policies? This decides whether S2 documents zero-policy RLS or designs policies.
3. What are the authoritative FK deletion semantics for `ticket.parentId`, `ticket.categoryId`, `ticket_note.ticketId`, and `ticket_audit.ticketId`/`guildId`: `CASCADE`, `SET NULL`, `RESTRICT`, or application-retained history?
4. Should live Supabase checks run automatically in CI against a dedicated staging project, or remain an explicit credential-gated integration command with mocked evidence in the default suite?
5. What are the S2 acceptance gates: full 1,814-test pass and Mypy zero, live FK/RLS/publication parity, zero `GUILD_SCOPE_GAPS`, or only the selected slice’s contract and rollback evidence?

### Ready for Proposal

**No, pending answers to the five product questions.** The technical direction is clear: use lifecycle/query/repair delivery slices, typed context cleanup, explicit guild-safe DB boundaries, and read-only live evidence before DDL. Proposal work can begin once scope (bounded first increment versus full physical split), RLS/FK policy, live-test strategy, and acceptance gates are recorded.
