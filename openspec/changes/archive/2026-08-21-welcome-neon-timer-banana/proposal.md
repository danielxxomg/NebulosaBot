# Proposal: welcome-neon-timer-banana

## Intent
Cycle 2/3 on `bce758d` (2329 tests 84.82%) — `gaming_neon` + `,12h` timer + banana/8ball + RLS. Hygiene done. Diagramas: greeting+ticket.

## Scope
### In Scope
- Greeting: `theme_id` nullable `021+` (no 019), Pillow neon `accent_a #FF2E97`/`accent_b #00E5FF` adjustable in review + `ACCENT 0xA855F7`, `GreetingRenderer` unchanged, `GreetingThemeSelector.tsx`+`greeting-actions.ts` Both CDC+`/welcome`, 60s `cache_key(gid,"greeting_avatar")`.
- Timer: `on_message` `^,\s*(\d+\s*[smhdwy])+$` via `parse_duration_strict` (fail `,hola`), open/claimed+`is_mod`, `2h 4h 6h 10h 1d 2d`+`1d12h`, `ConfirmCancelView` 30s if `<2h`/`>5d`, `scheduledCloseAt TIMESTAMPTZ`+`scheduledCloseBy`+partial index, `@tasks.loop(seconds=60)` batch 50 idempotent, `,cancel` clears, `⏳ Cierra <t:R> (<t:F>)`+`format_remaining()` channel-not-DM overwrite=extend.
- Ocio: `banana/*.webp` 5–8 + `OcioService.get_random_banana()` 1% dorada 30cm+Pillow fallback, ephemeral no DB, 8ball 20 i18n, `@cooldown(1,5,BucketType.user)`+`CommandOnCooldown`.
- Security: RLS remaining `service_role`, `AsyncClientOptions(auto_refresh_token=False,persist_session=False)`, `author.top_role <= target`, `delete_category is_mod→is_admin`, `escape_markdown`/`AllowedMentions`, `select("*")`→cols touched, `23505`.

### Out of Scope
Hygiene/DRY; `time.py` vs `timeparse.py` DO NOT MERGE; voice/`ScheduledAction`/`has_perm` Cycle 3; SVG/Jinja2+libcairo Pillow default; 19 PARTIALs ~6.

## Capabilities
### New Capabilities
- None
### Modified Capabilities
- `greeting-config`, `brand-tokens` (`#FF2E97`/`#00E5FF`), `welcome-goodbye`, `ticket-model`/`ticket-service`/`close-countdown`/`close-confirmation`, `time-parsing` (`parse_duration_strict` w/y), `ocio-commands`, `sentinel-commands`/`permission-model`, `database-layer`/`guards-contracts`

## Approach
Stacked-to-main auto-chain 800 lines, 3 slices (PR1 theming+cache, PR2 timer, PR3 ocio+security) solo-revertible. `GreetingRenderer` (`greeting_renderer.py:54`, `bot.py:230`) **Pillow default**, neon also **Pillow procedural** (hex+`GaussianBlur`+`accent_a→accent_b`), **SVG gated** `cairosvg` probe — no slim deps.

## Affected Areas
| Area | Impact | Description |
|------|--------|-------------|
| `greeting_renderer.py` | Modified | Theme + neon Pillow |
| `brand.py` | Modified | `ACCENT_A #FF2E97`/`B #00E5FF` |
| `migrations/021_*.sql` | New | `theme_id`+close+RLS |
| `cogs/tickets.py`/`time.py` | Modified | `on_message`+`parse_duration_strict` |
| `ticket_service.py` | Modified | 60s loop batch 50 |
| `dashboard/greeting/*` | Modified | Selector+Both |
| `ocio_service.py`/`banana/*.webp` | New | Pool+fallback |
| `sentinel.py`/`ticket_admin_flow.py` | Modified | Hierarchy+admin delete |

## Risks
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `scheduledCloseAt` vs `AUTO_CLOSE` | Med | Idempotent `already_closed`; clear on close; TDD |
| RLS blocks anon | Low | `service_role`; validate live |
| `select("*")` bloat | Med | Scope touched mixins |

## Rollback Plan
- **021+**: additive nullable — `DROP COLUMN`/`DROP INDEX`; null; validate `schema_migrations` live (drift 2026-08-19).
- **Loop**: `TICKET_TIMER_ENABLED=False` or `cog_unload()` cancels; stale harmless.
- **Ocio**: keep `banana.webp` fallback; Pillow placeholder if corrupt.
- **Neon**: `theme_id` nullable null→default; hidden if absent.

## Dependencies
`bce758d` green; `GreetingRenderer`+`brand.ACCENT`+CDC; `ConfirmCancelView` (`confirmation.py:47`); next `021+`.

## Success Criteria
- [ ] Neon `#FF2E97`/`#00E5FF` via `brand.py` adjustable, no `GREETING_ACCENT`, both PNG bytes TDD — gates spec→design→tasks.
- [ ] `,12h` strict regex fails `,hola`, channel+`is_mod`, `<2h`/`>5d` 30s confirm, `,cancel` clears, loop idempotent, `<t:R>/<t:F>`+`format_remaining()`.
- [ ] Banana 5–8+1% dorada 30cm+Pillow fallback, 8ball 20 i18n, `@cooldown(1,5)`+handler, no DB.
- [ ] RLS remaining, `AsyncClientOptions` flags, author deny+admin delete, no `select("*")` touched, escaping on.
- [ ] ≥2329 tests, coverage stable, each PR ≤800 lines solo-revertible, migration validated live.
