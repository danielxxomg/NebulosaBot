## Exploration: Cloudflare Tunnel / Discord Webhook Residual Cleanup

### Current State

The inbound webhook (Cloudflare Tunnel + HMAC) was **fully replaced** by the outbound Supabase Realtime CDC subscriber in change `cache-sync-realtime` (archived 2026-07-06). The active codebase (`bot/`, `dashboard/lib/`, `app.py`) is clean — no executable webhook code, no tunnel bootstrapping, no inbound HTTP server.

The bot startup path is **gateway-only (WebSocket)** via `app.py` → `bot.__main__.main` → `asyncio.run()`. Cache invalidation flows through `bot/core/realtime.py` (outbound Supabase Realtime WebSocket). Zero inbound ports needed.

### Affected Areas

All residuals are **documentation, diagrams, guard tests, and one untracked local env file**. No executable code is affected.

| # | File | Line(s) | Category | Verdict | Risk |
|---|------|---------|----------|---------|------|
| 1 | `dashboard/.env.local` | 26-29 | **Live deployment artifact** (gitignored) | **UPDATE** — delete lines 26-29 (`WEBHOOK_URL=`, `WEBHOOK_SECRET=`, comment) | None — file is gitignored, not tracked |
| 2 | `Diagramas/DiagramaSecuencia.mmd` | 29 | **Stale diagram** — `Web->>Bot: ⚡ POST /webhook/sync` | **UPDATE** — replace with Realtime CDC flow (`Web->>DB: UPDATE; DB-->>Bot: CDC event`) | None — documentation only |
| 3 | `openspec/specs/cache-sync-webhook/spec.md` | entire file | **Deprecated spec** — already marked DEPRECATED/REMOVED | **KEEP** — historical record of removed capability; referenced by archive reports | None — it's a tombstone spec |
| 4 | `openspec/specs/cache-sync-realtime/spec.md` | 5 | Line mentions "Cloudflare Tunnel + HMAC" in Purpose section | **KEEP** — accurate historical context for the replacement | None |
| 5 | `tests/test_app_entry.py` | 1-39 | **Guard test** — asserts no cloudflared/tunnel references in app.py | **KEEP** — prevents regression | None |
| 6 | `tests/test_config.py` | 142-171 | **Guard test** — asserts BotConfig has no webhook fields | **KEEP** — prevents regression | None |
| 7 | `tests/test_bot.py` | 181-204 | **Guard test** — asserts no webhook server lifecycle in bot | **KEEP** — prevents regression | None |
| 8 | `dashboard/__tests__/lib/actions/no-webhook-sync.test.ts` | entire file | **Guard test** — asserts actions don't import webhook-sync | **KEEP** — prevents regression | None |
| 9 | `bot/bot.py` | 136, 268 | **Comments** — "replaces the webhook", "Mirrors the webhook's degraded-safe pattern" | **KEEP** — helpful context for maintainers | None |
| 10 | `bot/core/realtime.py` | 3 | **Docstring** — "Replaces the inbound webhook model" | **KEEP** — module-level architectural context | None |
| 11 | `bot/listeners/xp_listener.py` | 42 | **Comment** — "system/webhook messages" (Discord message type guard) | **KEEP** — unrelated to cache-sync webhook; refers to Discord's webhook message type | None |
| 12 | `openspec/changes/archive/2026-07-06-cache-sync-realtime/` | many | **Archive** — full change history with webhook/tunnel references | **KEEP** — historical record | None |
| 13 | `openspec/changes/archive/2026-07-03-webhook-sync/` | many | **Archive** — original webhook implementation history | **KEEP** — historical record | None |
| 14 | `openspec/changes/archive/2026-07-08-audit-code-arch-tooling/exploration.md` | 91, 241-243, 272, 288 | **Archive** — prior audit that identified the diagram stale ref (W1) | **KEEP** — historical record | None |
| 15 | `docs/MANUAL.md` | — | No webhook/tunnel references found | **N/A** — already clean | None |
| 16 | `Makefile` | — | No webhook/tunnel references found | **N/A** — already clean | None |
| 17 | `.env.example` | — | No webhook/tunnel vars (6 lines, clean) | **N/A** — already clean | None |
| 18 | `dashboard/.env.example` | — | No webhook/tunnel vars (11 lines, clean) | **N/A** — already clean | None |
| 19 | `dashboard/.env.local.example` | — | No webhook/tunnel vars (11 lines, clean) | **N/A** — already clean | None |

### Answers

**1. Was Cloudflare Tunnel fully discarded? What replaced it?**

YES. Fully discarded. Replaced by **Supabase Realtime CDC** — an outbound WebSocket subscription from the bot to Supabase. The bot subscribes to INSERT/UPDATE/DELETE events on `guild`, `greeting_config`, `ticket`, and `ticket_note` tables. Zero inbound ports, zero public exposure, zero tunnel. Verified: `app.py` is 18 lines, imports no aiohttp/cloudflared, delegates only to `bot.__main__.main`.

**2. Is there ANY residual code path that still needs an inbound public HTTPS URL?**

NO. No code path requires an inbound URL. The bot connects outbound to Discord (gateway WebSocket) and Supabase (Realtime WebSocket + REST). The dashboard connects outbound to Supabase and Discord OAuth2. There is no HTTP server in the bot process.

**3. Residual inventory** — see table above (19 items). Summary:
- **1 actionable residual**: `dashboard/.env.local` lines 26-29 (gitignored, local deployment artifact)
- **1 stale diagram**: `Diagramas/DiagramaSecuencia.mmd` line 29
- **5 guard tests**: KEEP (prevent webhook reintroduction)
- **12 archive/comment/doc references**: KEEP (historical context, no action needed)

**4. Recommended cleanup plan (minimal, safe)**

| Step | Action | Effort |
|------|--------|--------|
| 1 | Delete lines 26-29 from `dashboard/.env.local` (webhook comment + vars) | Trivial |
| 2 | Update `Diagramas/DiagramaSecuencia.mmd` Flujo 2: replace `Web->>Bot: ⚡ POST /webhook/sync` with `Web->>DB: UPDATE; Note over Bot: CDC event → invalidate cache` | Low |
| 3 | Done. Everything else is historical or a guard test. | — |

**5. Risks of deleting each residual**

| Residual | Delete? | Risk |
|----------|---------|------|
| `dashboard/.env.local` lines 26-29 | YES | **Zero** — gitignored, untracked, vars are empty anyway |
| `Diagramas/DiagramaSecuencia.mmd` stale flow | UPDATE (not delete) | **Zero** — documentation accuracy improvement |
| Guard tests (5 files) | NO | Deleting would **increase** risk of webhook reintroduction |
| Archive change folders | NO | Losing project history |
| Comments in bot/bot.py, bot/core/realtime.py | NO | Useful architectural context |

### Recommendation

This is a **trivial 2-file cleanup** — not a feature change. The diagram fix improves documentation accuracy; the `.env.local` cleanup removes dead config from a gitignored deployment artifact. Both are zero-risk.

No proposal/design/spec/tasks cycle needed. This can be done as a single commit: `docs: remove stale webhook/tunnel residuals from diagram and env`.

### Ready for Proposal

**No** — this is cleanup-only, not a change that needs the SDD cycle. Recommend a single direct commit.
