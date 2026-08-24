# Proposal: Cycle 5 — Quality Zero (v1.0 readiness)

## Intent

Drive NebulosaBot to v1.0 readiness by liquidating three debt classes in one cycle: type-safety (495 ty warnings in `tests/`), command-surface policy drift (text commands still invocable against the approved slash-only decision), and consolidated quality blockers/warns — then converge with a full-range GGA review. Evidence base: total-quality audit (3 blockers, 12 warns with file:line), wave-2 pending-area analysis, cycle-5 preflight photo, and the fixed roadmap-grill decisions (slash-only, `nb!` retirement, `,` timer exception, listener rules, i18n standard, brand tokens, perf gate, test-consolidation policy, release order, RLS policy, backup-table DROP).

## Scope

### In Scope

| Slice | Deliverables |
|---|---|
| S0 reference-green | Align versions to 0.9.0 (pyproject vs `bot/__init__.py` drift); parametrize stale hygiene tests; PEP 503 requirements fix; CHANGELOG |
| S1 ty fatal gate | 495→0 warnings in `tests/`, deliberate per-file passes; `[tool.ty.terminal] error-on-warning=true` enabled as LAST commit (closes residual-debt §1) |
| S2 slash-policy / gap-7 | `get_prefix` returns static `[]`; `on_command_error` prefix branch simplified; AGENTS.md L17/18/22/23 rewritten + PLC0415 documented-exception policy + i18n/brand rules codified; ephemeral-standard spec updated (whois→userinfo, stale count removed, DM-first→slash reality); 8 DM-first locking tests KEEP-ADAPTED; help display cleanup |
| S3 quality T1 | LoggingService full i18n (~28 keys ×2 locales, wire orphan `voice.*` keys); InfractionService gains mute/kick/ban mirroring tempban + sentinel callsite swaps; xp_listener role-rewards delegate to service + listener-rule rewording; audit_listener routes ticket close via TicketService with honest docstring; migration 025 DROP exposed `public.ticket_backup_categoryid_text_20260818` + push live (25/25); `/unclaim` documented works-as-designed (claimer-or-mod); AST-based i18n literal enforcement extended |
| S4 robustness/perf | Transcript `_build_html` via `asyncio.to_thread`; greeting raid semaphore/debounce (guild-scoped); `,`-timer per-user 15s debounce (voice_listener pattern); resource-log task (~20ln); economy_config cache-first TTL ~300s + invalidation on save; brand token dedup (TRANSCRIPT_*/CARD_BG_*/LEGACY_BLURPLE/MUTED_TEXT); imgur footer icon dropped |
| S5a ImageService removal | ~775ln: shim, bot.py wiring, GreetingService compat branches + resolve_renderer step2 + TypeError fallback chain, `test_image_service*.py` deleted, mocks updated |
| S5b/c test consolidation | ~3300ln savings: facade merges preserving unique behavioral tests; `economy_math_smoke.py` deleted; i18n pair parametrization (~900ln); `_make_ctx`/`_make_member` factory hoist to conftest (~700ln); cluster parametrizations (~700ln); structural source-grep deletions (~350ln, keep read-only-listener guards + s3d1 guardrails); mock-theater replacement adding embed-content asserts first. RULE: nothing deleted without confirmed behavioral twin |
| S6 CDC member/economy_config | Wire `db._on_write` into member_db/economy_db RPC mutators FIRST (echo-storm prevention); idempotent publication migration (007 DO-block pattern); optional `updatedAt` columns for incremental poll; SUBSCRIBED_TABLES + `_extract_guild_id` cases + poll fallback + tests |
| S7 convergence | Full-range GGA review `v0.9.0-debt-zero..HEAD` (temporary PR_BASE_BRANCH swap + restore; max 2 rounds; efficient re-review base = parent commit of isolated fixes); residual-debt §1+§7 closed with evidence; gap register updated; archive |

### Out of Scope

- Dashboard QA SDD (separate; absorbs prefix-field UI/action removal, dead `dashboard/lib/supabase.ts` createClient() delete, shared assertSession decorator)
- ops-zero micro-SDD (Sentry SDK, task-loop watchdog cog, Docker log rotation doc, GitHub Actions backup cron)
- Voice-states feature (v1.x) · member short-TTL cache (blocked on S6 CDC) · mutmut adoption (deferred)

## Capabilities

> Contract for sdd-spec. Researched against `openspec/specs/`.

### New Capabilities

None.

### Modified Capabilities

- `ephemeral-standard`: whois→userinfo rename; stale 24-command count removed; Prefix-DM-fallback requirement replaced by slash-only reality.
- `bot-core`: hybrid-prefix and comma-alternate-prefix requirements reduced to slash-only; `,` survives solely as ticket-channel timer (`ticket-service` spec unchanged).
- `cache-sync-realtime`: subscriber extends to `member` + `economy_config`; documented deferral requirement superseded; poll fallback gains incremental option.
- `logging-service`: ADDED requirement — log embeds localized per guild language (`voice.*` keys wired).
- `infraction-service`: ADDED mute/kick/ban methods mirroring the tempban/unban method contract.
- `close-confirmation`: explicitly UNCHANGED.

## Approach

Nine stacked slices to main, each within the 800-line review budget, strict TDD (`uv run pytest`, RED-GREEN-REFACTOR per `openspec/config.yaml`). Ordering encodes hard constraints: S6 wires echo suppression into RPC mutators BEFORE the publication ALTER; the S1 fatal gate lands as the final commit of its slice; S7 reviews the entire stacked range. Cache-first + CDC work follows the existing patterns documented in `/Diagramas`.

## Affected Areas

| Area | Impact |
|---|---|
| `bot/bot.py` | Modified — static `[]` prefix, simplified error handler |
| `bot/services/logging_service.py`, `infraction_service.py`, `greeting_service.py`, `economy_service.py`, `ticket_service.py` | Modified |
| `bot/listeners/xp_listener.py`, `audit_listener.py`, `voice_listener.py` | Modified |
| `bot/cogs/sentinel*.py`, `tickets.py`, help/ocio cogs | Modified |
| ImageService module + all wiring | Removed (~775ln) |
| `pyproject.toml`, `requirements.txt`, `CHANGELOG.md`, `bot/__init__.py` | Modified |
| `supabase/migrations/025_*.sql` | Added — destructive DROP of exposed backup table |
| `openspec/specs/{ephemeral-standard,bot-core,cache-sync-realtime,logging-service,infraction-service}` | Delta specs |
| `AGENTS.md` | Policy lines L17/18/22/23 rewritten; PLC0415/i18n/brand rules codified |
| `tests/**` | Net ≈ −3300ln |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| ty-gate unknowns force per-file suppressions | Medium | Suppression permitted only with written rationale |
| GGA provider slow until 2026-08-28 | High (latency only) | S7 latency expected and planned; range review not skipped |
| S5b/c deletions remove real coverage | Medium | Behavioral-twin rule; embed-content asserts added before call asserts removed |
| CDC echo storm if ordering inverted | Medium | `_on_write` wired into RPC mutators before publication ALTER |

## Rollback Plan

Each slice ships as one stacked PR; reverting that PR restores the prior green state. S1's gate commit is last in its slice, so revert restores warning-tolerant ty. Migration 025's DROP is destructive and irreversible at table level: the backup table was ruled disposable in the approved grill decisions; recovery only via DB dump. The publication ALTER is idempotent (re-runnable DO-block) and reversible.

## Dependencies

- GGA reviewer availability (degraded until 2026-08-28)
- Live Supabase access for migration pushes (target 25/25)
- Dashboard QA SDD sequenced independently after this cycle

## Success Criteria

- [ ] `uv run pytest` green at every slice boundary
- [ ] `ty` exit 0 on both `bot/` and `tests/` with the fatal error-on-warning gate enabled
- [ ] Zero text-invocable commands remain except the `,` ticket-channel timer
- [ ] Supabase migrations 25/25 applied live and idempotent
- [ ] Full-range GGA review PASSED within ≤2 rounds
- [ ] residual-debt.md §1 and §7 closed with evidence; gap register updated
