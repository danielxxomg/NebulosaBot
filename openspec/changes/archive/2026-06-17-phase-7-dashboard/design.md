# Design: Phase 7 — Dashboard (MVP)

## Technical Approach

Next.js 15 App Router in `dashboard/` at project root. Supabase Auth handles Discord OAuth2 — no custom OAuth code. Server Components read Supabase directly (same camelCase schema the bot uses). Server Actions mutate config then rely on 5-min TTL cache expiry for bot sync (webhook deferred per proposal decision). Tailwind CSS + shadcn/ui for components. TypeScript interfaces mirror Python dataclasses exactly.

## Architecture Decisions

| Decision | Options | Tradeoff | Choice |
|----------|---------|----------|--------|
| Framework | Next.js App Router vs Vite SPA vs Remix | SSR/SEO vs simplicity vs maturity | Next.js App Router — Server Components eliminate API layer, matches exploration recommendation |
| Auth | Supabase Auth + Discord OAuth2 vs custom OAuth flow | Zero custom code vs full control | Supabase Auth — project already uses Supabase, config-only Discord provider setup |
| Data access | Direct Supabase queries vs bot API proxy | No API maintenance vs single source of truth | Direct Supabase — bot wasn't designed as API, sequence diagram confirms direct reads |
| Cache sync | aiohttp webhook (instant) vs TTL-only (≤5 min) | Instant propagation vs zero bot changes | TTL-only for MVP — webhook deferred, 5-min delay acceptable for config edits |
| Styling | Tailwind + shadcn/ui vs CSS modules vs styled-components | Rapid prototyping vs isolation vs flexibility | Tailwind + shadcn/ui — matches exploration recommendation, accessible components out of box |
| Mutations | Server Actions vs API routes + client fetch | Simpler code, no API needed vs REST flexibility | Server Actions — form submissions are simpler, no client-side state management for mutations |

## Data Flow

### Auth Flow
```
Browser → /login → Supabase OAuth2 (Discord)
       → /api/auth/callback → session cookie
       → / → Discord API GET /users/@me/guilds
       → filter: ADMINISTRATOR perm ∩ Supabase guild (active=true)
       → guild cards rendered
```

### Config Edit Flow
```
Admin edits form → Server Action
  → Supabase UPDATE (camelCase keys)
  → revalidatePath()
  → (bot picks up change within 5 min via TTL expiry)
```

### Guild Access Check
```
middleware.ts:
  1. Verify Supabase session exists → redirect /login if not
  2. Extract guildId from URL
  3. Call Discord API GET /users/@me/guilds (cached 60s)
  4. Check: user has ADMINISTRATOR on this guild
  5. Check: Supabase guild row exists with active=true
  6. Allow or redirect to / with error
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `dashboard/package.json` | Create | Next.js 15, @supabase/supabase-js, tailwind, shadcn deps |
| `dashboard/next.config.ts` | Create | Next.js config with Supabase env vars |
| `dashboard/tsconfig.json` | Create | TypeScript strict config |
| `dashboard/tailwind.config.ts` | Create | Tailwind config with shadcn theme |
| `dashboard/middleware.ts` | Create | Auth guard + guild admin check |
| `dashboard/app/layout.tsx` | Create | Root layout — sidebar shell, auth session provider |
| `dashboard/app/page.tsx` | Create | Home — guild selector (fetches user guilds from Discord API) |
| `dashboard/app/login/page.tsx` | Create | Login page with Discord OAuth2 button |
| `dashboard/app/api/auth/callback/route.ts` | Create | OAuth2 callback — exchanges code for session |
| `dashboard/app/guilds/[guildId]/layout.tsx` | Create | Guild context layout — permission check, guild sidebar |
| `dashboard/app/guilds/[guildId]/page.tsx` | Create | Guild overview — config summary cards |
| `dashboard/app/guilds/[guildId]/config/page.tsx` | Create | Guild config editor (prefix, language, channels, roles) |
| `dashboard/app/guilds/[guildId]/economy/page.tsx` | Create | Economy config editor (rewards, XP, level roles) |
| `dashboard/app/guilds/[guildId]/greeting/page.tsx` | Create | Greeting config editor (welcome/goodbye messages) |
| `dashboard/components/ui/*` | Create | shadcn/ui components (button, input, select, card, switch) |
| `dashboard/components/sidebar.tsx` | Create | Navigation sidebar with guild sections |
| `dashboard/components/guild-card.tsx` | Create | Guild selector card component |
| `dashboard/components/config-form.tsx` | Create | Reusable config form with Server Action integration |
| `dashboard/lib/supabase/server.ts` | Create | Server-side Supabase client (uses service role key) |
| `dashboard/lib/supabase/client.ts` | Create | Client-side Supabase client (uses anon key) |
| `dashboard/lib/supabase/middleware.ts` | Create | Auth helper for middleware session verification |
| `dashboard/lib/discord.ts` | Create | Discord API helpers (get user guilds, check permissions) |
| `dashboard/lib/types.ts` | Create | TypeScript interfaces mirroring Python dataclasses |
| `dashboard/lib/actions/guild-actions.ts` | Create | Server Actions for guild config CRUD |
| `dashboard/lib/actions/economy-actions.ts` | Create | Server Actions for economy config CRUD |
| `dashboard/lib/actions/greeting-actions.ts` | Create | Server Actions for greeting config CRUD |
| `dashboard/.env.example` | Create | Template for NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET |
| `dashboard/.gitignore` | Create | Standard Next.js gitignore + .env.local |

## Interfaces / Contracts

TypeScript types mirror Python dataclasses (camelCase DB keys):

```typescript
// dashboard/lib/types.ts
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
  levelRoles: Record<string, string>;
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

interface DiscordGuild {
  id: string;
  name: string;
  icon: string | null;
  owner: boolean;
  permissions: string;  // permission bitfield
}
```

Server Action return contract:
```typescript
type ActionResult =
  | { success: true; message: string }
  | { success: false; error: string; field?: string };
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Server Actions validation logic | Vitest — test input validation, error paths |
| Unit | Discord permission check utility | Vitest — test ADMINISTRATOR bit check |
| Unit | Type contract alignment | Vitest — snapshot test TS types match expected shape |
| Integration | Supabase read/write round-trip | Vitest + Supabase local or mocked client |
| E2E | Login → guild select → edit config | Playwright — full auth flow (deferred to post-MVP) |

## Migration / Rollout

No migration required. Dashboard reads existing tables directly. No new DB tables, no schema changes. The bot requires zero modifications for MVP (webhook deferred).

Rollout: deploy dashboard as standalone Next.js app. Configure Supabase Discord OAuth2 provider. Set env vars. No coordination with bot deployment needed.

## Open Questions

- [ ] Should the guild overview page (`/guilds/[guildId]`) show any summary stats (member count, ticket count) or just link to config sections?
- [ ] Discord API rate limit on `GET /users/@me/guilds` — should we cache the guild list server-side with a short TTL (e.g., 60s) to avoid hitting rate limits on page navigation?
