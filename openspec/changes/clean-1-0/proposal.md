# Proposal: clean-1.0 — Everything Clean Before v1.0.0

## Intent

Ship v1.0.0 with zero known defects, leaks, or unbounded growth. Today: automatic tempban expiry is dead (`infraction_db.py:199` `neq("expiresAt", None)` → PostgREST 22007), the Discord-token prefix is logged at INFO (`config.py:279`), permission denials surface as unhandled errors, transcripts rot on expiring Discord CDN URLs, DB tables grow forever (ticket/infraction/member), config UX is orphaned raw-UUID commands, and every command is legacy hybrid. All decisions locked through 3 grill rounds (ledger #4845 chain).

## Scope

### In Scope — ordered slices, one chained PR each (stacked-to-main)

| Slice | Deliverables | ~Lines |
|------|--------------|--------|
| S0 | tempban `not_.is_` fix + real PostgREST serialization test; ticket-timer `unix=` kwarg; CheckFailure/MissingPermissions→ephemeral reply; transfer-to-self UI pre-validation + log ERROR→WARNING; zombie-ticket auto-close + audit entry; remove token fragment from INFO log; /rank cooldown + shared semaphore; cache/semaphore eviction quick wins; gate flips: betterleaks blocking, coverage floor 80, GGA hook includes `tests/` | 450 |
| S1 | Transcript triple-path: DM HTML to creator + private Storage copy TTL 30d + existing log-channel post | 350 |
| S2a | `/setup` persistent non-ephemeral panel (single edited message, Select nav, breadcrumb, refresh, pending list, 🗑 close, static custom_ids + `bot.add_view`, matrix key + `default_permissions(administrator)`); Tickets module absorbs create/delete/list categories + guided fields editor (no raw UUID/JSON) | 800 |
| S2b | Setup modules Welcome/Goodbye/Log/Language exposing orphan columns (`cardEnabled`, `themeId`, `onboardingChannelId`); test buttons send real previews to configured channel (auto-closing self-deleting ticket); delete `/welcome`+`/goodbye` groups and `*_test` after parity | 500 |
| S3 | pg_cron retention: closed tickets+notes 30d global-configurable (sub-tickets before parents), inactive infractions 180d except permanent BANs kept forever, `crash_report` TTL 30d (unhandled exceptions + critical only); index `member(updatedAt)`; drop dup `idx_ticket_note_created`; private bucket | 400 |
| S4 | `config.toml` tomllib restart-only typed loader (logging, limits, timeouts, retention defaults, flags) + RotatingFileHandler 10MB×5; guild config/secrets stay in .env/DB | 350 |
| S5 | PLC0415 sweep (~25 sites); dead i18n key purge; rank_renderer t() routing; close_ticket dual-branch dedup; cache-layer spec ↔ CDC reality sync; governance_guard.py deletion; `.betterleaks.toml` env-rule scoping; CI binary SHA pins; test_live_catalog cleanup | 400 |
| S6 | Migrate ~30 surviving hybrids to pure app_commands (split PR if >1500); `/dados`→`/dice` (es localization); `/8ball`+`/banana` permanent (zero DB writes, cooldowns kept); delete `/sync` | 1000–1200 |

### Out of Scope (parking lot, post-1.0)
Multi-template greetings; full mega-test split (opportunistic splits allowed); member PII policy; voice-states track; mutmut; dashboard QA; ops-zero items (watchdog/docker/backup-cron). Never touch `TicketsCog.on_message` `,` close-timer parsing (close-confirmation invariant).

## Capabilities

**New:** `setup-panel` (persistent panel framework + module nav); `data-retention` (pg_cron TTLs, crash_report, index fixes); `operational-config` (toml loader + rotating file logging).

**Modified:** `setup-wizard` (panel replaces param command; Tickets module absorbs category/field management); `welcome-goodbye` (config via setup modules; legacy groups + `*_test` deleted); `transcript-service` (triple-path delivery); `ocio-commands` (/dice rename; permanence); `ephemeral-standard` (fun-command flips; error-handler branches); `bot-core` (CheckFailure/MissingPermissions→ephemeral); `core-commands` (/sync removed); `permission-model` (new setup matrix key); `cache-layer` (eviction; CDC doc sync); `ticket-service` (zombie auto-close).

## Approach

Slice order fixed (F1): stability/security first, then product UX, then infrastructure/debt/migration. Strict TDD RED→GREEN per work unit; ≤1500 changed lines per PR; small semantic commits; single writer; delete-before-migrate ordering in S3.

## Affected Areas

| Area | Impact |
|------|--------|
| `bot/core/db/infraction_db.py`, `bot/config.py`, `bot/cogs/ticket_lifecycle_flow.py` | Modified (S0) |
| `bot/services/transcript_service.py`, migrations/ | New delivery paths, retention DDL |
| `bot/cogs/setup*.py`, `bot/views/setup*` | New panel + modules; delete greeting command cogs |
| `bot/config.py`, `logging bootstrap` | toml loader + RotatingFileHandler |
| `migrations/NNN_*.sql` | pg_cron jobs, indexes, crash_report |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| PostgREST serialization differs under fake builders | Med | Real serialization test against query-string (S0) |
| pg_cron purge deletes wrong rows | Low | Sub-tickets-before-parents ordering; global flag default conservative; integration tests |
| Persistent views lost on restart edge cases | Low | Static custom_ids + add_view in setup_hook; tests |
| S6 volume exceeds budget | Med | Split into two chained PRs (pre-approved) |

## Rollback Plan

Each slice is one stacked PR; revert the individual merge commit. S3 DDL is idempotent (`IF NOT EXISTS`) and additive; disable cron jobs via `unschedule` before revert. S4 loader falls back to current env-only behavior when `config.toml` absent.

## Dependencies

Supabase Storage private bucket + pg_cron extension available; no new Python deps (tomllib is stdlib 3.11).

## Success Criteria

- [ ] No known runtime errors from logs.txt triage reproduce
- [ ] Token never logged at any level; betterleaks blocking green; coverage ≥80%
- [ ] Tempbans auto-expire (integration-proven serialization)
- [ ] All config achievable via /setup panel without raw UUIDs/JSON
- [ ] Retention jobs verified; growth bounded
- [ ] Zero hybrid declarations remain (except inert legacy none); `,` timer untouched
