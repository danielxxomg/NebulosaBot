## Exploration: Phase 7 — Dashboard (Next.js)

### Current State

NebulosaBot is a Python Discord bot (phases 1-6 complete) with:
- **7 cogs**: Core, Sentinel, Tickets, Stellar (economy), Greetings, Utility, Ocio
- **8 services**: guild, infraction, ticket, transcript, economy, logging, greeting, image
- **Cache-first architecture**: `TTLCache` with 5-min TTL, guild-scoped keys (`{guild_id}:config`)
- **Supabase DB**: 7 tables — `guild`, `user`, `member`, `infraction`, `ticket`, `ticket_category`, `economy_config`, `greeting_config`
- **All models** use camelCase DB keys via `to_db_dict()` / `from_db_row()`
- **Webhook concept** exists in the sequence diagram (`POST /webhook/sync {guild_id, type: "config"}`) but is NOT implemented in the bot yet

The bot has NO HTTP server. It is a pure Discord gateway application. The dashboard needs a way to notify the bot of config changes to invalidate its RAM cache.

### Affected Areas

- `bot/bot.py` — Needs an HTTP webhook endpoint for cache invalidation
- `bot/core/cache.py` — `invalidate_guild()` already exists, webhook just needs to call it
- `bot/services/*_service.py` — All services use cache-first reads; webhook invalidation affects all
- `dashboard/` (NEW) — Entire Next.js app is new
- `openspec/specs/` — New specs needed for dashboard, auth, webhook
- `migrations/` — No new tables needed (dashboard reads existing tables directly)

### Approaches

#### 1. Architecture: Bot Webhook Server

**Approach A — aiohttp sidecar in bot process**
Add a lightweight `aiohttp.web` server alongside the Discord gateway in the same Python process. Single deployable, shared memory for direct cache invalidation.

- Pros: Zero network hop for cache invalidation (direct method call), single process to deploy/monitor, no shared secret needed (localhost or internal network)
- Cons: Couples HTTP server lifecycle to bot lifecycle, bot crash kills dashboard sync, limited scalability
- Effort: Low

**Approach B — Separate FastAPI/Flask microservice**
Standalone HTTP service that receives webhook POSTs and relays cache invalidation to the bot via an internal channel (Redis pub/sub, or a second HTTP call to the bot).

- Pros: Independent scaling, clean separation, bot can run without dashboard
- Cons: Extra process to deploy, needs IPC mechanism (Redis/HTTP), more complexity
- Effort: Medium

**Approach C — No webhook; rely on cache TTL expiry only**
Dashboard writes to Supabase; bot picks up changes when cache expires (max 5 min delay).

- Pros: Zero bot changes, simplest architecture, no new failure modes
- Cons: Up to 5-minute delay before config changes take effect, bad UX for prefix changes
- Effort: None

**Recommendation**: **Approach A (aiohttp sidecar)**. The bot already runs 24/7, the cache invalidation is a single method call (`cache.invalidate_guild(guild_id)`), and the sequence diagram already specifies `POST /webhook/sync`. An aiohttp server can be started in `setup_hook()` as a background task. For production, bind to localhost or an internal network with a shared secret header.

#### 2. Architecture: Dashboard Auth

**Approach A — Supabase Auth with Discord OAuth2 provider**
Supabase natively supports Discord as an OAuth2 provider. Users log in via Supabase Auth, which returns an access token with Discord user info. Dashboard verifies guild admin via Discord API using the token.

- Pros: No custom OAuth2 code, Supabase handles token refresh/session, integrates with Supabase RLS for row-level security, well-documented
- Cons: Requires configuring Discord OAuth2 app + Supabase provider, Supabase Auth has rate limits on free tier
- Effort: Low

**Approach B — Custom Discord OAuth2 flow**
Implement the Discord OAuth2 handshake directly in Next.js API routes (redirect → exchange code → store session).

- Pros: Full control, no Supabase Auth dependency
- Cons: Must implement token refresh, session management, CSRF protection manually, more code to maintain
- Effort: High

**Recommendation**: **Approach A (Supabase Auth + Discord OAuth2)**. The project already uses Supabase. Adding Discord as an OAuth2 provider in Supabase is a config-only change. The `@supabase/supabase-js` client handles sessions. Middleware validates auth on every dashboard route.

#### 3. Architecture: Guild Access Verification

The dashboard must show only guilds where:
1. The user is an admin (Manage Guild permission)
2. The bot is present in the guild

**Approach**: After Discord OAuth2 login, call `GET /users/@me/guilds` with the Discord access token to get the user's guild list with permissions. Cross-reference with the `guild` table in Supabase (where `active = true`) to filter to guilds where the bot is present.

- The Discord token provides real-time guild membership + permissions
- Supabase provides bot presence (guild row exists and is active)
- No need to store guild membership in the DB — Discord API is the source of truth

#### 4. Architecture: Data Access Pattern

**Approach A — Dashboard reads Supabase directly (recommended)**
Server Components and Server Actions query Supabase directly using the `@supabase/supabase-js` client. No API layer between dashboard and DB.

- Pros: Matches the sequence diagram (`Dashboard → Supabase direct reads`), no API to maintain, secrets stay on server, same camelCase schema the bot uses
- Cons: Dashboard and bot must agree on schema (shared types needed)
- Effort: Low

**Approach B — Dashboard calls bot API**
Dashboard sends all reads/writes through the bot's HTTP endpoint.

- Pros: Single source of truth for business logic
- Cons: Bot becomes a bottleneck, adds latency, bot wasn't designed as an API server
- Effort: High

**Recommendation**: **Approach A (direct Supabase access)**. The sequence diagram explicitly shows `Dashboard → Supabase (direct reads)`. The bot's webhook endpoint is ONLY for cache invalidation, not data proxying.

#### 5. Architecture: Webhook Sync Protocol

From the sequence diagram:
```
POST /webhook/sync
Body: { guild_id: string, type: "config" | "economy" | "greeting" }
```

The bot's webhook handler:
1. Validates a shared secret (header `X-Webhook-Secret`)
2. Calls `cache.invalidate_guild(guild_id)` to flush all cached data for that guild
3. Returns 200 OK

This is intentionally simple — the webhook does NOT receive the new config values. It just invalidates the cache. The next bot read will fetch fresh data from Supabase.

#### 6. Project Structure: Next.js App Router

```
dashboard/
├── app/
│   ├── layout.tsx                    # Root layout (sidebar + header)
│   ├── page.tsx                      # Guild selector (home)
│   ├── login/
│   │   └── page.tsx                  # Login page (Discord OAuth2)
│   ├── auth/
│   │   └── callback/
│   │       └── route.ts              # OAuth2 callback handler
│   ├── (dashboard)/                  # Route group — auth-protected
│   │   ├── layout.tsx                # Guild context layout (sidebar per guild)
│   │   └── [guildId]/
│   │       ├── layout.tsx            # Guild selector + permission check
│   │       ├── page.tsx              # Guild overview / config summary
│   │       ├── config/
│   │       │   └── page.tsx          # Edit prefix, language, channels, roles
│   │       ├── tickets/
│   │       │   ├── page.tsx          # Ticket list (closed tickets)
│   │       │   └── [ticketId]/
│   │       │       └── page.tsx      # Ticket detail + transcript viewer
│   │       ├── moderation/
│   │       │   └── page.tsx          # Infraction list
│   │       ├── economy/
│   │       │   └── page.tsx          # Economy config editor
│   │       └── greetings/
│   │           └── page.tsx          # Greeting config editor
│   └── api/
│       └── webhook/
│           └── sync/
│               └── route.ts          # NOT here — webhook goes to bot, not dashboard
├── lib/
│   ├── supabase/
│   │   ├── client.ts                 # Server-side Supabase client
│   │   ├── client-component.ts       # Client-side Supabase client
│   │   └── middleware.ts             # Auth helper for middleware
│   ├── actions/
│   │   ├── guild-actions.ts          # Server Actions for guild config
│   │   ├── economy-actions.ts        # Server Actions for economy config
│   │   ├── greeting-actions.ts       # Server Actions for greeting config
│   │   └── webhook-actions.ts        # Server Action to POST /webhook/sync to bot
│   └── types/
│       └── index.ts                  # TypeScript types matching Python dataclasses
├── middleware.ts                      # Auth check on /dashboard/* routes
├── next.config.ts
├── package.json
└── tsconfig.json
```

#### 7. Shared Types (TypeScript ↔ Python)

TypeScript interfaces must mirror Python dataclasses exactly (camelCase keys):

```typescript
// lib/types/index.ts
interface GuildConfig {
  id: string;
  prefix: string;
  language: string;
  modRoleId: string | null;
  logChannelId: string | null;
  ticketCategoryId: string | null;
  ticketPanelMessageId: string | null;
  ticketPanelChannelId: string | null;
  logEnabled: boolean;
  welcomeEnabled: boolean;
  active: boolean;
}

interface EconomyConfig {
  guildId: string;
  dailyReward: number;
  dailyCooldownHours: number;
  xpPerMessage: number;
  xpCooldownSeconds: number;
  levelBaseXp: number;
  levelMultiplier: number;
  levelRoles: Record<string, string>;  // { "level": "role_id" }
  levelUpChannelId: string | null;
}

interface GreetingConfig {
  guildId: string;
  welcomeEnabled: boolean;
  goodbyeEnabled: boolean;
  welcomeChannelId: string | null;
  goodbyeChannelId: string | null;
  welcomeMessage: string | null;
  goodbyeMessage: string | null;
  welcomeCardEnabled: boolean;
  goodbyeCardEnabled: boolean;
}

interface Ticket {
  id: string;
  ticketNumber: number;
  guildId: string;
  authorId: string;
  channelId: string;
  categoryId: string | null;
  status: "open" | "claimed" | "closed";
  claimedBy: string | null;
  transcriptUrl: string | null;
  createdAt: string;
  closedAt: string | null;
  lastActivity: string;
}

interface Infraction {
  id: string;
  guildId: string;
  targetId: string;
  moderatorId: string;
  type: "WARN" | "MUTE" | "KICK" | "BAN";
  reason: string;
  active: boolean;
  expiresAt: string | null;
  createdAt: string;
}

interface TicketCategory {
  id: string;
  guildId: string;
  name: string;
  emoji: string | null;
  description: string | null;
  position: number;
  active: boolean;
  createdAt: string | null;
}

interface Member {
  guildId: string;
  userId: string;
  xp: number;
  level: number;
  warnings: number;
  coins: number;
  dailyStreak: number;
  lastDailyReset: string | null;
  lastDaily: string | null;
  lastXpGain: string | null;
}
```

#### 8. Webhook Sync Flow (Server Action)

When a Server Action updates config in Supabase, it must also notify the bot:

```typescript
// lib/actions/webhook-actions.ts
'use server';

async function notifyBot(guildId: string, type: string) {
  const botUrl = process.env.BOT_WEBHOOK_URL;  // e.g. http://localhost:8080
  const secret = process.env.BOT_WEBHOOK_SECRET;

  await fetch(`${botUrl}/webhook/sync`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Webhook-Secret': secret,
    },
    body: JSON.stringify({ guild_id: guildId, type }),
  });
}
```

Each config Server Action calls `notifyBot()` after the Supabase write succeeds. If the bot is unreachable, the cache will expire naturally within 5 minutes (graceful degradation).

### Recommendation

**Full stack approach:**

1. **Bot webhook**: Add `aiohttp.web` server in `bot.py` started as a background task in `setup_hook()`. Single endpoint: `POST /webhook/sync`. Validates shared secret, calls `cache.invalidate_guild(guild_id)`.

2. **Dashboard**: Next.js App Router in `dashboard/` directory at project root. Supabase Auth with Discord OAuth2 provider. Server Components for reads, Server Actions for mutations.

3. **Auth flow**: Discord OAuth2 → Supabase Auth → Next.js middleware validates session on every `/dashboard/*` route. After login, call Discord API `GET /users/@me/guilds` to get guild list with permissions, cross-reference with Supabase `guild` table for bot presence.

4. **Data access**: Direct Supabase queries from Server Components/Actions. TypeScript types mirror Python dataclasses (camelCase keys).

5. **Cache sync**: Server Actions write to Supabase, then POST to bot webhook. Bot invalidates cache. Graceful degradation if bot is unreachable (5-min TTL).

### Risks

- **Bot webhook availability**: If the bot process crashes, the webhook is down. Mitigation: cache TTL (5 min) ensures eventual consistency.
- **Discord API rate limits**: `GET /users/@me/guilds` is rate-limited. Mitigation: cache the guild list in a short-TTL cookie or server-side cache.
- **Type drift**: TypeScript types can diverge from Python dataclasses. Mitigation: both use camelCase keys from the same DB schema; add a CI check or shared schema doc.
- **Supabase Auth free tier limits**: 50k MAU on free tier. Mitigation: sufficient for admin-only dashboard (very low user count).
- **Shared secret management**: The webhook secret must be in both bot's `.env` and dashboard's `.env`. Mitigation: document in `.env.example` for both.
- **aiohttp port conflict**: The bot's webhook server needs a port. Mitigation: configurable via env var `WEBHOOK_PORT`, default 8080.

### Ready for Proposal

**Yes.** The exploration is complete. The orchestrator should tell the user:

1. The dashboard will be a Next.js App Router app in `dashboard/` at the project root
2. Auth uses Supabase Auth with Discord OAuth2 (no custom OAuth code)
3. The bot gets a lightweight aiohttp webhook endpoint for cache invalidation
4. Dashboard reads Supabase directly — no API proxy through the bot
5. TypeScript types mirror the existing Python dataclass camelCase schema
6. All mutations use Server Actions that write to Supabase then POST to the bot webhook

No new database tables or migrations are needed. The dashboard operates entirely on existing tables.
