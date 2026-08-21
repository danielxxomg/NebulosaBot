# Design: welcome-neon-timer-banana

> Cycle 2 of 3. Neon Pillow theme, `,12h` scheduled-close timer, banana/8ball
> ocio, and security/Supabase carry. Head `bce758d` (2329 tests, 84.82%).
> Delivery: stacked-to-main, auto-chain, 3 PRs ≤800 lines each, solo-revertible.

## Technical Approach

Four tracks ship as **3 stacked slices** against the existing Tach 7-layer
boundary (no reshaping):

1. **PR1 — Greeting theming + cache.** Add `brand.ACCENT_A`/`ACCENT_B`, a
   `theme_id` Pillow branch in `PillowGreetingRenderer` (unchanged
   `GreetingRenderer` Protocol + optional `theme_id` param), `021` migration
   (additive nullable `theme_id`), `GreetingConfig.theme_id` round-trip, a
   60s guild-scoped avatar cache via `cache_key(gid,"greeting_avatar")`, and
   the dashboard `GreetingThemeSelector` + Both-selector (Realtime CDC dual
   observer).
2. **PR2 — Timer `,12h`.** `parse_duration_strict` in `bot/utils/time.py`
   (new function, NOT a merge), `022` migration (additive
   `scheduledCloseAt`/`scheduledCloseBy` + partial index), an
   `on_message` listener extension in `TicketsCog`, `ConfirmCancelView`
   reuse for `<2h`/`>5d`, a 60s `@tasks.loop` batch-50 closer, `,cancel`, and
   `format_remaining` + `<t:R>`/`<t:F>` pinned embed.
3. **PR3 — Ocio + Security.** `OcioService` (services layer) + banana pool +
   1% dorada + Pillow fallback + `/8ball` (20 i18n) + shared cooldown +
   `CommandOnCooldown` handler; sentinel `author.top_role` hierarchy deny;
   `delete_category` `is_mod`→`is_admin`; `escape_markdown`/`AllowedMentions`;
   bot-side `select("*")`→explicit cols (greeting + ticket timer only);
   `AsyncClientOptions(auto_refresh_token=False, persist_session=False)`;
   `23505` idempotent handling on greeting upsert; `ENABLE ROW LEVEL SECURITY`
   on the 7 remaining tables (`023` migration).

All migrations are **additive nullable**; rollback is `DROP COLUMN`/`DROP INDEX`/
`DISABLE ROW LEVEL SECURITY`. Live `schema_migrations` is queried before each
apply (prior 2026-08-19 staging drift).

## Architecture Decisions

| # | Decision | Alternatives | Rationale |
|---|----------|--------------|----------|
| D1 | Neon via **Pillow procedural** (hex polygon + `ImageFilter.GaussianBlur`, `ACCENT_A→ACCENT_B` diagonal) inside `PillowGreetingRenderer`; SVG stays behind the `bot.py:220` probe | SVG/Jinja2 template + cairosvg | `python:3.11-slim` has no `libcairo`; spec mandates Pillow default even when probe succeeds. `GreetingRenderer` Protocol makes a later 1-line swap to SVG trivial. No new system dep. |
| D2 | `theme_id: str \| None = None` added to `GreetingRenderer.render()` (backwards-compatible: omit → default theme) | Separate `NeonGreetingRenderer` class | One Protocol, one injection site (`bot.py:230`), unknown `theme_id` falls back to default (no broken card). Existing callers unchanged. |
| D3 | Timer via existing **`on_message` listener** in `TicketsCog` (`tickets.py:163`) reusing `is_ticket_channel` + `is_mod_check` | New hybrid `/timer` slash command | Spec mandates `,12h` prefix; existing listener already guards ticket channels. `parse_duration_strict` regex `^,\s*(\d+\s*[smhdwy])+$` rejects `,hola` silently (no error embed). |
| D4 | `parse_duration_strict` is a **new function** in `bot/utils/time.py` returning `int \| None` (no 3600 fallback) | Modify `parse_duration` | `time.py` vs `timeparse.py` DO-NOT-MERGE rule; `parse_duration` callers (Sentinel timeouts) rely on the 3600 graceful default. Strict variant fails `,hola`/`,`/`12`/`1x`. Adds `w`(7d)/`y`(365d). |
| D5 | 60s `@tasks.loop` batch-50 in `TicketsCog` calls existing `close_ticket_full` (silent); idempotent via `transition_ticket_to_closed` `in_` filter | Dedicated scheduled-close service | `transition_ticket_to_closed` already guarantees exactly-one mutation via SELECT+UPDATE both carrying `status IN ('open','claimed')` — the loser returns `None` (`already_closed`). Reuses tested path; `cog_unload()` cancels loop; `TICKET_TIMER_ENABLED` flag disables. |
| D6 | Coexistence: 48h `AUTO_CLOSE` sweep clears `scheduledCloseAt`/`scheduledCloseBy` on close | Mutually exclusive timers | Both may select the same ticket; `transition_ticket_to_closed` makes double-close impossible. AUTO_CLOSE clears the scheduled fields so no stale time lingers. |
| D7 | Banana **pool** (`assets/images/banana/*.webp` 5–8) + 1% dorada 30cm weighted pick + Pillow fallback render via `asyncio.to_thread`; **no DB** | Procedural Pillow generation | Spec mandates pool; real assets > procedural shapes; `OcioService.get_random_banana()` is unit-testable without Discord mocks; missing/corrupt file → Pillow placeholder. |
| D8 | `/8ball` 20 localized responses via `t()`, ephemeral, no DB | Hardcoded English list | i18n-isolated (es/en independently testable); shared `@commands.cooldown(1,5,BucketType.user)` with `CommandOnCooldown` handler formatting `retry_after` via `t()`. |
| D9 | `OcioService` in `bot/services/` (thin cog delegates) | Logic in cog | Architecture rule: cogs are Discord I/O only; service is testable without Discord mocks. Pillow fallback in service via `asyncio.to_thread`. |
| D10 | Sentinel author-hierarchy deny: `author.top_role <= target.top_role` added to `_validate_target` (`sentinel.py:102`); owner exempt | Bot-hierarchy only (status quo) | Spec behavior change; **Strict TDD RED first** on the new deny branch, existing bot-hierarchy + owner-exemption unchanged. |
| D11 | `delete_category` guard `is_mod()`→`is_admin()` (`tickets.py:262`); service `guildId != gid` check unchanged | Keep `is_mod()` | Destructive admin action; `@is_mod()` count drops 24→23 (characterization updated). **Strict TDD RED first** on mod-denied branch. |
| D12 | Bot-side `select("*")`→explicit cols **scoped to greeting + ticket timer** only | All 10+ mixins at once | Economy/infraction/etc. deferred to Cycle 3 to keep PR3 ≤800 lines (documented tech-debt, not a failure). |
| D13 | `23505` handling on `upsert_greeting_config`: `on_conflict="guildId", ignore_duplicates=True` OR catch `UniqueViolation` → re-read no-op | Raw traceback to user | Keyed by `guildId` (unique); 23505 means another writer won — same config. Reuses `guild_db.py:69` precedent. |
| D14 | `AsyncClientOptions(schema="public", auto_refresh_token=False, persist_session=False)` | `schema="public"` only | Bot is server-side `service_role` with static `sb_secret_`; no token refresh, no disk session. Config-only, no behavior change. |
| D15 | `ENABLE ROW LEVEL SECURITY` on `guild`,`member`,`infraction`,`ticket`,`ticket_category`,`economy_config`,`greeting_config` (migration `023`) | Status quo (only `ticket_note`/`ticket_audit` RLS) | service_role bypasses RLS (bot unaffected); anon/publishable/authenticated denied. Additive (`DISABLE` on rollback). Live `schema_migrations` validated first. |
| D16 | Dashboard `theme_id` write flows through existing Realtime CDC (`greeting_config` already subscribed); **both** bot cache + dashboard `/welcome` preview observe CDC | Inbound bot webhook | No coupling webhook; `invalidate_guild` drops `{gid}:greeting_avatar` + `{gid}:greeting_config` for free. Dashboard MAY refetch on CDC. |

## Data Flow

### Sequence: Theme selection (slash + dashboard)

```
Member joins ──> on_member_join ──> GreetingService.dispatch_greeting
  │ get_config(gid) cache-first ──> GreetingConfig.theme_id
  └─> asyncio.to_thread(renderer.render, theme_id=config.theme_id, ...)
        └─> PillowGreetingRenderer._render_theme(theme_id)
              ├─ theme_id=None/unknown ─> _render_default (brand.ACCENT)
              └─ theme_id="gaming_neon" ─> _render_neon (ACCENT_A→ACCENT_B, GaussianBlur)

Dashboard: GreetingThemeSelector ──> updateGreetingConfig (Server Action)
  └─> Supabase upsert greeting_config.themeId
        └─> Realtime CDC postgres_changes ──> bot.invalidate_guild(gid)
              └─> drops {gid}:greeting_config + {gid}:greeting_avatar
                    └─> next dispatch re-reads DB ──> neon renders
        └─> dashboard /welcome refetch (MAY) ──> preview reflects new theme
```

### Sequence: `,12h` timer lifecycle

```
Mod sends ",12h" in ticket channel
  └─> TicketsCog.on_message (tickets.py:163)
        ├─ guard: is_ticket_channel(channel.id) AND is_mod_check(author) AND status IN (open,claimed)
        ├─ parse_duration_strict(",12h") ──> 43200  (None on ",hola" → silent ignore)
        ├─ if <2h OR >5d ─> ephemeral ConfirmCancelView (owner-only, 30s)
        │     ├─ Confirm ─> proceed    ├─ Cancel/timeout ─> no-op return
        ├─ TicketService.schedule_close(channel, ticket, duration, author_id)
        │     └─ update ticket SET scheduledCloseAt=now()+dur, scheduledCloseBy=author
        │     └─ pin/edit embed: ⏳ Cierra <t:{unix}:R> (<t:{unix}:F>) via format_remaining
        └─ if existing pinned embed ─> edit (extend), else pin new

@tasks.loop(seconds=60) scheduled_close_loop
  └─> get_scheduled_close_candidates(batch=50)  -- partial index
        └─> for each: close_ticket_full(channel, ticket, "auto:scheduled", manual=False)
              └─> transition_ticket_to_closed(in_=['open','claimed'])
                    ├─ winner ─> close + clear scheduledCloseAt/By + delete channel (silent)
                    └─> None (already_closed by AUTO_CLOSE/manual) ─> clear scheduledCloseAt/By, no double-close

",cancel" ─> on_message ─> update ticket SET scheduledCloseAt=NULL, scheduledCloseBy=NULL ─> confirm embed
                      (does NOT touch AUTO_CLOSE inactivity clock)
```

### Sequence: Banana pool fallback

```
/banana ─> OcioCog.banana ─> OcioService.get_random_banana()
  ├─ 1% path ─> dorada variant + 30cm
  ├─ 99% path ─> random.choice(glob("assets/images/banana/*.webp"))
  │     └─ load bytes ─> success: discord.File
  │     └─ missing/corrupt ─> asyncio.to_thread(_pillow_banana_placeholder) ─> discord.File
  └─ empty pool ─> Pillow placeholder ─> delivery succeeds (no error embed)
  (ephemeral, no DB row, @cooldown(1,5,user) enforced)
```

### Sequence: RLS enable

```
Migration 023 staged ─> validate against live schema_migrations (not already recorded)
  └─> ALTER TABLE ... ENABLE ROW LEVEL SECURITY  (×7 tables, no policies)
        └─> anon/publishable/authenticated ─> denied (no rows)
        └─> bot service_role client ─> bypasses RLS, health probe (guild+ticket) still passes
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `bot/utils/brand.py` | Modify | Add `ACCENT_A=0xFF2E97`, `ACCENT_B=0x00E5FF`; keep `ACCENT`, `GREETING_ACCENT==ACCENT` |
| `bot/services/greeting_renderer.py` | Modify | Add `theme_id` param to `render()` + Protocol; `_render_neon` branch (hex polygon, GaussianBlur, ACCENT_A→B diagonal) |
| `bot/models/greeting_config.py` | Modify | Add `theme_id: str \| None = None`; round-trip in `from_db_row`/`to_db_dict` |
| `bot/core/db/greeting_db.py` | Modify | Explicit cols (no `select("*")`); `upsert_greeting_config` `23505` handling (`on_conflict="guildId"`) |
| `bot/services/greeting_service.py` | Modify | Pass `config.theme_id` to renderer; avatar cache `cache_key(gid,"greeting_avatar")` 60s TTL |
| `bot/utils/time.py` | Modify | Add `parse_duration_strict` + `format_remaining`; reaffirm DO-NOT-MERGE docstring |
| `bot/models/ticket.py` | Modify | Add `scheduled_close_at`/`scheduled_close_by` fields + round-trip |
| `bot/core/db/ticket_db.py` | Modify | `get_scheduled_close_candidates` (explicit cols, batch 50); clear-on-close helpers |
| `bot/cogs/tickets.py` | Modify | Extend `on_message` (`,<dur>`/`,cancel`); `scheduled_close_loop` 60s task; `cog_unload` cancel |
| `bot/services/ticket_service.py` | Modify | `schedule_close`/`cancel_scheduled_close` (delegate to query/lifecycle); clear in `close_ticket_full` |
| `bot/cogs/sentinel.py` | Modify | `_validate_target` author-hierarchy deny (owner exempt) |
| `bot/cogs/ticket_admin_flow.py` | (none) | Service guild-scope check unchanged; only command guard changes |
| `bot/cogs/tickets.py` (`delete_category`) | Modify | `@is_mod()`→`@is_admin()` |
| `bot/cogs/ocio.py` | Modify | Thin: delegate to `OcioService`; add `/8ball`; cooldowns + `CommandOnCooldown` handler |
| `bot/services/ocio_service.py` | Create | `get_random_banana()` (pool + 1% dorada + Pillow fallback) + `get_8ball_response()`; no Discord imports |
| `assets/images/banana/*.webp` | Create | 5–8 variants incl. `dorada.webp` |
| `bot/locales/{es,en}.json` | Modify | `ocio.8ball.*` (20 keys ×2), `ocio.banana.*` dorada key, timer embed keys, sentinel author-hierarchy key |
| `bot/core/db/base.py` | Modify | `AsyncClientOptions(schema="public", auto_refresh_token=False, persist_session=False)` |
| `bot/utils/embeds.py` (echo paths) | Modify | `escape_markdown` + `AllowedMentions` on ticket-subject/ban-reason/8ball echo |
| `dashboard/app/.../greeting/page.tsx` | Modify | `GreetingThemeSelector` + `themeId` field |
| `dashboard/lib/actions/greeting-actions.ts` | Modify | Extract + persist `themeId`; no webhook |
| `supabase/migrations/021_greeting_theme_id.sql` | Create | `ALTER TABLE greeting_config ADD COLUMN "themeId" TEXT` |
| `supabase/migrations/022_ticket_scheduled_close.sql` | Create | `scheduledCloseAt TIMESTAMPTZ`, `scheduledCloseBy TEXT`, partial index |
| `supabase/migrations/023_rls_remaining_tables.sql` | Create | `ENABLE ROW LEVEL SECURITY` ×7 |
| `tests/test_*.py` | Create/Modify | TDD RED-first per spec; ≥2329 stable, coverage stable |

## Interfaces / Contracts

```python
# bot/utils/time.py — NEW (same module, duration domain)
def parse_duration_strict(text: str) -> int | None:
    """Strict ^,\\s*(\\d+\\s*[smhdwy])+$ ; None on ,hola/,/12/1x (no 3600 fallback)."""
def format_remaining(seconds: int, *, guild_id: str) -> str:
    """Localized '12h' / '1d 6h' via t()."""

# bot/services/greeting_renderer.py — UNCHANGED Protocol + optional param
class GreetingRenderer(Protocol):
    def render(self, *, ..., theme_id: str | None = None) -> io.BytesIO: ...

# bot/services/ocio_service.py — NEW, no Discord imports
class OcioService:
    def get_random_banana(self) -> tuple[bytes, str, int]: ...  # (png_bytes, filename, cm)
    def get_8ball_response(self, guild_id: str) -> str: ...     # one of 20 localized

# bot/models/ticket.py — additive fields
@dataclass
class Ticket:
    ...
    scheduled_close_at: datetime | None = None
    scheduled_close_by: str | None = None
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|---------|
| Unit | `parse_duration_strict` (all scenarios incl. w/y/`,`/`12`/`1x`), `format_remaining` i18n | pytest-asyncio; pure function, no mocks |
| Unit | `OcioService.get_random_banana` (99%/1%/empty/corrupt), `get_8ball_response` (20 keys, i18n-isolated) | Direct calls, no Discord mocks; monkeypatch RNG + glob |
| Unit | `PillowGreetingRenderer.render(theme_id="gaming_neon")` PNG bytes (welcome+goodbye), no hex literal in source | `to_thread`; assert PNG magic bytes + `rg "#FF2E97"` in renderer → 0 |
| Unit | `GreetingConfig`/`Ticket` round-trip (null + non-null `theme_id`/`scheduledCloseAt/By`) | Dataclass in/out equality |
| Unit | Sentinel `_validate_target` author-hierarchy deny (RED first), owner exempt, bot-hierarchy unchanged | Mock Member top_role; assertion on deny embed |
| Unit | `delete_category` mod-denied (RED first), admin-allowed, service guild-scope unchanged | Mock `is_admin`/`is_mod` |
| Integration | `on_message` `,12h`/`,cancel` listener: open/claimed/closed/non-mod/DM/`,hola`/overwrite-extend | Mock Message+Guild+member; assert DB calls + pinned embed |
| Integration | 60s loop batch-50 idempotent + AUTO_CLOSE coexistence (double-close impossible via `transition_ticket_to_closed`) | Two concurrent calls → exactly one mutation |
| Integration | `ConfirmCancelView` `<2h`/`>5d` confirm/cancel/timeout/owner-only | Reuse existing view; assert timer set only on Confirm |
| Integration | `23505` on greeting upsert → no-op/retry; `AsyncClientOptions` flags present | Mock client raising 23505; inspect `acreate_client` kwargs |
| Migration | `021`/`022`/`023` additive + live `schema_migrations` validation; partial index predicate; RLS `rowsecurity=true` ×7 | SQL inspection + rollback `DROP`/`DISABLE` |
| Coverage | ≥2329 tests, coverage stable ≥84.82% | `pytest --cov`; no regression |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file
classification, or process-integration boundary. All changes are in-process
Python/Discord/Supabase with additive SQL migrations and no command
dispatch beyond the existing `on_message`/slash paths.

## Migration / Rollout

- **021** `greeting_config."themeId" TEXT` (nullable, default null→default theme).
- **022** `ticket."scheduledCloseAt" TIMESTAMPTZ`, `ticket."scheduledCloseBy" TEXT` + partial index `WHERE status IN ('open','claimed') AND "scheduledCloseAt" IS NOT NULL`.
- **023** `ENABLE ROW LEVEL SECURITY` on 7 remaining tables.
- Each migration: query live `schema_migrations` before apply; `DROP COLUMN`/`DROP INDEX`/`DISABLE ROW LEVEL SECURITY` on rollback.
- Runtime flags: `TICKET_TIMER_ENABLED=False` disables the 60s loop without disabling the 48h sweep.
- Neon: `theme_id` nullable → null renders default; hidden if absent.
- Stacked-to-main: PR1→PR2→PR3, each solo-revertible, each ≤800 lines.

## Open Questions

- [ ] Banana `.webp` assets: confirm 5–8 variants are licensed/original before shipping binaries.
- [ ] Confirm 2-palette neon hex values (`#FF2E97`/`#00E5FF`) are final (proposal lists them as binding).
- [ ] Whether dashboard `/welcome` Realtime refetch should be automatic or opt-in (spec says MAY).

## Key Learnings

1. `transition_ticket_to_closed` already guarantees exactly-one close via SELECT+UPDATE both carrying `status IN ('open','claimed')`, making the AUTO_CLOSE/scheduled-close coexistence idempotent by construction.
2. `cache.invalidate_guild` drops the entire `{guild_id}:*` prefix, so the new `{gid}:greeting_avatar` cache is invalidated for free by the existing `greeting_config` CDC subscription — no new invalidation wiring needed.
3. `bot/utils/time.py` and `bot/utils/timeparse.py` are distinct domains (duration vs DB timestamp); `parse_duration_strict` must be a NEW function in `time.py`, never a merge.
4. `python:3.11-slim` lacks `libcairo`, so neon MUST be Pillow procedural (`ImageFilter.GaussianBlur`) even when the cairosvg probe succeeds — the `bot.py:220` probe is acknowledged but never drives neon rendering in Cycle 2.
5. Bot-side `select("*")` cleanup is scoped to greeting + ticket-timer mixins only to keep PR3 within the 800-line review budget; economy/infraction are deferred to Cycle 3.
