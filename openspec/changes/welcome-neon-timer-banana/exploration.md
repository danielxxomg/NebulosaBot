# Exploration: welcome-neon-timer-banana (Cycle 2 of 3)

> SDD exploration phase. Cycle 2 of 3. Scope: Neon greeting theming +
> timer ,12h prefix + banana C pool/8ball + security/Supabase carry.
> Cycle 3 (voice/moderation, ScheduledAction, has_perm) is OUT OF SCOPE.
> Baseline: Cycle 1 (`welcome-svg-foundation`) archived
> `2026-08-20` at head `6d2a892` — 2329 passed / 17 skipped / 84.82%.

## Current State

Cycle 1 shipped the SRP split of `ImageService` into three services-layer
modules behind a `GreetingRenderer` Protocol (`bot/services/greeting_renderer.py:54`),
with `PillowGreetingRenderer` injected at `bot/bot.py:230` even when the
cairosvg probe succeeds (`bot/bot.py:220-232`). The 454-line SRP violation
is gone; `#7289da` blurple is replaced by `brand.ACCENT`
(`bot/services/greeting_renderer.py:48-51`). `updatedAt` is additive on
`greeting_config` (`supabase/migrations/020_greeting_updated_at.sql`) and
the Realtime poll is incremental with null inclusion
(`bot/core/realtime.py:741-748`). DRY extracts landed (`guards.ts`,
`embeds.py`, explicit columns in dashboard). **19 PARTIAL scenarios
carried forward** (probe simulation vs `setup_hook`, rank golden delegating
baseline, migration comment-only evidence, realtime source-inspection
tests, `ImageService` deprecated shim, `GREETING_ACCENT` legacy alias) —
all non-critical evidence gaps, bounded.

**Cycle 2 baseline is greenfield for three of four tracks** (timer, banana
pool, 8ball are entirely new), and is an **extension** for the fourth
(greeting theming — the `GreetingRenderer` interface makes neon a 1-line
swap candidate).

## Affected Areas

### Greeting theming (extension)

- `bot/services/greeting_renderer.py:77-199` — `PillowGreetingRenderer.render`
  is procedural: `_card_base()` gradient, `rounded_rectangle` panels,
  `brand.ACCENT` accent stripe (`:133`). Neon = new theme with polygon hex
  + glow + magenta→cyan diagonal. Currently single-theme (no `theme_id`).
- `bot/services/shared_assets.py:26-41` — `CARD_WIDTH/HEIGHT`,
  `BG_TOP/BG_BOTTOM` gradient constants, `GREETING_PLACEHOLDER` palette.
  Theme-specific background/palette would live here or in a neon branch.
- `bot/models/greeting_config.py:10-62` — `GreetingConfig` has NO `theme_id`
  field. Needs additive column + round-trip.
- `supabase/migrations/004_greeting_config.sql` + `020_greeting_updated_at.sql`
  — base + updatedAt. `theme_id` migration is `021+`.
- `bot/core/db/greeting_db.py:32,52` — `select("*")` remains (Cycle 1 only
  fixed dashboard); upsert sets `updatedAt = now()` (`:51`). Theme upsert
  needs the column.
- `bot/services/greeting_service.py:106-228` — `dispatch_greeting` builds
  kwargs and calls `render_fn` via `to_thread`. Theme selection (default vs
  neon) must pass theme to renderer.
- `bot/bot.py:220-243` — probe + injection. Neon via Pillow procedural (SVG
  path stays behind probe for Cycle 2 per scope).
- `bot/utils/brand.py:1-19` — single palette (`ACCENT = 0xA855F7`). Neon
  needs `accent_a`/`accent_b` (magenta→cyan) — 2 palettes per scope.
- `dashboard/app/(authenticated)/guilds/[guildId]/greeting/page.tsx:13-123`
  — `GREETING_DEFAULTS` + `fields` array. NO `theme_id` field/select. Needs
  `GreetingThemeSelector` + i18n.
- `dashboard/lib/actions/greeting-actions.ts:15-87` — `updateGreetingConfig`
  extracts fields, validates, upserts. No `theme_id` handling.
- `bot/core/realtime.py:49-54,120` — `SUBSCRIBED_TABLES` already includes
  `greeting_config`; CDC invalidates guild cache on theme change (free).
- Avatar cache: NO greeting avatar cache exists (Cycle 1 added none). Scope
  asks for 60s dedup — new cache MUST use `cache_key(gid, "greeting_avatar")`
  (greeting-config spec scenario "Cache key is guild-scoped").

### Ocio with life (greenfield)

- `bot/cogs/ocio.py:1-113` — 113L, two commands (`dados` `:47`, `banana`
  `:70`). NO cooldowns (`rg cooldown` empty). NO `8ball`. `banana` uses
  single `assets/images/banana.webp` (`:28`) with `random.randint(2,30)`
  (`:92`). NO dorada easter egg. NO service layer (docstring `:3` "No
  service layer").
- `bot/locales/es.json:575-586` + `en.json:575-586` — `ocio.dados.*`,
  `ocio.banana.*` only. NO `ocio.8ball.*` keys.
- `assets/images/banana.webp` — single file; scope wants
  `assets/images/banana/*.webp` 5-8 variants pool.

### Timer versatile ,12h prefix (greenfield)

- `bot/cogs/tickets.py:110-145` — `AUTO_CLOSE_HOURS` 48h task
  (`@tasks.loop(hours=1)`) via `get_stale_tickets`. NO `scheduledCloseAt`,
  NO `,12h` prefix listener, NO `format_remaining`.
- `bot/cogs/tickets.py:163-180` — `on_message` listener already exists for
  `lastActivity` update in ticket channels. Timer listener coexists here
  (same guard: `is_ticket_channel` + `is_mod`).
- `bot/models/ticket.py:189-252` — `Ticket` dataclass has `last_activity`,
  `closed_at`, NO `scheduledCloseAt`/`scheduledCloseBy`. Needs additive
  columns.
- `bot/cogs/ticket_lifecycle_flow.py:1-322` — `TicketLifecycleFlow`
  (subticket/reopen/transfer/unclaim). No `,cancel`/timer commands.
  `ConfirmCancelView` imported from `bot/views/confirmation.py`.
- `bot/views/confirmation.py:24-144` — `ConfirmCancelView` (owner-only, 30s
  default timeout `:47`, `on_confirm` callback `:100`). Reusable for timer
  confirm if <2h or >5d.
- `bot/utils/time.py:34-61` — `parse_duration` (s/m/h/d, compound, returns
  3600 default on failure). Scope wants `parse_duration_strict` that
  **fails** on `,hola` (regex `^,\s*(\d+\s*[smhdwy])+$` adds w/y, strict
  anchoring).
- `supabase/migrations/015_ticket_lifecycle_reliability.sql` — partial
  indexes exist (`idx_ticket_active_channel` `WHERE status IN
  ('open','claimed')`). Scope's partial index `WHERE status IN
  ('open','claimed') AND scheduledCloseAt IS NOT NULL` is additive.
- `bot/services/ticket_service.py:388` — `close_ticket_full` exists;
  `@tasks.loop(seconds=60)` batch 50/guild is new.

### Security/Supabase (partial — Cycle 1 DRY closed dashboard, bot side remains)

- `bot/core/db/*.py` — `select("*")` remains in **10+ bot DB mixins**
  (`greeting_db.py:32`, `ticket_db.py:83,103,125,143,186,298,357`,
  `ticket_note_db.py:88`, `economy_db.py:30`, `ticket_category_db.py:62,87`,
  `member_db.py:31`, `ticket_audit_db.py:95`, `infraction_db.py:82,110`,
  `guild_db.py:32`). Cycle 1 spec `guards-contracts` "No select star"
  scoped to **dashboard actions only** (`:46-56`). Bot side is Cycle 2/3
  territory.
- `bot/core/db/base.py:86-90` — `AsyncClientOptions(schema="public")` only.
  Scope wants `auto_refresh_token=False`, `persist_session=False`.
- `supabase/migrations/005_rls_secure_default.sql` — **no-op parity stub**
  (`:13` "no DDL"). RLS explicitly enabled only on `ticket_note` (008) and
  `ticket_audit` (012). `guild`, `member`, `infraction`, `ticket`,
  `ticket_category`, `economy_config`, `greeting_config` have NO `ENABLE
  ROW LEVEL SECURITY`. Scope: "RLS remaining tables (ENABLE RLS secure
  default)".
- `bot/cogs/sentinel.py:102-117` — `_validate_target` checks
  `bot_member.top_role <= target.top_role` (`:107`). Scope says
  `author.top_role <= target deny` — **author hierarchy is NOT checked**,
  only bot hierarchy.
- `bot/cogs/ticket_admin_flow.py:142-177` — `delete_category` uses
  `is_mod()` (decorator on command). Scope: `delete_category is_mod→is_admin`.
- `escape_markdown` + `AllowedMentions`: `rg` finds **zero** usages in
  `bot/`. Greenfield.
- `23505` handling: `rg` finds **zero** `23505`/`UniqueViolation`/
  `duplicate key` handling. `greeting_db.py:52` upsert has no `on_conflict`
  (only `guild_db.py:69` uses it). Greenfield.

## Approaches

### 1. Neon SVG templating (Jinja2 `.svg.j2` → cairosvg) vs Pillow procedural

| Aspect | SVG template (Jinja2) | Pillow procedural (extend) |
|---|---|---|
| Layout source | `gaming_neon.svg.j2` text artifact (diffable, auditable, i18n-friendly) with `{{ accent_a }}`/`{{ accent_b }}` vars | Code in `PillowGreetingRenderer` (fork per theme) |
| libcairo dependency | cairosvg needs `libcairo` (NOT on `python:3.11-slim` no apt) → probe+fallback Pillow | Zero system deps, already works |
| Glow effect | Native `feGaussianBlur` SVG filter | Pillow `ImageFilter.GaussianBlur` (achievable but code) |
| Cycle 2 scope fit | Scope explicitly says "neon also via Pillow procedural for now, SVG path behind probe" | Matches scope directly |
| 1-line swap later | Template + renderer already abstracted | Needs theme param threading |
| TDD | Template render test (string output) + PNG bytes | Direct PNG bytes test |
| Effort | Medium-High (new dep jinja2, template, renderer, probe integration) | Medium (extend renderer with theme branch) |

**Recommendation: Pillow procedural for Cycle 2** (matches scope's explicit
"neon also via Pillow procedural for now, SVG path behind probe"). Reserve
SVG/Jinja2 for when libcairo is provisioned (Cycle 3+). The
`GreetingRenderer` interface already makes the swap 1-line; adding a
`theme_id` param to `render()` keeps both themes behind one interface.

### 2. Timer listener vs hybrid command

| Aspect | `on_message` regex listener (`,12h`) | Hybrid `/timer` slash command |
|---|---|---|
| Prefix ergonomics | Matches scope `^,\s*(\d+\s*[smhdwy])+$` | Slash `/timer 12h` |
| Ticket-channel guard | Reuses existing `on_message` (`tickets.py:163`) `is_ticket_channel` check | Needs channel context |
| `is_mod` guild-scoped | Same `is_mod_check` | Same |
| Coexists with AUTO_CLOSE 48h | Yes (separate `scheduledCloseAt` column) | Yes |
| Effort | Low (extend existing `on_message`) | Medium (new command + permission wiring) |

**Recommendation: `on_message` listener** (scope mandates `,12h` prefix;
existing `on_message` in `tickets.py:163` is the natural home). Add
`,cancel` as a prefix command in the same listener or
`TicketLifecycleFlow`.

### 3. Banana pool vs generation

| Aspect | Pool (`assets/images/banana/*.webp` 5-8) | Procedural generation (Pillow) |
|---|---|---|
| Visual variety | Real assets, artist-controlled | Procedural shapes (limited) |
| 1% dorada 30cm easter egg | Weighted pick from pool (include `dorada.webp`) | Conditional render branch |
| Pillow fallback if missing | Load fails → Pillow placeholder | Always Pillow |
| Effort | Low (ship webp files + `OcioService.get_random_banana()`) | Medium (Pillow banana drawing) |

**Recommendation: Pool** (scope explicitly says "banana C pool+fallback ...
assets/images/banana/*.webp 5-8 variants + OcioService.get_random_banana()").
New `OcioService` (services layer, testable without Discord mocks per
AGENTS.md architecture rule). `@cooldown(1,5,BucketType.user)` on
`dados`/`banana`/`8ball` + `CommandOnCooldown` handler with `retry_after`
+ `t()`.

## Recommendation

Ship Cycle 2 as a 3-slice stacked-to-main chain (auto-chain, 800-line
budget per slice):

1. **PR1 — Greeting theming + DRY carry** (`greeting_renderer` theme
   branch + `theme_id` migration `021` + model/db/dashboard/locales +
   avatar cache `cache_key(gid,"greeting_avatar")` 60s + clean
   `ImageService` shim + `GREETING_ACCENT` legacy + rank golden independent
   fixture + real probe `setup_hook` test). Pays off ~6 of 19 PARTIAL
   items naturally.
2. **PR2 — Timer ,12h** (`parse_duration_strict` + `Ticket.scheduledCloseAt/By`
   migration `022` + partial index + `on_message` regex +
   `ConfirmCancelView` reuse + `@tasks.loop(60s)` batch + `,cancel` +
   `format_remaining` + pinned embed `<t:unix:R>`). Greenfield,
   TDD-friendly.
3. **PR3 — Ocio + Security** (`OcioService` + banana pool + 8ball i18n +
   cooldowns + `CommandOnCooldown` handler + sentinel `author.top_role`
   hierarchy + `delete_category is_mod→is_admin` + `escape_markdown`/
   `AllowedMentions` + bot-side `select("*")` → explicit columns +
   `AsyncClientOptions` flags + RLS `ENABLE` on remaining tables + `23505`
   handling on greeting upsert).

All three are independently revertible; each stays within the 800-line
budget.

## Risks

- **libcairo still absent on Pterodactyl** — neon SVG path stays behind
  probe; Pillow procedural delivers neon glow via `ImageFilter.GaussianBlur`.
  No new system dep.
- **`scheduledCloseAt` + AUTO_CLOSE 48h interaction** — both can fire;
  `close_ticket_full` is idempotent (`already_closed` path exists in
  `ticket_repair_service.py:153-177`). Timer must clear
  `scheduledCloseAt=NULL` on close; `,cancel` clears it; overwrite=extend.
  Coexistence test required (TDD RED first).
- **`parse_duration_strict` vs `parse_duration`** — DO NOT merge (`time.py`
  docstring `:9-12` mandates separation). Add `parse_duration_strict` as a
  **new function** in `time.py` (same module, strict variant) returning
  `None`/raising on `,hola` rather than the 3600 default. Different
  domains rule still holds.
- **Bot-side `select("*")` is broad** (10+ files) — risks bloating PR3
  beyond 800 lines. Mitigation: scope to greeting/ticket DB mixins touched
  by Cycle 2 (greeting theme, ticket timer); leave economy/infraction for
  Cycle 3.
- **RLS `ENABLE` on live tables** — `ENABLE ROW LEVEL SECURITY` with no
  policies = no access for anon key (bot uses service_role, unaffected).
  Additive + safe but must be validated against live `schema_migrations`
  (memory: prior staging drift pain 2026-08-19).
- **Sentinel author hierarchy** — changing `_validate_target`
  (`:102-117`) to add `author.top_role <= target` deny is a behavior
  change to a tested path (`tests/test_sentinel_*.py`). Strict TDD: RED on
  the new deny branch first, then add the check. Could surprise mods who
  currently rely on bot-hierarchy-only — surface in proposal.
- **Banana pool assets** — shipping 5-8 `.webp` files adds binary artifacts
  to the repo. Confirm assets are licensed/original. Pillow fallback if a
  variant is missing/corrupt.
- **19 PARTIAL carry-forward** — only ~6 pay off in PR1 (shim, golden,
  probe). The rest (realtime builder tests, migration receipt, dashboard
  default test) should be scoped into PR1/PR3 opportunistically, not
  forced.
- **Review budget 800** — three tracks + security is broad. If any slice
  exceeds 800, split per `size:exception` precedent (documented cohesive
  work unit). Prefer staying within budget.

## Ready for Proposal

**Yes.** The orchestrator should tell the user:

- Cycle 2 ships as 3 stacked slices (greeting theming + DRY carry / timer
  ,12h / ocio + security), each ≤800 lines, solo-revertible.
- Neon is Pillow procedural for Cycle 2 (matches scope; SVG/Jinja2
  reserved for libcairo provisioning). One open decision: confirm the
  2-palette neon tokens (`accent_a` magenta, `accent_b` cyan) hex values
  for `brand.py` before spec.
- Timer `,12h` lives in the existing `on_message` listener
  (`tickets.py:163`); `parse_duration_strict` is a NEW function in
  `time.py` (not a merge with `parse_duration`).
- Security scope is partially-greenfield (escape_markdown/AllowedMentions/
  23505) and partially-carry (bot-side `select("*")`, RLS remaining tables,
  sentinel author hierarchy, AsyncClientOptions). Bot-side `select("*")`
  should be scoped to Cycle-2-touched mixins to keep PR3 within budget.
- ~6 of 19 PARTIAL carry-forward items pay off naturally in PR1; the rest
  are opportunistic, not forced.

`skill_resolutions: paths-injected` — all four requested skill files
(test-driven-development, supabase-postgres-best-practices, python-testing,
cognitive-doc-design) were loaded before task-specific work.
