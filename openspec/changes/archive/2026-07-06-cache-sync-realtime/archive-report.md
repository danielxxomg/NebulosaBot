# Archive Report: Cache Sync Realtime

**Change**: cache-sync-realtime
**Date**: 2026-07-06
**Branch**: `cache-sync-realtime-pr2`
**Artifact store**: openspec
**Verify verdict**: PASS

---

## Summary

Replaced the inbound webhook (Cloudflare Tunnel + HMAC) with an outbound Supabase Realtime CDC subscriber for cache invalidation. Same invalidation semantics, zero public exposure. The change was delivered across two stacked PRs covering 45 tasks in 7 phases plus a fixup.

### PR 1 (Phases 1-4): Migration + Realtime subscriber core
- Added Supabase Realtime CDC subscriber (`bot/core/realtime.py`) with health monitoring, poll fallback, self-echo filtering, and migration watchdog.
- Database factory for async Realtime client (`bot/core/database.py`).
- Bot wiring: subscriber starts in `setup_hook`, stops on `close()` (`bot/bot.py`).
- Migration: 4 tables added to `supabase_realtime` publication (idempotent).
- 68 Realtime tests in `tests/test_realtime.py`.

### PR 2 (task 3.12 fixup + Phases 5-7): Webhook removal + cleanup
- Fixed poll-task lifecycle: cancel on WebSocket recovery, recreate on later unhealthy status (task 3.12 fixup).
- Deleted `bot/webhook/*` (4 files) and `tests/test_webhook_*.py` (3 files).
- Deleted `dashboard/lib/webhook-sync.ts` + its test.
- Removed `notifyWebhookSync()` calls from 3 dashboard action files.
- Simplified `app.py` to 19 lines (bot-only entry point).
- Cleaned all webhook/tunnel env vars from all 3 `.env` templates.
- Resolved P0 found during fresh-context verify: stale `WEBHOOK_URL`/`WEBHOOK_SECRET` in `dashboard/.env.example` (commit `f8df959`).

---

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| `cache-sync-realtime` | Created | New capability spec with 6 requirements (lifecycle, CDC invalidation, reconnection/health, poll fallback, self-echo filtering, migration prerequisite) |
| `cache-sync-webhook` | Replaced | Original 6-requirement webhook spec replaced with deprecation spec (6 REMOVED requirements with Reason/Migration notes) |

---

## Archive Contents

- `proposal.md` ✅
- `specs/cache-sync-realtime/spec.md` ✅
- `specs/cache-sync-webhook/spec.md` ✅
- `design.md` ✅
- `tasks.md` ✅ (45/45 tasks complete)
- `verify-report.md` ✅
- `archive-report.md` ✅ (this file)

---

## Source of Truth Updated

The following main specs now reflect the new behavior:
- `openspec/specs/cache-sync-realtime/spec.md` — new capability (Supabase Realtime CDC)
- `openspec/specs/cache-sync-webhook/spec.md` — deprecated (replaced by cache-sync-realtime)

---

## Verification Evidence

| Check | Result | Evidence |
|-------|--------|----------|
| Python test suite | 580 passed | 7.87s, coverage 78.52% (≥70% gate) |
| Realtime targeted suite | 68 passed | 0.08s |
| PR 2 guard suite | 22 passed | 0.05s |
| Dashboard test suite | 152 passed | 1.14s (11 files) |
| Poll-recovery focused | 2 passed | 0.01s |
| Webhook code absent | Confirmed | `bot/webhook/*`, `dashboard/lib/webhook-sync.ts` deleted |
| Webhook env clean | Confirmed | All 3 `.env` templates have zero webhook/tunnel vars |
| Spec compliance | 16/16 requirements compliant | Full matrix in verify-report.md |

---

## Commit SHAs

### PR 1
- `a20e9f0` feat(realtime): add Supabase CDC subscriber replacing webhook
- `9e61b2e` feat(realtime): add subscriber tests and migration
- `cb87cb1` chore(openspec): add cache-sync-realtime delta specs
- `8b465ec` fix(realtime): ensure synchronous on_subscribe callback
- `324b0c3` fix(realtime): poll task lifecycle (cancel on recovery, recreate on unhealthy)

### PR 2
- `7a1d666` fix(realtime): task 3.12 fixup — poll task cancel/recreate
- `b18c79f` refactor(webhook): remove webhook capability
- `ec95a3c` refactor(dashboard): remove webhook-sync and notifyWebhookSync calls
- `1e670fa` refactor(app): simplify app.py to bot-only entry point
- `f8df959` fix(dashboard): remove stale webhook env vars from .env.example

### Openspec chore commits
- Chained PR openspec artifacts co-located with implementation commits.

---

## Residual Warnings

1. **Ruff inherited debt**: 10 findings in pre-existing files not touched by this change (`bot/cogs/core.py`, `bot/cogs/sentinel.py`, `bot/services/*`, `bot/utils/checks.py`, `tests/test_logging_service.py`). Non-blocking per GGA diff-scope rule.
2. **Changed-file coverage**: `bot/bot.py` at 73% and `bot/core/database.py` at 67% are below strict 80% changed-file guidance, though project coverage (78.52%) exceeds the configured 70% gate.
3. **No live CDC event**: Realtime behavior verified by unit tests + Supabase publication state, not an end-to-end dashboard write. Residual risk, acceptable for archive.

---

## SDD Cycle Complete

The change has been fully planned, implemented, verified, and archived.
Ready for the next change.
