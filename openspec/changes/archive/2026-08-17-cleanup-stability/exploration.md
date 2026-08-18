## Exploration: cleanup-stability — S1 L3

### Current State

The audited baseline is clean: `master` and `origin/master` are both `f83e767`, tagged as `v0.2.0-baseline-pre-cleanup-stability`. The local worktree has no tracked changes. The requested three stacked slices are directionally sound, but the measured formatting diff alone is larger than the declared review budget.

#### Live verification snapshot

| Check | Result |
|---|---|
| Python | 3.13.14 |
| Ruff | 0.15.20 from `uv.lock` (the project minimum/pre-commit pin is `>=0.8`/`0.8.6`) |
| Mypy | 2.1.0 |
| discord.py | 2.7.1 |
| Supabase Python | 2.31.0 |
| `uv run ruff check . --statistics` | 30 errors: 27 in `bot/` and `tests/`, 3 in `scripts/check_awaited_execute.py`; 14 are auto-fixable |
| `uv run ruff format --check .` | 25 files would be reformatted; 122 are already formatted |
| Format authored diff estimate | 658 changed lines (`364` additions + `294` deletions) across the 25 files, before other S1 changes |
| `uv run mypy bot tests` | 57 errors in 12 files |
| `uv run bandit -r bot -c pyproject.toml --severity-level medium` | No medium/high issues; 93 low-severity findings are below the gate |
| `uv run pytest --cov=bot --cov-fail-under=75 -q` | 1,761 passed, 3 skipped; 88.47% coverage |
| Forced C901 check at max complexity 15 | No reported C901 violations in the surveyed services/cogs; file size remains the larger maintainability risk |

The OpenSpec context is stale relative to this run: it still says 384 tests and 74.59% coverage, while the live suite is materially larger and at 88.47%. The CI workflow and `Makefile` still run Ruff and Mypy against curated file lists; `lint-full` and `type-full` are explicitly aspirational/non-blocking.

#### Ruff findings and ignore ratchet

The current full `bot/` + `tests/` Ruff count is 27:

- `E501`: 7
- `F401`: 6
- `I001`: 4
- `F541`: 3
- `SIM102`: 2
- `RUF012`: 2
- `EM102`, `S112`, `SIM117`: 1 each

The 3 extra project-wide findings are `SIM102` and two `T201` findings in `scripts/check_awaited_execute.py`. That script is outside the stated blocking scope, so S1-PR1 must explicitly choose either `bot/` + `tests/` as the gate or include the script in the same cleanup.

`pyproject.toml` currently suppresses 19 entries for every `bot/**/*.py` file: 14 whole rule families plus specific `SIM105`/`SIM108`/`SIM103`/`RUF059`/`F841` exceptions. The broad families include `S`, `C90`, `RET`, `ARG`, `DTZ`, `EM`, `TRY`, `RSE`, `PERF`, and `FURB`. Ruff's current documentation supports exact per-file codes and `extend-per-file-ignores`; it does not require broad family suppression. The lowest-risk ratchet is:

1. Preserve the existing test-specific exceptions and first land mechanical formatting/import cleanup.
2. Remove `RSE` first: 0 currently suppressed findings.
3. Remove `RET` and `SIM` next: 2 and 7 findings respectively.
4. Replace the broad `TRY` ignore with explicit codes. Removing all `TRY` suppressions exposes 136 findings, including 116 `TRY003` message-construction findings concentrated in `ticket_service.py`, `ticket_field_service.py`, `ticket_invariants.py`, and DB mixins. Clear the smaller `TRY300`/`TRY301`/`TRY004` set first and retain an explicit `TRY003` exception until separately budgeted.
5. Treat `S` as a separate security ratchet, not a blanket PR3 switch. The isolated production-only count is 95, of which 90 are `S101` assertions; `S110`, `S310`, and `S311` are the actionable subset. Ruff S rules and Bandit are overlapping but not equivalent gates.

This order minimizes semantic edits and keeps the large `TRY003`/`S101` debt from being disguised as a small configuration change.

#### Mypy findings

The 57 errors divide into 27 errors in four cogs and 30 test typing errors. The cog group contains 13 `arg-type` failures from `hybrid_command`/`hybrid_group`, 13 corresponding misplaced/unused `type: ignore[arg-type]` comments, and one generic `commands.Command` error in `bot/cogs/core.py`. The remaining 30 errors are test union narrowing, mock return annotations, and optional-value handling.

The installed discord.py source types `hybrid_command` as a generic callback over `CogT`, `ContextT`, parameters, and return type. The current callbacks mostly use `commands.Context[Any]`, while `NebulosaContext` inherits `commands.Context` without a bot type parameter. The real-fix direction is to parameterize the custom context with the concrete bot type and use `commands.Context[NebulosaBot]` (or the parameterized custom context) consistently in cog callbacks, then type the help-builder command as `commands.Command[Any, Any, Any]` (or the precise generic shape). This lets decorator inference resolve instead of suppressing the error. Moving the existing ignore comments would only hide the problem and is explicitly out of scope.

#### Git hygiene and branch safety

There are no open GitHub PRs. `git ls-remote --heads origin` shows 12 actual remote heads, including `master`; seven additional local `origin/*` tracking refs are stale. `git remote prune origin --dry-run` identifies these local-only refs:

- `origin/chore/type-strict-core-listeners`
- `origin/chore/type-strict-models`
- `origin/feat/edit-category-audit-feedback`
- `origin/feat/spanish-ux-01-translator`
- `origin/feat/spanish-ux-02-runtime-ui`
- `origin/feat/spanish-ux-03-slash-cogs`
- `origin/fix/command-permissions-and-log-hygiene`

The actual remote branches whose tips are ancestors of `f83e767` are safe from a Git reachability standpoint after the final owner audit: `chore/type-strict-cogs`, `feat/product-artifact-audit`, `feat/ticket-category-ops-01-foundation`, `feat/ticket-category-ops-02-service`, `feat/ticket-category-ops-03-views`, `feat/ticket-integrity-recovery-pr1`, `feat/ticket-integrity-recovery-pr2`, `feat/welcome-card-disabled-cta-guard`, and `fix/ticket-open-limit-ephemeral`. Historical merged PRs confirm the main groups (#33–35, #37, #39, #53, and #54); ancestor reachability also covers intermediate branches.

`feat/ticket-integrity-recovery-pr2a` and `pr2b` are the same head (`8cb5674`) and each has one commit not reachable from `master`. That commit is preserved on remote tags `archive/2026-07-feat-ticket-integrity-recovery-pr2a` and `archive/2026-07-feat-ticket-integrity-recovery-pr2b`. They are not merged branches; they are safe to delete only if the maintainer accepts the tag as the authoritative archive of the abandoned alternative. Branch deletion is a separate repository-administration action, not something a PR merge performs. Local stale tracking refs can be pruned independently without deleting any remote branch.

#### CodeGraph blast radius

CodeGraph was queried before filesystem exploration and returned the current source plus call relationships:

- `TicketService`: 2,170 lines, 31 dependent callers, and tests in the ticket service/contract/remediation suites.
- `GreetingService`: 5 dependent callers through `GuildService`/`NebulosaBot`, with `tests/test_greeting_service.py` coverage. `dispatch_welcome` and `dispatch_goodbye` repeat the same card/text/channel flow.
- `GuildService`: 17 dependent callers through bot startup and command paths; it owns the moderator-role cache used by permission checks.
- `Database`: 29 callers across bot context and services; the database facade composes nine DB mixins.
- `is_mod`: 23 callers in `sentinel` and `tickets`, plus direct permission tests. It has a decorator path and an inline predicate path sharing role resolution, so changes have a broad authorization blast radius.
- `get_ticket_by_number`: 7 callers and contract coverage; it is the canonical guild-scoped ticket-number lookup.
- Several DB mixins, including `GuildDBMixin`, `MemberDBMixin`, and `TicketAuditDBMixin`, have no direct covering tests reported by CodeGraph.

The requested S2 monolith split remains a valid non-goal. S1 should only make bounded helper/typing changes and not alter ticket-domain ownership.

#### Supabase and PostgreSQL audit

The live project `nebulosabot` is active and healthy (PostgreSQL 17.6). The live database has nine public tables: `guild`, `member`, `infraction`, `ticket`, `ticket_category`, `economy_config`, `greeting_config`, `ticket_note`, and `ticket_audit`. It currently reports 3 tickets, 1 note, and 16 audit rows; the other table counts are zero.

The current client construction is valid: `acreate_client(url, key, AsyncClientOptions(schema="public"))` matches the installed async signature. Context7 confirms that Realtime requires the async factory. The deep audit should still decide whether server-side clients set `auto_refresh_token=False` and `persist_session=False`, and should stop describing the key as interchangeable `anon or service_role` if the runtime contract requires service-role access.

The repository and live state differ materially:

| Audit area | Evidence | Gap / implication |
|---|---|---|
| RLS | Live `list_tables` reports RLS enabled on all nine tables. Security advisors report `rls_enabled_no_policy` for all nine, with 10 security lints total including a leaked-password-protection warning. | The live state appears intentionally service-role-only, but that contract is undocumented and untested. If dashboard/API clients need `authenticated` access, policies and grants are missing. If service-role-only is intentional, S1-PR3 should encode and test that decision rather than treating the advisor output as harmless noise. RLS no-policy remediation: https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy |
| RLS migration parity | Live migration history includes `005_rls_secure_default`, but that file is absent from the repository. | Filesystem SQL is not a complete deployment ledger. Reconstruct or explicitly document the live-only migration before claiming reproducible environments. |
| Referential integrity | Live foreign-key introspection shows only child-to-`guild` FKs. `ticket_note` and `ticket_audit` have no FKs; `ticket.parentId`, `ticket.categoryId`, and ticket actor/author IDs are not DB-constrained. | `migrations/003_subtickets_notes.sql` says Transaction Mode prevents FK enforcement, but Supabase Transaction Mode only changes pooling behavior and disallows prepared statements; it does not disable PostgreSQL constraints. PostgreSQL confirms FKs enforce referential integrity independently of pooler mode. Choose explicit `CASCADE`, `SET NULL`, or `RESTRICT` semantics. |
| Ticket uniqueness | `migrations/015_ticket_lifecycle_reliability.sql` already defines unique `(guildId, ticketNumber)`, partial active-slot uniqueness, partial active-channel uniqueness, and normalized active category-name uniqueness. | These are not missing in the repository; their live existence must be verified. The live advisor also sees the older non-unique `idx_ticket_guild_number`, so the unique replacement may leave a redundant index. Do not add a duplicate index without an inventory. |
| Query guild scoping | Many ticket methods are correctly guild-scoped (`get_ticket_by_number`, stale/active queries, conditional close). Several low-level methods are ID-only: `get_ticket`, `get_ticket_by_channel`, `update_ticket`, `get_tickets_by_parent`, category get/delete, note get/delete/insert, and audit insert. | Service checks are not a substitute for a consistent database boundary. Add guild-scoped APIs or enforce ownership before these methods are callable from dashboard/operator paths. |
| Indexes | Performance advisors report 12 unused indexes, including `idx_member_guild`, `idx_infraction_guild_target`, `idx_ticket_guild_status`, `idx_ticket_guild_number`, member leaderboard indexes, `idx_ticket_parent`, note indexes, and audit history indexes. | The database is nearly empty, so unused-index output is not proof of dead production indexes. Compare each index with actual query predicates and `EXPLAIN`, then remove only redundant indexes. Candidates for query-shape review include stale-ticket `(guildId,status,lastActivity)`, active-warning `(guildId,targetId,createdAt)`, and the duplicate ticket-number indexes. Unused-index remediation: https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index |
| Migration ledger | Live history contains 19 migrations, including two extra Realtime migrations and a live `greeting_onboarding_channel` name. The live schema already accepts `ticket_audit.outcome = 'repaired'`, but the live migration listing has no `017_ticket_audit_repaired_outcome` entry. | Migration history and schema state are drifting. S1-PR3 needs a read-only inventory and a deploy/replay decision before any destructive DDL. |
| Realtime/cache | `SUBSCRIBED_TABLES` contains only `guild`, `greeting_config`, `ticket`, and `ticket_note`. Guild/greeting TTL is 300 seconds; leaderboard TTL is 30 seconds. `claim_daily` updates member coins but does not invalidate leaderboard keys, and member/economy changes are not in Realtime publication. | Multi-instance economy reads can be stale beyond the intended contract. Either publish/invalidate the cached entities or explicitly make the leaderboard cache local/short-lived and test the stale window. |

Supabase's live security advisor also reports leaked-password protection disabled. That is a project-level Auth setting, not necessarily an S1 code change, but it must be surfaced to the operator rather than silently folded into the migration work.

The official Supabase RLS documentation says exposed tables need both RLS and grants/policies, that a table with RLS and no policies denies publishable-key access, and that service-role keys bypass RLS and must stay server-side. The Google search attempt was rate-limited; authoritative Context7, Supabase, PostgreSQL, installed package signatures, and live Supabase MCP evidence were sufficient for this exploration.

### Affected Areas

- `pyproject.toml` — broad Ruff per-file ignores, strict Mypy, version floors, and coverage configuration.
- `.pre-commit-config.yaml` — Ruff is pinned to 0.8.6, while `uv.lock` resolves 0.15.20; the Mypy hook receives filenames instead of enforcing the full project.
- `.github/workflows/ci.yml` — blocking job currently checks curated files rather than all `bot/` and `tests/`.
- `.github/workflows/code-quality.yml` — duplication/dead-code checks are intentionally report-only; it should not be confused with the blocking QA gate.
- `Makefile` — `lint`/`type` are curated and `lint-full`/`type-full` are non-blocking aspirations.
- `bot/services/ticket_service.py` — 2,170-line high-blast-radius service; exclude structural decomposition to S2.
- `bot/services/guild_service.py`, `bot/services/greeting_service.py` — cache-key duplication, 300-second TTLs, moderator-role cache synchronization, and duplicated greeting dispatch flows.
- `bot/utils/checks.py`, `bot/cogs/sentinel.py`, `bot/cogs/tickets.py` — shared `is_mod` authorization paths with 23 callers.
- `bot/cogs/greetings.py`, `bot/cogs/core.py`, `bot/cogs/stellar.py`, `bot/cogs/ocio.py` — hybrid-command typing failures and stale ignores.
- `bot/core/database.py`, `bot/core/db/*.py`, `bot/core/realtime.py` — async Supabase lifecycle, query scope, cache invalidation, and nine mixins.
- `migrations/*.sql` — local/live migration parity, RLS, constraints, indexes, RPC grants, and side-effectful migration 012.
- `tests/` — 30 current Mypy errors plus direct coverage gaps for several DB mixins; tests are green and above the coverage gate.

### Approaches

1. **Keep exactly three stacked PRs and absorb the measured debt** — Deliver the proposed hygiene, rigor, and deep slices without changing the 600-line envelope.
   - Pros: Matches the cached delivery plan; fewer review handoffs; clear PR themes.
   - Cons: The format-only diff is already 658 authored lines, so the plan violates the review budget before CI, pre-commit, Mypy, or database changes. Blanket `TRY`/`S` ratchets would add hidden semantic risk.
   - Effort: High

2. **Use four or five stacked-to-main work units with a mechanical-format slice** — Keep PR1 focused on branch/CI/format policy, split the 25-file formatting diff by bot/tests or by independent mechanical batches, then land Mypy/ignore rigor and a narrowly evidenced Supabase/cache slice.
   - Pros: Honest review accounting; formatting remains mechanically reviewable; each PR can have an independent rollback and verification receipt; preserves the chosen stacked-to-main strategy.
   - Cons: More branch/PR administration; the deep database work may need to be reduced to inventory plus one or two safe migrations rather than every desired hardening item.
   - Effort: Medium-High

3. **One global strictness and schema-hardening pass** — Remove broad ignores, add all FKs/RLS policies/index changes, and make CI run every tool in one change.
   - Pros: Fastest path to an apparently strict end state.
   - Cons: Contradicts the 400/600-line review guard, combines security semantics with formatting noise, risks breaking service-role/dashboard behavior, and makes rollback ambiguous.
   - Effort: Very High; not recommended

### Recommendation

Use approach 2. Keep the proposed business boundaries, but do not promise three ~200-line PRs until the maintainer resolves the measured 658-line formatter diff. The proposal should reserve the first slice for clean, reversible hygiene and blocking full `bot/` + `tests/` gates; use explicit Ruff code lists rather than broad family removal; fix hybrid typing by parameterizing `Context`/`NebulosaContext` instead of adding ignores; and make S1-PR3 an evidence-driven database/cache audit with no destructive DDL until live migration, RLS/grant, FK, and index state is reconciled.

For the Supabase portion, first decide whether this is a service-role-only backend. If yes, document that publishable-key access is intentionally denied, validate the key/role at startup or configuration time, and add negative access tests. If dashboard/API clients require authenticated Data API access, policies, grants, guild-scoped predicates, and policy tests become required scope. Correct the Transaction Mode misconception before choosing FKs; at minimum, notes need a ticket ownership decision and audit retention needs an explicit policy.

### Risks

- The declared 600-line envelope is not credible for three slices: Ruff formatting alone is 658 authored changes.
- Removing `TRY` or `S` as whole families exposes 136 and 95 production findings respectively; broad ratchets can create semantic churn disguised as configuration cleanup.
- Live Supabase state has all tables under RLS but no policies, while the repository lacks the live `005_rls_secure_default` migration. Adding policies without an authorization contract could expose data; removing RLS could be worse.
- Live migration history and filesystem migration names/results do not match; destructive DDL or replay claims need a read-only inventory and rollback plan.
- Several low-level DB methods accept only IDs and rely on service-layer ownership checks; future dashboard/operator callers could bypass guild isolation.
- The two `pr2a`/`pr2b` branches contain a unique tagged commit not in `master`; deleting them without an explicit abandoned-alternative decision could erase discoverability even though the tag preserves bytes.
- Mypy changes touch decorator inference across multiple cogs and the custom context type; each callback family needs focused tests before the full gate is enabled.
- Re-enabling strict full CI will expose the 3 script Ruff findings unless the blocking scope is explicitly `bot/` + `tests/`.

### Product and Business Questions for the Proposal

1. Is the 600 authored-line limit hard, or may the change become four/five stacked PRs so the already-measured formatting diff remains reviewable?
2. Is NebulosaBot intentionally service-role-only for Supabase, including the dashboard server actions, or must authenticated users receive policy-controlled Data API access?
3. When a guild, ticket, category, or parent ticket is deleted, should notes and audit history cascade, be retained, or be detached with `SET NULL`?
4. Should `ticket-integrity-recovery-pr2a/pr2b` be treated as abandoned tag-backed alternatives and deleted, or should their unique `8cb5674` implementation be recovered before branch deletion?
5. Is a 30-second cross-instance economy leaderboard staleness window acceptable, or is Realtime/member-cache invalidation part of the S1 product reliability contract?

### Ready for Proposal

**No, not yet.** The technical direction is clear, but the proposal must first record the review-budget decision and the service-role/RLS, deletion-retention, and tag-backed branch decisions above. Once those boundaries are accepted, approach 2 is ready for proposal; no spec or design has been created in this exploration.
