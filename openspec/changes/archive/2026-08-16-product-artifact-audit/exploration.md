# Exploration: Product Artifact Audit

## Audit Posture

This is a read-only audit of the current NebulosaBot worktree against repository documentation, diagrams, OpenSpec artifacts, observable implementation, tests, current library contracts, and repository history. No product code, active change, proposal, design, delta spec, task list, or verification report was modified or created. The only persisted artifact is this file.

The audit targets the current worktree, including staged ticket-integrity implementation and untracked active OpenSpec artifacts. It does not treat the current feature branch as the deployed product: local `HEAD` is `e68896a` on `feat/ticket-integrity-recovery-pr2`, while GitHub `master` is `456d496`.

## Current State

### Product Intent

**Explicit repository intent**

- `docs/MANUAL.md:3-26` describes NebulosaBot as an all-in-one Discord bot for moderation, tickets, economy, greetings, utility, and server setup; it claims 8 modules and 47 hybrid commands.
- `pyproject.toml:5-15` describes a Discord bot with moderation, economy, and tickets powered by Supabase.
- `openspec/config.yaml:3-9` names Core, Tickets, Sentinel moderation, Stellar economy, Utility, and Audit/XP listeners, with a cache-first RAM plus Supabase Realtime architecture.
- `Diagramas/DiagramaCasosUso.mmd` explicitly includes Discord XP/coins, support tickets, web profile, web configuration, moderation, and ticket management. `Diagramas/DiagramaSecuencia.mmd` explicitly promises Discord commands, dashboard writes, cache invalidation, and transcript-backed ticket closure.

**Inferred product value**

The coherent product value is a Discord-first, multi-guild operations layer: a server administrator should configure a guild once, users should receive safe and localized interaction flows, staff should moderate and manage tickets reliably, and the dashboard should expose trusted operational state without creating a second inconsistent source of truth. This is an inference from the explicit intent plus the cache, guild-scope, permissions, and dashboard artifacts; it is not stated as one authoritative product contract.

**Intent conflicts requiring a product decision**

- The use-case diagram includes giveaways and a web profile, but there is no giveaway/profile implementation, command, dashboard route, or current manual section. Repository search found no `giveaway` or `sorteo` product implementation.
- The manual says `/help` is the command source of truth, while `docs/MANUAL.md:442-452` acknowledges that the manual may be stale and still claims there is no README or visual greeting configuration even though the dashboard now has configuration routes.
- The diagram uses “Tickets (Enterprise)” and “Participar en Sorteos”; the current implementation and manual define a smaller support/moderation/economy product. These diagram labels are therefore treated as aspirational or stale, not as shipped requirements.

### Execution Snapshot

| Evidence | Verified result |
|---|---|
| CodeGraph | Index current: 213 files, 4,354 nodes, 11,911 edges. |
| Main OpenSpec specs | 62 spec files, 337 requirements, 801 scenarios. |
| Archived OpenSpec directories | 49 directories under `openspec/changes/archive/`, not 28. The 28 figure is stale or uses a different counting rule. |
| Active changes | Exactly `ticket-integrity-reconciliation` and `ticket-integrity-recovery`. |
| OpenSpec session config | `strict_tdd: true`, `uv run pytest`, `delivery_strategy: auto-chain`, `review_budget_lines: 800`. |
| Python suite | 1,612 collected; 1,608 passed, 1 failed, 3 skipped; 88.52% coverage. |
| Dashboard tests | 17 files, 240 tests passed; React `act(...)` warnings were emitted. |
| Dashboard type/build | `npx tsc --noEmit` passed; `npm run build` passed on Next.js 15.5.19 and generated the expected App Router routes. |
| Python compile/lint | `python -m py_compile bot/__main__.py` passed. `uv run ruff check .` failed with 30 findings, concentrated in scripts and tests. |

### Current Capability Map

- **Core/runtime:** `bot/bot.py:44-58` registers 8 cogs and 2 listeners. `setup_hook()` initializes the async database, TTL cache, Realtime subscriber, services, persistent ticket views, localization, extensions, and tree sync before gateway operation. Realtime startup failure degrades to TTL-only cache operation (`bot/bot.py:264-301`).
- **Moderation/permissions:** Sentinel commands and shared `is_admin()`/`is_mod()` checks exist. Both slash and prefix predicates are registered in `bot/utils/checks.py:18-171`; the recent GitHub security fix addressed the historical prefix bypass.
- **Tickets:** Ticket creation, claim/unclaim, transfer, close, reopen, notes, categories, custom fields, transcripts, and dashboard list/audit/notes flows exist. Current staged code adds conditional close, integrity evidence, G.2 preflight primitives, and repair service primitives, but not the promised deletion-event repair, sweeps, or manual repair command.
- **Economy:** Stellar exposes daily rewards, coins, leaderboards, XP, and rank cards; `EconomyService` delegates configuration reads to the database and XP messages are handled by `XPListener`. Dashboard economy configuration exists, but direct page coverage is absent in CodeGraph's test relationships.
- **Greetings/onboarding:** Welcome/goodbye commands, image cards, onboarding-channel CTA, cache invalidation, and a dashboard greeting form exist. This is one of the better cross-surface capabilities, although supported-language contracts are inconsistent.
- **Utility/ocio:** Avatar, server/user information, dice, and banana commands exist with tests and localized responses. No material implementation blocker was found in this slice.
- **Dashboard:** The build exposes authenticated guild overview, general config, economy, greeting, and tickets routes plus auth callback/logout/login. It is an operational configuration and ticket-observation surface, not parity with every Discord moderation, ticket setup, or integrity operation.
- **Data/runtime contracts:** Guild cache keys are guild-scoped and expire after 300 seconds. Realtime subscribes only to `guild`, `greeting_config`, `ticket`, and `ticket_note`; the publication migration names the same four tables. The live database could not be inspected because Supabase MCP authentication failed.

## Affected Areas

- `docs/MANUAL.md`, `Diagramas/*.mmd`, `pyproject.toml` — explicit product intent, command claims, and architecture diagrams.
- `openspec/config.yaml`, `openspec/specs/`, `openspec/changes/archive/` — source-of-truth and historical artifact health.
- `openspec/changes/ticket-integrity-reconciliation/` — active reconciliation claims all six implementation phases complete but has no verification report.
- `openspec/changes/ticket-integrity-recovery/` — active recovery currently stops after PR1/PR2; later lifecycle phases and fresh evidence remain unchecked.
- `bot/bot.py`, `bot/cogs/`, `bot/services/`, `bot/core/`, `bot/listeners/` — current Discord behavior, service boundaries, cache, Realtime, permissions, and ticket lifecycle.
- `dashboard/app/`, `dashboard/lib/actions/`, `dashboard/lib/supabase.ts` — dashboard routes, server actions, authentication, guild isolation, and service-role boundaries.
- `migrations/` — schema, RLS, RPC, and Realtime publication contracts.
- `tests/`, `dashboard/__tests__/` — executable evidence and known contract/test drift.

## Artifact Health Inventory

### Main Specs

- 62 main specs contain 337 requirements and 801 scenarios.
- `cache-sync-webhook/spec.md` intentionally records a removed capability and has no scenarios. It is not automatically a defect, but it is a weak executable contract and should be explicitly classified as a deprecation record rather than treated like an active behavior spec.
- Only 18 of 62 specs contain explicit repository-path code hints, and only 8 mention test paths or test commands. This is a traceability weakness, not proof that the remaining specs are unimplemented.
- No duplicate main spec files were byte-identical. The greater issue is semantic overlap: active ticket changes restate and modify the same `database-layer`, `ticket-model`, and `ticket-service` contracts.

### Archived Changes

There are 49 archived change directories. Standard artifact presence is uneven:

- `proposal.md`, `design.md`, and `tasks.md`: 43/49 each.
- `verify-report.md`: 43/49.
- `archive-report.md`: 34/49.
- `apply-progress.md`: 18/49.
- The clearly incomplete standard sets include `2026-07-03-nebulosabot-foundation`, `2026-07-07-default-ticket-categories-and-smoke-fixes`, `2026-07-08-audit-code-arch-tooling`, `2026-07-08-audit-product-ux-tickets`, `2026-07-09-cloudflare-webhook-cleanup`, and `2026-07-09-ticket-panel-persistence`.
- At least 13 archived verification reports contain explicit `FAIL` findings or failure evidence, and 33 contain `PASS WITH WARNINGS` evidence. Four archived task files still contain unchecked task boxes. Archiving has therefore preserved history, but “archived” does not mean “fully green” or “artifact-complete.”

### Active Changes

| Change | Artifact evidence | Implementation alignment |
|---|---|---|
| `ticket-integrity-reconciliation` | 13 delta specs, 44 requirements, 103 scenarios; `tasks.md` is fully checked; `apply-progress.md` says READY through PR4/C25; no `verify-report.md`. | `bot/models/ticket.py`, `integrity_report.py`, conditional DB close, and repair primitives exist. `audit_listener.py` remains logging-only; no `ops/` directory, no `bot/services/ticket_integrity.py`, no sweep wiring, and no manual repair command exist. |
| `ticket-integrity-recovery` | 3 delta specs, 11 requirements, 44 scenarios; `tasks.md` has 28/45 boxes checked; phases 3–5 plus E.1/E.2 remain unchecked; apply progress explicitly says PR3+ are out of scope. | PR1/PR2 primitives are present in the staged worktree. The active change is incomplete by its own task contract and lacks `verify-report.md`. |

The two active changes overlap on the same lifecycle contracts while disagreeing on phase completion and artifact ownership. The reconciliation change appears to have promoted future work to “complete” in metadata without corresponding implementation or independent verification.

## Known Failing Test Classification

`tests/contract/test_ticket_invariants.py::test_ti020_audit_every_denied` was executed both with the configured runner and with `--no-cov`; it fails in both runs at the already-closed close case.

Evidence:

- The test fixture sets `db.get_ticket.return_value` to a closed row but does not configure `db.transition_ticket_to_closed` (`tests/contract/test_ticket_invariants.py:72-91, 473-477`).
- Current `TicketService.close_ticket()` intentionally calls the conditional `transition_ticket_to_closed()` first and raises only when that transition returns `None` (`bot/services/ticket_service.py:173-230`).
- The current service/DB contract is therefore not reached by the stale fixture: an unconfigured `AsyncMock` transition yields a truthy mock instead of the closed-row denial path.
- The active reconciliation exploration already identified this exact mismatch and recommended configuring the transition mock, but the test remains failing in the current worktree.

**Disposition:** this is primarily **test drift caused by incomplete active-change reconciliation**, not evidence that the real conditional-close implementation accepts a closed ticket. It is still a release-blocking contract failure because the required aggregate invariant suite does not prove TI-020. No fix was applied.

## Post-Exploration Correction (2026-08-11)

This note is appended after the read-only snapshot above and does not rewrite
the findings, which remain accurate for the instant they describe.

A subsequent scoped continuation under `ticket-integrity-recovery` (work unit
`ti020-contract-fixture-normalization`) changed the contract fixture and
recovery metadata:

- `tests/contract/test_ticket_invariants.py`: `_contract_db()` now models
  `transition_ticket_to_closed` status-aware — it returns `None` unless the
  ticket's status is in `expected_statuses`, replacing the truthy bare
  `AsyncMock` that hid the already-closed denial path. This is the exact fix
  the "Known Failing Test Classification" section above recommended.
- `openspec/changes/ticket-integrity-recovery/tasks.md` and
  `apply-progress.md`: PR2 tasks (2.1–2.6) are marked complete with matching
  implementation evidence; phases 3–5 and E.1/E.2 remain unchecked.
  `ticket-integrity-reconciliation` metadata was not modified.

Focused verification (native attempt authority, 2026-08-11):
`uv run pytest --no-cov tests/contract/test_ticket_invariants.py::test_ti020_audit_every_denied -q`
→ `1 passed`; smallest adjacent proof `uv run pytest --no-cov tests/contract/test_ticket_invariants.py -q`
→ `41 passed, 3 skipped`. The snapshot's "remains failing in the current
worktree" statement was accurate for the snapshot instant and is retained
unchanged as history; it is no longer the current state.

## Root-Class Gap Matrix

| Intended capability | Artifact evidence | Implementation evidence | Test evidence | External-contract evidence | Disposition | Severity / impact | Confidence | Recommended next SDD action |
|---|---|---|---|---|---|---|---|---|
| A coherent, auditable SDD lifecycle | `openspec/config.yaml:12-59`; 49 archives; active reconciliation marked complete without verify; recovery leaves phases unchecked. | Active metadata and product code disagree; current branch contains staged/uncommitted work. | Full suite has one failure; no active-change verification report exists. | None required. | Root governance/provenance drift. | **High** — unsafe to select the next feature from unchecked claims. | **High** | Create a small artifact-truth/verification cluster first; reconcile status, provenance, and archive completeness before more product work. |
| Reliable ticket lifecycle and zombie-ticket recovery | Active `ticket-integrity-*` specs require conditional close, channel-delete detection, bounded sweeps, manual repair, G.2 gating, and auditability. | Conditional close, evidence, preflight, and service repair primitives exist. `on_guild_channel_delete` only logs (`bot/listeners/audit_listener.py:117-139`); no sweep/manual repair/ops SQL wiring is present. | TI-020 fails; active recovery explicitly leaves phases 3–5 and E.1/E.2 pending. | Supabase migration/realtime readiness cannot be verified live. | Incomplete active capability; artifact implementation disconnect. | **Critical** — deleted Discord channels can leave active ticket rows and no user/operator repair path. | **High** | Finish one bounded ticket-integrity cluster: contract fixture, event detection, sweeps/manual fallback, fresh G.2/E.2 evidence, integration verification, then archive. |
| Denied operations are auditable | Main `ticket-invariants` and active reconciliation require every denied operation to write a non-empty denied audit row. | `close_ticket` now has a best-effort denied audit path, while other service operations use per-operation invariant checks. | Aggregate TI-020 cannot exercise the close denial path because its mock models the old API. `TicketAuditDBMixin` has no direct covering tests in CodeGraph. | `ticket_audit` RLS is enabled in migration 012, but live policy state is unavailable. | Contract evidence is incomplete; implementation is not disproven. | **High** — audit gaps undermine support, incident response, and trust. | **High** | Update the contract evidence under the active change, add DB/audit failure and guild-scope cases, and verify every denied path against the canonical API. |
| Multi-guild, safe configuration onboarding | `setup-wizard`, `guild-config`, `dashboard-ticket-view`, and manual quick-start specs require admin setup and guild-scoped values. | `/setup` is admin-gated and preserves omitted fields (`bot/cogs/setup.py:37-126`); dashboard actions re-check Discord admin and filter by `guildId`. Dashboard accepts 10 language codes (`dashboard/lib/actions/guild-actions.ts:11-13`), but the bot accepts `Literal["es", "en"]` and only `bot/locales/en.json`/`es.json` exist. | Setup/action tests pass; direct coverage for several dashboard page/auth helpers is absent in CodeGraph. | Next.js 15 async route params are used correctly and the build passes. | Partial parity; supported-language contract is contradictory. | **High** — admins can save a language the bot cannot render, producing fallback or inconsistent UX. | **High** | Define one supported-language contract across dashboard, `/setup`, locale assets, specs, and tests; add a guided validation path rather than raw ID entry alone. |
| Dashboard parity with the Discord product | Diagram and manual imply unified server management; `dashboard-ticket-view` requires read-only ticket monitoring plus notes/audit and safe reopen guidance. | Dashboard has overview/config/economy/greeting/tickets, ticket notes/audit/actions, but no dashboard moderation, ticket-category/panel setup, or ticket-integrity report/repair surface. | 240 dashboard tests pass; `AuditPanel` and several server auth/page boundaries have no direct test relationship; build/typecheck pass. | Next.js App Router route handlers and async params match current docs. | Implemented observation/config slice, not full operator parity. | **Medium-High** — “manage everything from one place” is false for moderation and ticket operations. | **High** | Cluster dashboard parity after auth/config contract: choose an explicit dashboard scope and close the highest-value Discord/dashboard gaps without creating a second business-logic owner. |
| Consistent cache and realtime behavior | `cache-layer`, `cache-sync-realtime`, and `DiagramaSecuencia.mmd` promise cache-first reads and CDC invalidation. | TTL cache is guild-scoped with 300-second expiry. Realtime subscribes/publication covers only `guild`, `greeting_config`, `ticket`, `ticket_note`; economy config is read directly from DB, and ticket audit/category/member changes have no CDC subscription. | Realtime unit tests pass as part of the suite; no live CDC/publication verification was possible. GitHub PR #51 explicitly says the publication must include required tables for multi-instance sync. | Supabase Realtime depends on published tables; Supabase docs also recommend explicit filters and correct RLS/client boundaries. | Partially implemented architecture; operational readiness unproven. | **Medium-High** — stale state or silent invalidation loss appears when future cached entities are added or multi-instance behavior is used. | **High** for table mismatch; **Medium** for production impact | Add a data-consistency/operations cluster that defines the cache ownership table, publishes every cached entity, proves degraded behavior, and records live subscription evidence. |
| Secure server-side data access and guild isolation | `permission-model`, `rpc-least-privilege`, `dashboard-ticket-view`, and AGENTS.md require runtime checks and guild filters. | Bot checks both invocation paths. Dashboard server actions use service-role clients only after session + Discord administrator checks and guild filters; service client is server-only (`dashboard/lib/supabase.ts:55-90`). Migrations enable RLS on `ticket_note`/`ticket_audit` but repository SQL contains no corresponding `CREATE POLICY`. `.env.example` ambiguously permits “anon or service_role”. | Permission and dashboard action tests pass, but no direct live RLS/auth test; CodeGraph reports no direct coverage for `verifyGuildAdmin`/`resolveTicketGuild`. | `app_commands.default_permissions` is only a Discord client hint, not a strict check; service-role keys bypass RLS and must remain server-only. Current code correctly adds runtime checks, but the RLS boundary is fragile. | Mostly compliant defense-in-depth with a high-risk evidence gap. | **High** security impact if any server action bypasses its helper or if credentials are misconfigured. | **High** for contract facts; **Medium** for exploitable production behavior | Add an auth/RLS contract cluster with live policy inventory, service-role configuration validation, direct negative tests, and one shared guild authorization helper. |
| Schema and RPC contracts remain deployable | `initial-schema` states a three-argument `set_member_daily`; `rpc-least-privilege` describes the function generically. | `migrations/009_member_increment_rpc.sql` and `bot/core/db/economy_db.py` define/call six arguments for `set_member_daily`; migration 010 revokes the six-argument signature. Migration 012 is labeled idempotent but contains a backup-table creation, data update, and cron scheduling. | Structural migration tests pass locally, but no live migration/advisor query succeeded. | Supabase/Postgres security and RLS semantics make function signatures and `SECURITY DEFINER` search paths deployment-critical. | Main spec/data contract drift plus an idempotence claim that needs explicit deployment proof. | **High** operational impact on fresh installs, migration replay, and RPC access. | **High** | Create a schema-contract cluster: canonical signatures, migration replay semantics, RLS policies, live migration inventory, and advisor-backed proof. |
| Economy and utility deliver user value | Manual and `economy-*`/`utility-*` specs cover daily coins, XP, rankings, rank cards, avatar/server/user info, dice, and banana. | Stellar, XP listener, utility, and ocio cogs/services are registered and implemented; no material utility blocker was found. Economy configuration is dashboard-editable but behavior remains Discord-only. | Economy, utility, image, property, integration, and i18n tests pass within the full run. | No external contract needed beyond normal Discord/Supabase behavior. | Largely implemented; evidence is stronger for Discord behavior than dashboard/operator workflows. | **Medium** — core engagement works, but configuration and live end-to-end proof are weaker than unit evidence. | **High** | Keep as a verification slice inside the dashboard/data-consistency cluster; do not create separate changes for each command. |
| Resilient, observable operations | `bot-core`, `logging-service`, `audit-listener`, `cache-sync-realtime`, and AGENTS.md require graceful errors, logging, and degraded operation. | Extension loading continues after failures; Realtime degrades to TTL-only; audit/logging services exist. Ticket audit DB mixin lacks direct coverage; active integrity repair has no event/sweep observability. | Dashboard tests emit React 19 `act(...)` warnings; `uv run ruff check .` fails 30 findings; full Python suite is not green. | React 19 guidance requires state updates to be flushed with `act`; discord.py sync/default-permission behavior was verified through current docs. | Resilience exists in local seams, but verification noise and missing operational probes reduce trust. | **Medium** — failures are visible but not yet unified into an operator health model. | **High** | Add observability/test-hygiene work to the data-consistency cluster: warning-free dashboard tests, explicit health/readiness evidence, and direct audit/realtime failure tests. |
| Product roadmap is understandable to maintainers and users | Manual, diagrams, 62 specs, and archive history are all candidate sources of truth. | No root `README.md` or `PRODUCT.md`; `pyproject.toml` points at a README that is absent locally and its repository URL names `gentle-programming/NebulosaBot`, while the actual origin is `danielxxomg/NebulosaBot`. | `test_manual.py` protects command descriptions but cannot resolve broader product-intent contradictions. | GitHub has one open temporary test issue (#52), no open PRs, no releases, and recent PRs #49/#51 document merged i18n/security work plus unresolved operational follow-ups. | Documentation/product-intent gap; historical artifacts are overburdened as roadmap. | **Medium** — slows prioritization and makes stale artifacts look authoritative. | **High** | Resolve product scope before feature proposals: publish one authoritative intent/roadmap artifact and mark diagrams/specs as shipped, deprecated, or aspirational. |

## External and Current-Contract Evidence

Context7 library IDs were resolved before retrieval. Sources were retrieved on **2026-08-11**. No separate web lookup was needed because Context7 covered the external claims below.

| Library / source | Current contract used in this audit | Repository comparison |
|---|---|---|
| discord.py — `/websites/discordpy_readthedocs_io_en` | `@app_commands.default_permissions` is a client-facing hint and administrators can override it; runtime checks are required. Hybrid commands require explicit `CommandTree.sync()`. Sources: [interactions API](https://discordpy.readthedocs.io/en/latest/interactions/api.html), [hybrid commands](https://discordpy.readthedocs.io/en/latest/ext/commands/commands.html), [FAQ sync](https://discordpy.readthedocs.io/en/latest/faq.html). | NebulosaBot correctly combines default permission hints with `is_admin()`/`is_mod()` runtime checks and syncs in `setup_hook()`/`/sync`. |
| Next.js — `/vercel/next.js` | Next.js 15 makes `params` and `searchParams` asynchronous; App Router route handlers use named async HTTP methods; server fetch/cache semantics are explicit. Sources: [version 15 upgrade](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/upgrading/version-15.mdx), [route handlers](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/03-file-conventions/route.mdx), [fetch](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/04-functions/fetch.mdx). | Dashboard pages use `params: Promise<...>` and `await`; the auth callback exports `GET`; build/typecheck pass. Cache/revalidation policy is not documented as one cross-surface contract. |
| React — `/react/react` | React 19 requires stateful test interactions to be wrapped with `act`; `ReactDOMTestUtils.act` is deprecated in favor of `React.act`. Source: [React nested event test](https://github.com/react/react/blob/main/packages/react-dom/src/__tests__/ReactDOMNestedEvents-test.js) and [React act warning](https://react.dev/warnings/react-dom-test-utils). | Dashboard tests pass but emit repeated `AuditPanel` act warnings, so test evidence is green but not warning-clean. |
| Supabase — `/supabase/supabase` | Realtime Postgres changes require the relevant tables in the publication; service-role clients bypass RLS and must never reach browser code; explicit query filters remain important. Sources: [RLS guide](https://github.com/supabase/supabase/blob/master/apps/docs/content/guides/database/postgres/row-level-security.mdx), [browser client/RLS example](https://github.com/supabase/supabase/blob/master/examples/user-management/react-user-management/src/supabaseClient.js), [Realtime listener example](https://github.com/supabase/supabase/blob/master/apps/www/_blog/2024-05-09-meetup-kahoot-alternative.mdx). | Dashboard service clients are server-only and actions filter guild IDs. Realtime publication/subscriptions cover four tables only, and live RLS/publication state could not be queried. |

## GitHub and MCP Evidence

- Git remote: `https://github.com/danielxxomg/NebulosaBot.git`; repository description: “Discord bot with web dashboard and QA tooling.”
- GitHub `master` is `456d496`, while the audit worktree is the recovery feature branch at `e68896a` with staged ticket changes and active SDD metadata edits.
- GitHub reports no open pull requests and one open issue, [#52](https://github.com/danielxxomg/NebulosaBot/issues/52), explicitly a temporary GitHub MCP permission test.
- [PR #51](https://github.com/danielxxomg/NebulosaBot/pull/51) merged the dual-path permission fix, ticket limit ordering, benign close `NotFound`, and one-time Realtime watchdog warning. Its operations note explicitly says the Supabase Realtime publication must include cache tables for multi-instance sync.
- [PR #49](https://github.com/danielxxomg/NebulosaBot/pull/49) merged the final i18n slice and documented deploy plus `/sync` as an operational follow-up.
- No GitHub releases were returned.

Supabase MCP could discover project `nebulosabot` (`vozkcckiybebhcclrasa`, `sa-east-1`), but live database reads were unavailable. Exact limitations: migration listing failed with `28P01 password authentication failed for user "postgres"`; table/extension reads failed with `password authentication failed for user "supabase_read_only_user"`; security/performance advisors reported the project as hibernated. Consequently, production migration status, RLS policies, publication membership, and live ticket/channel evidence remain unverified; G.2 must stay unresolved.

## Approaches

1. **Evidence-first root-class clusters (recommended)** — Establish artifact truth and verification status, then finish ticket integrity, configuration/auth parity, dashboard scope, and data-consistency work in dependency order.
   - Pros: Prevents stale SDD claims from driving implementation; fixes systemic classes instead of symptoms; keeps the 800-line review budget meaningful.
   - Cons: Delays new user-facing features until active ticket work and product scope are explicit.
   - Effort: High

2. **Continue the active ticket change immediately** — Treat `ticket-integrity-reconciliation` as authoritative and implement its checked tasks without first correcting the registry, missing artifacts, and stale contract test.
   - Pros: Shortest path to the highest-impact product defect.
   - Cons: Repeats the failure mode this audit found: checked metadata without verified implementation, overlapping APIs, missing live evidence, and an already-failing aggregate contract.
   - Effort: High, with high rework risk

## Recommendation

Use the evidence-first approach. The first follow-up should be a bounded artifact-truth and verification gate, not another implementation slice. It should classify the 49 archives, reconcile the two active ticket changes into one authoritative lifecycle, correct the TI-020 contract harness, and record the exact live-evidence limitation without claiming G.2 resolution. Then deliver four coherent clusters: ticket integrity completion; configuration/auth/dashboard parity; data consistency/RLS/Realtime; and product-intent/documentation cleanup. Do not create one change per row in the matrix.

## Risks

- The worktree is intentionally dirty and includes staged active product changes; conclusions are for this snapshot, not necessarily `origin/master`.
- Supabase production state could not be read, so migration application, RLS policy coverage, Realtime publication membership, and ticket #3 corroboration are unknown.
- The current Python suite is not green even though it exceeds the coverage threshold; the failing contract must not be silently normalized as “expected.”
- Archive reports contain historical failures and partial evidence; archive presence alone is not proof of product behavior.
- Product intent is split across Spanish manual text, diagrams, OpenSpec, and GitHub history; a maintainer decision is required before treating giveaway/web-profile references as roadmap commitments.

## Ready for Proposal

Yes, for the first bounded follow-up cluster only after the maintainer accepts the audit dispositions. The next SDD action should be a proposal for artifact truth/verification and active ticket-integrity reconciliation as one dependency-aware cluster; no proposal, spec, design, tasks, or product-code change was created in this exploration.
