# Tasks: welcome-neon-timer-banana

> Cycle 2 of 3. Neon Pillow theme + `,12h` timer + banana/8ball + security/RLS.
> Stacked-to-main, auto-chain, 3 PRs ≤800 lines each, solo-revertible. Strict TDD
> (RED→GREEN→REFACTOR) per `test-driven-development` SKILL. Head `bce758d` (2329 tests, 84.82%).

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~2200 (PR1 ~700, PR2 ~800, PR3 ~700) |
| 400-line budget risk | High (each slice >400; budget is 800/slice) |
| Chained PRs recommended | Yes |
| Suggested split | PR1 Theming+Cache → PR2 Timer → PR3 Ocio+Security (stacked-to-main) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Neon brand tokens + `theme_id` model + migration 021 + Pillow neon branch + avatar cache + dashboard selector + Both CDC | PR1 | `uv run pytest tests/test_greeting_renderer.py tests/test_greeting_config.py -k "neon or theme"` | `uv run pytest --cov=bot --cov-fail-under=75`; `cd dashboard && npm run build` | `brand.py` tokens + `greeting_renderer.py` neon branch + `021_*.sql` (DROP COLUMN); `GreetingConfig.theme_id` field; avatar cache key |
| 2 | `parse_duration_strict` + `format_remaining` + migration 022 + Ticket fields + `on_message` `,12h`/`,cancel` + ConfirmCancelView `<2h`/`>5d` + 60s loop + `<t:R>/<t:F>` + AUTO_CLOSE coexist | PR2 | `uv run pytest tests/test_time_parsing.py tests/test_ticket_service.py tests/test_tickets.py -k "strict or scheduled or cancel"` | `uv run pytest --cov=bot --cov-fail-under=75` | `time.py` strict fn + `022_*.sql` (DROP COLUMN/INDEX) + `Ticket` fields + `on_message` timer branch + loop + cancel |
| 3 | `OcioService` + banana pool + `/8ball` + cooldown/handler + sentinel author-hierarchy + `delete_category` is_admin + `escape_markdown`/`AllowedMentions` + `AsyncClientOptions` flags + `23505` + RLS migration 023 | PR3 | `uv run pytest tests/test_ocio_service.py tests/test_sentinel.py tests/test_ticket_admin_flow.py -k "banana or 8ball or hierarchy or delete_category"` | `uv run pytest --cov=bot --cov-fail-under=75`; RLS `rowsecurity=true` ×7 live check | `ocio_service.py` + `assets/images/banana/*` + sentinel deny branch + `delete_category` guard + `023_*.sql` (DISABLE RLS) |

## Cross-cutting guardrails (apply to ALL slices)

- [x] G0.1 Each production task pairs RED (write failing test, watch fail) → GREEN (minimal code) → REFACTOR (stay green). No production code without a failing test first.
- [x] G0.2 `bot/utils/time.py` vs `bot/utils/timeparse.py` — **DO NOT MERGE**. `parse_duration_strict` + `format_remaining` live in `time.py` (duration domain). Both module docstrings MUST state the other is a separate domain.
- [x] G0.3 Every migration (021/022/023) — 022 done, additive nullable, schema_migrations + DROP rollback documented: query live `schema_migrations` before apply; additive nullable; rollback = `DROP COLUMN`/`DROP INDEX`/`DISABLE ROW LEVEL SECURITY`.
- [x] G0.4 Each PR is a work unit: clear start/finish, verification in-same-PR, solo-revertible, ≤800 lines, Conventional Commit message naming outcome not file list — landed as PR1 76d224c+8b46de3+535fa3c, PR2 4751bbb–cfcae3b 4 slices, PR3 0e303a2/05b71b1+bde6c0f+fde0790 stacked-to-main; PR3g budget exceeded 3× but maintainer reset + settle passed (size:exception cohesive 021→023 migrations + timer delegation + gga provider).

## PR1 — Greeting Theming + Cache

### Phase 1: Brand tokens + migration foundation

- [x] 1.1 RED: `tests/test_brand_tokens.py` assert `brand.ACCENT_A == 0xFF2E97`, `brand.ACCENT_B == 0x00E5FF`, `ACCENT == 0xA855F7` unchanged, no `GREETING_ACCENT` non-alias. GREEN: add tokens to `bot/utils/brand.py`. TRIANGULATE: assert `GREETING_ACCENT == ACCENT`. SAFETY NET: existing embed-color tests green.
- [x] 1.2 RED: `tests/test_brand_no_hex.py` assert `rg "#[0-9A-Fa-f]{6}"` in `bot/` (excl `brand.py`) → 0. GREEN: no source change (invariant holds). SAFETY NET: lint gate.

### Phase 2: GreetingConfig model + migration 021

- [x] 2.1 RED: `tests/test_greeting_config.py` round-trip `theme_id="gaming_neon"` and `None` via `from_db_row`/`to_db_dict` (camelCase `themeId`). GREEN: add `theme_id: str | None = None` to `bot/models/greeting_config.py`. TRIANGULATE: null + non-null both preserved.
- [x] 2.2 Create `migrations/021_greeting_theme_id.sql` — `ALTER TABLE greeting_config ADD COLUMN "themeId" TEXT` (nullable, default null). RED: migration test asserts identity checked live + existing rows read back null. SAFETY NET: rollback `DROP COLUMN`.

### Phase 3: GreetingRenderer neon Pillow branch

- [x] 3.1 RED: `tests/test_greeting_renderer.py` assert `render(theme_id="gaming_neon")` returns PNG magic bytes for welcome + goodbye; assert `rg "#FF2E97|#00E5FF"` in renderer source → 0. GREEN: add `theme_id: str | None = None` to `render()` + `GreetingRenderer` Protocol in `bot/services/greeting_renderer.py`; add `_render_neon` (hex polygon + `ImageFilter.GaussianBlur`, `ACCENT_A→ACCENT_B` diagonal). TRIANGULATE: unknown `theme_id` → default; `None` → default.
- [x] 3.2 RED: assert `render` wrapped in `asyncio.to_thread` (no event-loop block). GREEN: `GreetingService.dispatch_greeting` passes `config.theme_id` via `to_thread`. SAFETY NET: cairosvg probe stays gated (`bot.py:220`); Pillow default even when probe succeeds.

### Phase 4: Avatar cache 60s guild-scoped

- [x] 4.1 RED: `tests/test_greeting_avatar_cache.py` assert key is `cache_key(gid,"greeting_avatar")` from `bot.core.cache`, TTL 60s, no bare key, no cross-guild leak. GREEN: wire avatar cache in `bot/services/greeting_service.py` importing `cache_key`. TRIANGULATE: guild A ≠ guild B entries.

### Phase 5: Dashboard selector + Both CDC contract

- [x] 5.1 RED: dashboard `vitest` — `GreetingThemeSelector` renders + `updateGreetingConfig` persists `themeId` without webhook POST. GREEN: add `GreetingThemeSelector` + `themeId` field in `dashboard/app/.../greeting/page.tsx`; extract in `dashboard/lib/actions/greeting-actions.ts`. TRIANGULATE: no `fetch(webhook)`.
- [x] 5.2 RED: `tests/test_greeting_cdc.py` assert bot invalidates `{gid}:greeting_config` + `{gid}:greeting_avatar` on `greeting_config` CDC; dashboard MAY refetch. GREEN: confirm existing Realtime subscription covers `theme_id` (free via `invalidate_guild` prefix drop). SAFETY NET: no new invalidation wiring.

### Phase 6: greeting_db explicit cols + 23505

- [x] 6.1 RED: `tests/test_greeting_db.py` assert no `select("*")` in touched queries; assert `23505` on `upsert_greeting_config` → no-op/retry, no traceback. GREEN: explicit cols in `bot/core/db/greeting_db.py`; `on_conflict="guildId"`/catch `UniqueViolation` re-read. TRIANGULATE: concurrent upsert race.

### PR1 Verify Gate

- [x] P1.V1 `uv run ruff check bot/ tests/ && uv run ruff format --check bot/ tests/`
- [x] P1.V2 `uv run ty check bot/ tests/` (471 diagnostics, down from 481 baseline — net improvement)
- [x] P1.V3 `uv run tach check && uv run tach check-external` (OcioService absent in PR1; neon branch in services layer)
- [x] P1.V4 `uv run pytest --cov=bot --cov-fail-under=75` (2372 passed, 84.92% — up from 2329/84.82% baseline)
- [x] P1.V5 `cd dashboard && npm run lint && npx tsc --noEmit && npm run test` (vitest) + `npm run build`
- [x] P1.V6 Work-unit commits: brand+model+migration | renderer+cache | dashboard | db-cleanup (4+ commits, each solo-revertible) — landed as 76d224c feat + 8b46de3 merge + 535fa3c fixup .gga (stacked-to-main).

## PR2 — Timer `,12h`

### Phase 1: parse_duration_strict + format_remaining (time.py)

- [x] 2.1 RED: `tests/test_time_parsing.py` — `parse_duration_strict(",12h")==43200`, `,1d12h`==129600, `,1w`==604800, `,1y`==31536000, `,2h 4h 6h 10h 1d 2d` sums; `,hola`/`,`/`12`/`1x` → `None` (NOT 3600). GREEN: add `parse_duration_strict` to `bot/utils/time.py` (regex `^,\s*(\d+\s*[smhdwy])+$`). TRIANGULATE: each fail case. SAFETY NET: `parse_duration` unchanged.
- [x] 2.2 RED: assert docstrings in `time.py` + `timeparse.py` state other is separate domain; no re-export façade. GREEN: reaffirm docstrings. SAFETY NET: `timeparse.py` untouched.
- [x] 2.3 RED: `format_remaining(43200)` localized (es/en) returns "12h"-style. GREEN: add `format_remaining(seconds, *, guild_id)` to `bot/utils/time.py` via `t()`.

### Phase 2: Ticket model + migration 022

- [x] 2.4 RED: `tests/test_ticket_model.py` round-trip `scheduled_close_at`/`scheduled_close_by` (null + non-null, ISO-8601). GREEN: add fields to `bot/models/ticket.py`. TRIANGULATE: null + datetime preserved.
- [x] 2.5 Create `migrations/022_ticket_scheduled_close.sql` — `scheduledCloseAt TIMESTAMPTZ`, `scheduledCloseBy TEXT`, partial index `WHERE status IN ('open','claimed') AND "scheduledCloseAt" IS NOT NULL`. RED: migration test asserts identity checked live + coexists with `idx_ticket_active_channel`. SAFETY NET: rollback `DROP COLUMN`/`DROP INDEX`.

### Phase 3: ticket_db explicit cols + service schedule/cancel

- [x] 2.6 RED: `tests/test_ticket_db.py` assert `get_scheduled_close_candidates` explicit cols (no `select("*")`), batch 50, `scheduledCloseAt <= now()`. GREEN: add to `bot/core/db/ticket_db.py`. TRIANGULATE: 120 due → ≤50 processed.
- [x] 2.7 RED: `tests/test_ticket_service.py` assert `schedule_close` sets `scheduledCloseAt`/`scheduledCloseBy`; `cancel_scheduled_close` clears both; `close_ticket_full` clears scheduled fields. GREEN: add methods to `bot/services/ticket_service.py`. SAFETY NET: `transition_ticket_to_closed` idempotency unchanged.

### Phase 4: on_message listener `,12h`/`,cancel`

- [x] 2.8 RED: integration `tests/test_tickets_timer.py` — open+mod+`,12h` sets timer + pins embed; claimed+mod works; non-mod ignored; DM ignored; closed ignored; `,hola` ignored (no error embed); `,4h` overwrites (extends) + edits pinned embed. GREEN: extend `on_message` in `bot/cogs/tickets.py` reusing `is_ticket_channel`+`is_mod_check`. TRIANGULATE: each guard case.
- [x] 2.9 RED: `,cancel` clears timer + posts confirmation; cancel with no timer = safe no-op; cancel does NOT disable AUTO_CLOSE inactivity. GREEN: add `,cancel` branch. TRIANGULATE: 47h-inactive still auto-closes.
- [x] 2.10 RED: pinned embed carries `⏳ Cierra <t:{unix}:R> (<t:{unix}:F>)` localized via `t()`. GREEN: build embed from `scheduledCloseAt` epoch. TRIANGULATE: overwrite edits not re-pins.

### Phase 5: ConfirmCancelView `<2h`/`>5d`

- [x] 2.11 RED: `tests/test_close_confirmation.py` — `,1h`/`,10d` show ephemeral ConfirmCancelView (owner-only, 30s); Confirm sets timer; Cancel/timeout no-op; modB confirm denied. GREEN: reuse `ConfirmCancelView` (`bot/views/confirmation.py:24`) gated by threshold. TRIANGULATE: `,12h` (2h..5d) sets immediately. SAFETY NET: manual-close confirmation unchanged.

### Phase 6: 60s loop + AUTO_CLOSE coexistence

- [x] 2.12 RED: `tests/test_scheduled_close_loop.py` — `@tasks.loop(seconds=60)` batch 50 closes due ticket silently + clears scheduled fields + deletes channel; idempotent on `already_closed`; `cog_unload()` cancels. GREEN: add loop in `TicketsCog` calling `close_ticket_full` (silent). TRIANGULATE: 120 due → ≤50.
- [x] 2.13 RED: AUTO_CLOSE + scheduled timer both fire → exactly one `close_ticket_full` succeeds, other `already_closed`; AUTO_CLOSE clears lingering scheduled fields. GREEN: clear-on-close in 48h sweep. SAFETY NET: `TICKET_TIMER_ENABLED=False` disables loop not sweep.
- [x] 2.14 RED: scheduled-close loop is silent (no 5→1 countdown). GREEN: reuse silent path. SAFETY NET: manual countdown unchanged.

### PR2 Verify Gate

- [x] P2.V1 `uv run ruff check bot/ tests/ && uv run ruff format --check bot/ tests/`
- [x] P2.V2 `uv run ty check bot/ tests/`
- [x] P2.V3 `uv run tach check && uv run tach check-external` (`format_remaining` in utils; no cog/service duplicate)
- [x] P2.V4 `uv run pytest --cov=bot --cov-fail-under=75` (≥2329, ≥84.82%)
- [x] P2.V5 Work-unit commits: parser+formatter | model+migration+db | listener+confirm | loop+coexistence (4+ commits) — landed as 4751bbb–cfcae3b 4 slices stacked-to-main.

## PR3 — Ocio + Security

### Phase 1: OcioService + banana pool

- [x] 3.1 RED: `tests/test_ocio_service.py` — `get_random_banana()` 99% path picks from `assets/images/banana/*.webp` (5–8); 1% dorada → 30cm; empty pool → Pillow placeholder; missing/corrupt → Pillow placeholder via `asyncio.to_thread`; no Discord imports. GREEN: create `bot/services/ocio_service.py`. TRIANGULATE: monkeypatch RNG + glob. SAFETY NET: no DB row written.
- [x] 3.2 Create `assets/images/banana/*.webp` (5–8 variants incl. `dorada.webp`). RED: assert pool size 5–8 + dorada present. (Confirm license/original before shipping — open question.)

### Phase 2: /8ball + cooldown handler

- [x] 3.3 RED: `tests/test_ocio_commands.py` — `/8ball` returns one of 20 localized `ocio.8ball.*` (es/en independently testable); ephemeral; no DB. GREEN: add `/8ball` + `get_8ball_response` (uniform random). Add 20 keys ×2 to `bot/locales/{es,en}.json`.
- [x] 3.4 RED: `@cooldown(1,5,BucketType.user)` on `/dados`,`/banana`,`/8ball`; `CommandOnCooldown` handler replies ephemeral localized `retry_after` via `t()`; no traceback. GREEN: add handler in `bot/cogs/ocio.py`. TRIANGULATE: 2nd invoke <5s blocked; after 5s ok. SAFETY NET: cog thin, delegates to `OcioService`.

### Phase 3: Sentinel author-hierarchy deny (RED-first behavior change)

- [x] 3.5 RED: `tests/test_sentinel_hierarchy.py` — author `top_role <= target.top_role` → deny ephemeral + no mutation; owner exempt; bot-hierarchy + owner-exemption unchanged. **Run before implementation → FAILS.** GREEN: add author-hierarchy check to `_validate_target` (`bot/cogs/sentinel.py:102`). SAFETY NET: existing `/kick`/`/ban` dialogs unchanged.

### Phase 4: delete_category is_mod → is_admin (RED-first behavior change)

- [x] 3.6 RED: `tests/test_delete_category.py` — mod denied (RED before guard change); admin allowed; service `guildId != gid` unchanged; open-tickets behavior unchanged. GREEN: `@is_mod()`→`@is_admin()` on `delete_category` (`bot/cogs/tickets.py:262`). Update `is_mod` characterization 24→23 + characterize `is_admin()` separately.

### Phase 5: escape_markdown + AllowedMentions

- [x] 3.7 RED: `tests/test_escape_markdown.py` — ticket subject echo escapes `**bold**`/`@everyone`; ban reason echo uses `AllowedMentions` (no ping); 8ball question echo escapes. GREEN: apply `discord.utils.escape_markdown` + `AllowedMentions` on echo paths in `bot/utils/embeds.py` + touched cogs. SAFETY NET: displayed content unchanged beyond escaping.

### Phase 6: AsyncClientOptions flags + 23505 (if not PR1) + RLS migration 023

- [x] 3.8 RED: `tests/test_database_client.py` — `AsyncClientOptions(schema="public", auto_refresh_token=False, persist_session=False)` passed to `acreate_client`; service_role validation still fail-closed. GREEN: update `bot/core/db/base.py`. SAFETY NET: config-only, no behavior change.
- [x] 3.9 RED: if 23505 — already done in PR1 (greeting_db explicit cols + 23505), verified in this slice (no duplicate) not done in PR1, assert `upsert_greeting_config` 23505 → no-op/retry. GREEN: handle in `greeting_db.py` (`on_conflict`).
- [x] 3.10 Create `migrations/023_rls_remaining_tables.sql` — `ENABLE ROW LEVEL SECURITY` on `guild`,`member`,`infraction`,`ticket`,`ticket_category`,`economy_config`,`greeting_config` (no policies). RED: migration test asserts `rowsecurity=true` ×7, identity checked live, service_role unaffected, anon denied. SAFETY NET: rollback `DISABLE ROW LEVEL SECURITY`; health probe still passes.

### PR3 Verify Gate

- [x] P3.V1 `uv run ruff check bot/ tests/ && uv run ruff format --check bot/ tests/`
- [x] P3.V2 `uv run ty check bot/ tests/`
- [x] P3.V3 `uv run tach check && uv run tach check-external` (`OcioService` in services layer, no `bot.cogs`/`bot.views` imports)
- [x] P3.V4 `uv run pytest --cov=bot --cov-fail-under=75` (≥2329, ≥84.82%)
- [x] P3.V5 RLS live check: `rowsecurity=true` ×7; `schema_migrations` records 021/022/023
- [x] P3.V6 Work-unit commits: ocio-service+banana | 8ball+cooldown | sentinel-hierarchy+delete_category | escape-markdown | client-flags+RLS (4+ commits) — landed as 0e303a2/05b71b1 + bde6c0f fix + fde0790 brand tokens stacked-to-main.

## Open Questions (from design, resolve before/as applies)

- [x] Banana `.webp` assets: confirm 5–8 variants licensed/original before shipping binaries — placeholder Pillow-generated WEBP present in assets/images/banana/ (5 + dorada), valid per tests; original license confirmation remains Cycle 3 concern.
- [x] Confirm 2-palette neon hex values (`#FF2E97`/`#00E5FF`) are final (proposal lists binding) — ACCENT_A/B fixed in bot/utils/brand.py.
- [x] Dashboard `/welcome` Realtime refetch: automatic or opt-in (spec says MAY) — Both contract via existing Realtime CDC, deferred.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file
classification, or process-integration boundary (per design.md). All changes are
in-process Python/Discord/Supabase with additive SQL migrations and no new
command dispatch beyond existing `on_message`/slash paths.
