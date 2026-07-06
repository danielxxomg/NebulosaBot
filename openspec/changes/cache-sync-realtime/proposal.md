# Proposal: Cache Sync Realtime

## Intent

Replace inbound webhook (Cloudflare Tunnel + HMAC) with outbound Supabase Realtime CDC. Same invalidation, zero public exposure.

## Scope

### In Scope
- `bot/core/realtime.py` — subscriber: `acreate_client`, 4 tables (guild, greeting_config, ticket, ticket_note), `on_subscribe` health, poll fallback 30s
- `bot/core/database.py` — async client for Realtime; sync client untouched
- `bot/bot.py` — wire in `setup_hook`
- Self-echo filtering (TBD in design — recent-writes set)
- Delete `bot/webhook/*` (4) + `tests/test_webhook_*.py` (3)
- Dashboard: delete `webhook-sync.ts`, remove `notifyWebhookSync()` from 3 actions
- Env: drop `WEBHOOK_URL/SECRET/HOST/PORT`, `TUNNEL_TOKEN`
- `app.py` → bot-only (< 20 lines)
- Migration: `alter publication supabase_realtime add table guild, greeting_config, ticket, ticket_note;` — **PREREQUISITE** (0 tables published)

### Out of Scope
- B5 invariant layer, debt #545, `member` table (30s TTL), Pterodactyl

## Capabilities

### New Capabilities
- `cache-sync-realtime`: Realtime CDC subscriber replacing `cache-sync-webhook`

### Modified Capabilities
- None — `cache-layer` unchanged; `cache-sync-webhook` fully replaced

## Approach

1. Async client (`acreate_client`) in `database.py`
2. `realtime.py`: subscription + health + fallback
3. Wire `setup_hook`
4. Run migration
5. Delete webhook/dashboard sync code + env vars
6. Simplify `app.py`

## Affected Areas

| Area | Impact |
|------|--------|
| `bot/core/realtime.py` | New |
| `bot/core/database.py` | Modified |
| `bot/bot.py` | Modified |
| `bot/webhook/*` | Removed |
| `bot/config.py` | Modified |
| `app.py` | Modified |
| `dashboard/lib/webhook-sync.ts` | Removed |
| `dashboard/lib/actions/*.ts` | Modified |
| `.env.example` | Modified |
| `dashboard/.env.local.example` | Modified |

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Sync/async client confusion | Med | Separate async client |
| WS silent disconnect | Med | Health check + poll fallback |
| Self-echo filtering | Med | Deferred to design |
| Migration not run | High | Block start; log error |

## Rollback Plan

Restore webhook files + env vars from git. Re-enable cloudflared. Drop tables from publication.

## Dependencies

- supabase-py >= 2.0 (exists)
- Migration SQL applied first

## Success Criteria

- [ ] CDC events received within 5s of dashboard write
- [ ] No tunnel; no inbound ports
- [ ] Zero webhook references in codebase
- [ ] `app.py` < 20 lines
- [ ] All tests pass
