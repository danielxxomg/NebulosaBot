# Archive Report: webhook-sync

**Change**: `webhook-sync`
**Archived**: 2026-07-03
**Status**: PASS WITH WARNINGS

## Change Summary

Implement dashboard-to-bot webhook cache sync: when the dashboard writes guild config, economy config, or greeting config to Supabase, a signed HTTP POST notifies the bot to invalidate its in-memory TTL cache, closing the 5-minute stale-cache gap.

## PRs

| PR | Branch | Status | Description |
|----|--------|--------|-------------|
| #9 | `feat/webhook-sync-pr1` | Merged to master | Bot-side: webhook module (auth, models, server), config fields, setup_hook lifecycle, .env.example, aiohttp reconcile |
| #10 | `feat/webhook-sync-pr2` | Closed/replaced | Original dashboard PR — closed during stacked-PR merge workflow |
| #11 | `feat/webhook-sync-pr2` | Merged to master | Dashboard-side: webhook helper, action wirings (guild/economy/greeting), env examples, tests |

## Verify Verdict

**PASS WITH WARNINGS** (verify-report.md)

- 13/13 tasks complete
- 430 bot tests pass (77.65% coverage), 89 dashboard tests pass
- All gates pass: lint, type, security, tsc
- 18/19 spec scenarios fully compliant; 1 partial (no single integration test chaining webhook invalidation → service read)
- No CRITICAL issues

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| `cache-sync-webhook` | Created | NEW spec copied from delta (7 requirements, 14 scenarios) |
| `guild-config` | Updated | 1 ADDED requirement (Dashboard webhook notification) + 2 scenarios appended |
| `economy-service` | Updated | 1 ADDED requirement (Dashboard webhook notification) + 2 scenarios appended |
| `greeting-config` | Updated | 1 ADDED requirement (Dashboard webhook notification) + 2 scenarios appended |

## Source of Truth Updated

- `openspec/specs/cache-sync-webhook/spec.md` — created
- `openspec/specs/guild-config/spec.md` — merged
- `openspec/specs/economy-service/spec.md` — merged
- `openspec/specs/greeting-config/spec.md` — merged

## Archive Contents

- `proposal.md` ✅
- `exploration.md` ✅
- `specs/cache-sync-webhook/spec.md` ✅
- `specs/guild-config/spec.md` ✅
- `specs/economy-service/spec.md` ✅
- `specs/greeting-config/spec.md` ✅
- `design.md` ✅
- `tasks.md` ✅ (13/13 tasks complete)
- `apply-progress.md` ✅
- `verify-report.md` ✅
- `state.yaml` ✅

## Deferred Follow-ups

1. **Integration test**: Add one test that chains webhook invalidation → service read to prove full DB repopulation path (warn in verify-report).
2. **Dashboard coverage**: Configure vitest coverage measurement (pre-existing tooling gap).
3. **`next lint`**: Configure ESLint in dashboard (pre-existing — interactive setup prompt).
4. **`discord.py` drift**: `requirements.txt` pins 2.4.0 vs `uv.lock` resolves 2.7.1 — pre-existing, out of this change's scope.
5. **`design.md` staleness**: Design still references `BOT_WEBHOOK_URL` (impl uses `WEBHOOK_URL`) and required-looking `entity` field (impl sends guild_id-only). Documented in verify-report; not blocking.

## Files Touched (implementation, for traceability)

**Bot (PR #9):**
- `bot/webhook/__init__.py`, `bot/webhook/auth.py`, `bot/webhook/models.py`, `bot/webhook/server.py` (new)
- `bot/config.py`, `bot/bot.py` (modified)
- `tests/test_webhook_auth.py`, `tests/test_webhook_models.py`, `tests/test_webhook_server.py` (new)
- `tests/test_config.py`, `tests/test_bot.py` (modified)
- `.env.example`, `requirements.txt` (modified)

**Dashboard (PR #11):**
- `dashboard/lib/webhook-sync.ts` (new)
- `dashboard/__tests__/lib/webhook-sync.test.ts` (new)
- `dashboard/lib/actions/guild-actions.ts`, `dashboard/lib/actions/economy-actions.ts`, `dashboard/lib/actions/greeting-actions.ts` (modified)
- `dashboard/__tests__/lib/actions/guild-actions.test.ts`, `dashboard/__tests__/lib/actions/economy-actions.test.ts`, `dashboard/__tests__/lib/actions/greeting-actions.test.ts` (modified)
- `dashboard/.env.local.example`, `dashboard/.env.example` (modified)

**CI:**
- `.github/workflows/ci.yml` (modified — added dashboard-tests job)
