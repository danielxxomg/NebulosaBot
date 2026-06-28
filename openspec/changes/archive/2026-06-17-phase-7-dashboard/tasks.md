# Tasks: Phase 7 — Dashboard (MVP)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 1800–2300 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain (PR 2) |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain (PR 2 in progress)
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Scaffolding + types + auth flow | PR 1 | Base: main; login works end-to-end |
| 2 | Layout shell + guild selector + permission guard | PR 2 | Base: PR 1 branch; sidebar + guild nav |
| 3 | Config pages + Server Actions + validation | PR 3 | Base: PR 2 branch; 3 editors + CRUD |
| 4 | Unit tests for actions, permissions, types | PR 4 | Base: PR 3 branch; Vitest coverage |

## Phase 1: Project Scaffolding & Types

- [x] 1.1 Create `dashboard/package.json` with Next.js 15, @supabase/supabase-js, @supabase/ssr, tailwind, shadcn deps
- [x] 1.2 Create `dashboard/next.config.ts`, `dashboard/tsconfig.json`, `dashboard/tailwind.config.ts`, `dashboard/postcss.config.mjs`
- [x] 1.3 Create `dashboard/.env.example` with SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_BOT_TOKEN
- [x] 1.4 Create `dashboard/.gitignore` (standard Next.js + .env.local)
- [x] 1.5 Create `dashboard/lib/types.ts` with GuildConfig, EconomyConfig, GreetingConfig, Member, Ticket, TicketCategory, Infraction, DiscordGuild, ActionResult interfaces
- [x] 1.6 Install shadcn/ui components: button, input, select, card, switch, label, skeleton

## Phase 2: Auth Infrastructure

- [x] 2.1 Create `dashboard/lib/supabase.ts` — single-file Supabase clients: browser (anon key), server (cookie auth), and service role (bypasses RLS)
- [x] 2.2 Create `dashboard/lib/supabase.ts` — browser Supabase client via `createClient()` (included in single-file supabase module)
- [x] 2.3 Create `dashboard/lib/supabase/middleware.ts` — session refresh helper for middleware
- [x] 2.4 Create `dashboard/middleware.ts` — auth guard redirecting to `/login`, guild admin check with Discord API + Supabase active guild
- [x] 2.5 Create `dashboard/lib/discord.ts` — `fetchUserGuilds()`, `fetchGuildInfo()`, and `hasAdministratorPerm()` helpers
- [x] 2.6 Create `dashboard/app/login/page.tsx` — Discord OAuth2 login button
- [x] 2.7 Create `dashboard/app/api/auth/callback/route.ts` — exchanges OAuth2 code for Supabase session

## Phase 3: Layout & Navigation

- [x] 3.1 Create `dashboard/app/layout.tsx` — root layout with sidebar shell and session provider
- [x] 3.2 Create `dashboard/components/sidebar.tsx` — nav links (overview, config, economy, greeting), mobile toggle
- [x] 3.3 Create `dashboard/app/page.tsx` — guild selector: fetches Discord guilds, filters admin+active, renders GuildCards
- [x] 3.4 Create `dashboard/components/guild-card.tsx` — guild icon, name, link to `/guilds/[id]`
- [x] 3.5 Create `dashboard/app/guilds/[guildId]/layout.tsx` — guild context layout with permission re-check
- [x] 3.6 Create `dashboard/app/guilds/[guildId]/page.tsx` — guild overview with config summary cards

## Phase 4: Config Pages & Server Actions

- [x] 4.1 Create `dashboard/lib/actions/guild-actions.ts` — `updateGuildConfig()` with validation (prefix length, language code, snowflake IDs), auth re-check, Supabase UPDATE, revalidatePath
- [x] 4.2 Create `dashboard/app/guilds/[guildId]/config/page.tsx` — form with prefix, language, modRoleId, logChannelId, ticketCategoryId, logEnabled
- [x] 4.3 Create `dashboard/lib/actions/economy-actions.ts` — `updateEconomyConfig()` with numeric validation, auth re-check
- [x] 4.4 Create `dashboard/app/guilds/[guildId]/economy/page.tsx` — form with dailyReward, xpPerMessage, cooldowns, levelRoles, levelUpChannelId
- [x] 4.5 Create `dashboard/lib/actions/greeting-actions.ts` — `updateGreetingConfig()` with channel/message validation, auth re-check
- [x] 4.6 Create `dashboard/app/guilds/[guildId]/greeting/page.tsx` — form with welcome/goodbye toggles, channel IDs, messages, card toggles
- [x] 4.7 Create `dashboard/components/config-form.tsx` — reusable form wrapper with Server Action integration, field errors, success/warning toasts

## Phase 5: Testing

- [x] 5.1 Configure Vitest in `dashboard/vitest.config.ts` with jsdom environment
- [x] 5.2 Write `dashboard/__tests__/lib/discord.test.ts` — test `hasAdministratorPerm()` bitfield check, `getUserGuilds()` filtering
- [x] 5.3 Write `dashboard/__tests__/lib/actions/guild-actions.test.ts` — test validation (prefix too long, invalid language, bad snowflake), unauthorized rejection, successful update
- [x] 5.4 Write `dashboard/__tests__/lib/actions/economy-actions.test.ts` — test numeric bounds, auth check
- [x] 5.5 Write `dashboard/__tests__/lib/actions/greeting-actions.test.ts` — test channel ID validation, message length
- [x] 5.6 Write `dashboard/__tests__/lib/types.test.ts` — snapshot test TS interfaces match expected shape
