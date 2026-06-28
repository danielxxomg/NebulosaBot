# Proposal: Phase 7 — Dashboard (Next.js)

## Intent

Guild admins configure NebulosaBot exclusively via Discord commands — slow for complex edits, transcript review, and infraction history. A web dashboard provides richer management while the bot handles real-time interactions.

## Scope

### In Scope
- Discord OAuth2 via Supabase Auth
- Guild selector (admin + bot present)
- Guild/economy/greeting config editors
- Closed ticket browser with transcripts
- Infraction browser with filters
- Bot webhook sidecar (aiohttp) for cache invalidation

### Out of Scope
- Real-time WebSocket, member management, ticket creation, analytics, i18n

## Capabilities

### New Capabilities
- `dashboard-auth`: Discord OAuth2 via Supabase Auth, session middleware, guild admin check
- `dashboard-layout`: App Router shell — sidebar, guild selector, permission guard
- `guild-config-pages`: Server Actions for guild config CRUD
- `ticket-viewer`: Closed tickets + HTML transcript reader
- `moderation-viewer`: Infractions with type/user/status filters
- `economy-config`: Server Actions for economy config CRUD
- `bot-webhook`: aiohttp `POST /webhook/sync` → `cache.invalidate_guild()`

### Modified Capabilities
None

## Approach

Next.js App Router in `dashboard/`. Supabase Auth for OAuth2. Server Components read Supabase directly. Server Actions mutate then POST to bot webhook. aiohttp server in bot's `setup_hook()`. TS types mirror Python camelCase schema. Tailwind + shadcn/ui. Ref: `Diagramas/DiagramaSecuencia.mmd`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `dashboard/` | New | Full Next.js app |
| `bot/bot.py` | Modified | aiohttp webhook in `setup_hook()` |
| `openspec/specs/` | New | 7 capability specs |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Webhook unreachable | Low | 5-min TTL fallback |
| TS/Python type drift | Medium | Shared camelCase schema from DB |

## Rollback Plan

Delete `dashboard/` directory. Remove aiohttp task from `bot.py`. No DB migrations to revert.

## Dependencies

- Supabase with Discord OAuth2 provider
- Node.js 20+, `aiohttp` (transitive dep)

## Decisions (from Proposal Question Round)

| Question | Answer |
|----------|--------|
| Scope | MVP: auth + guild selector + config pages. Viewers deferred. |
| Styling | Tailwind + shadcn/ui |
| Webhook | Deferred — TTL fallback (5 min) for now |

## Success Criteria

- [ ] Admin logs in via Discord OAuth2, sees only authorized guilds
- [ ] Admin edits guild/economy/greeting config from dashboard
- [ ] Changes propagate via webhook (seconds) or TTL fallback (≤5 min)
- [ ] Admin browses closed tickets with transcripts and infractions with filters
- [ ] Webhook rejects unauthorized requests
