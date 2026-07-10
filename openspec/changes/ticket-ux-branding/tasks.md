# Tasks: Ticket UX & Branding Overhaul

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1,320 (across 4 chained PRs) |
| 400-line budget risk | High (single PR would exceed) |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 |
| Delivery strategy | auto-forecast |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Brand palette + asset resolvers | PR 1 | Foundation; no ticket logic. Tests + brand.py + embeds + cog adoption. |
| 2 | Close confirmation + countdown | PR 2 | Depends on PR 1 (brand tokens in embeds). Ephemeral view + countdown service. |
| 3 | Unclaim + claim-transfer | PR 3 | Depends on PR 1. Invariant + service + cog + transfer confirm view. |
| 4 | Channel naming + Spanish manual | PR 4 | Depends on PR 1. Sanitizer + service wiring + docs/MANUAL.md. |

---

## PR 1: Branding & Assets (~330 lines)

### Phase 1.1: Brand Tokens Foundation

- [x] 1.1.1 RED: Write `tests/test_brand.py` — assert `brand.py` exports PRIMARY, ACCENT, SUCCESS, WARNING, ERROR, INFO with correct hex values
- [x] 1.1.2 GREEN: Create `bot/utils/brand.py` — export 6 color constants per brand-tokens spec
- [x] 1.1.3 REFACTOR: Verify `uv run pytest tests/test_brand.py` passes

### Phase 1.2: Embed Factories + Asset Resolvers

- [x] 1.2.1 RED: Write `tests/test_embeds.py` additions — `_make_embed()` uses `PRIMARY` not `COLOR_DEFAULT`; footer icon resolves from `bot.user.display_avatar.url`; `guild_footer_icon()` returns guild icon or bot fallback
- [x] 1.2.2 GREEN: Modify `bot/utils/embeds.py` — replace `COLOR_*` with brand imports; add `bot_avatar_url(bot)` and `guild_footer_icon(guild, bot)` resolvers; update `_make_embed()` and `build_ticket_embed()` signatures to accept optional `bot`/`guild` *(R2-001 fix: `build_ticket_embed` now accepts `bot`/`guild` kwargs and wires footer icon)*
- [x] 1.2.3 REFACTOR: Remove dead `COLOR_*` constants and `FOOTER_ICON` from `embeds.py`

### Phase 1.3: Cog & Service Adoption

- [x] 1.3.1 RED: Update `tests/test_sentinel_cog.py`, `tests/test_stellar_cog.py`, `tests/test_bot.py`, `tests/test_greetings_cog.py`, `tests/test_utility_cog.py` — replace `COLOR_*` assertions with brand token assertions
- [x] 1.3.2 GREEN: Modify `bot/cogs/sentinel.py`, `bot/cogs/stellar.py`, `bot/cogs/core.py`, `bot/cogs/utility.py`, `bot/listeners/xp_listener.py` — import from `brand.py`, replace all `COLOR_*` references
- [x] 1.3.3 GREEN: Modify `bot/services/logging_service.py` — use brand tokens and guild asset resolver *(R2-001 fix: `_send_log` now resolves guild via `bot.get_guild(guild_id)` and applies `guild_footer_icon(guild, bot)` to every log embed footer)*
- [x] 1.3.4 REFACTOR: `uv run pytest` — all existing tests pass with brand tokens *(R2-001 fix: also wired `deploy_ticket_panel`, `_create_ticket_after_modal`, `TicketActionsView.claim_button`, and `TicketActionsView.close_button` to pass `bot`/`guild` to embed factories)*

---

## PR 2: Close Confirmation + Countdown (~320 lines)

### Phase 2.1: i18n Keys

- [x] 2.1.1 Add close confirmation keys to `bot/locales/en.json` and `bot/locales/es.json` (confirm_title, confirm_description, confirm_button, cancel_button, cancelled_message, timeout_message, unauthorized_message)

### Phase 2.2: Close Confirmation View

- [x] 2.2.1 RED: Write `tests/test_ticket_views.py` additions — close button triggers ephemeral `ConfirmCancelView`; confirm proceeds to close flow; cancel shows ephemeral message; dismiss/timeout keeps ticket open; other user's confirm rejected
- [x] 2.2.2 GREEN: Modify `bot/views/tickets.py` — close button callback sends ephemeral `ConfirmCancelView`; confirm callback calls `close_ticket_full(manual=True)`; cancel/third-party handled
- [x] 2.2.3 REFACTOR: `uv run pytest tests/test_ticket_views.py` passes

### Phase 2.3: Countdown Service

- [x] 2.3.1 RED: Write `tests/test_ticket_service.py` additions — `close_ticket_full(manual=True)` posts ONE message, edits 5→1 with 1s sleep, then deletes channel; `close_ticket_full(manual=False)` deletes silently; `CancelledError` logged and re-raised without deletion
- [x] 2.3.2 GREEN: Modify `bot/services/ticket_service.py` — add `manual` param to `close_ticket_full()`; implement countdown loop (send, edit 5..1, sleep, delete); keep silent path for auto-close
- [x] 2.3.3 REFACTOR: `uv run pytest tests/test_ticket_service.py` passes

### Phase 2.4: Auto-close Wiring

- [x] 2.4.1 RED: Write integration test — auto-close task calls `close_ticket_full(manual=False)`, no countdown messages posted
- [x] 2.4.2 GREEN: Update auto-close callers to pass `manual=False`
- [x] 2.4.3 Verify: `uv run pytest` — full suite green

---

## PR 3: Unclaim + Claim-Transfer (~350 lines)

### Phase 3.1: i18n Keys

- [x] 3.1.1 Add unclaim and transfer-confirm keys to `bot/locales/en.json` and `bot/locales/es.json`

### Phase 3.2: Unclaim Invariant

- [x] 3.2.1 RED: Write `tests/contract/test_ticket_invariants.py` additions — `check_can_unclaim(claimer, ticket)` grants; `check_can_unclaim(mod, ticket)` grants; `check_can_unclaim(other, ticket)` denies
- [x] 3.2.2 GREEN: Modify `bot/services/ticket_invariants.py` — add `check_can_unclaim(actor_id, ticket, *, is_mod)` with claimer-or-mod logic
- [x] 3.2.3 REFACTOR: `uv run pytest tests/contract/test_ticket_invariants.py` passes

### Phase 3.3: Unclaim Service

- [x] 3.3.1 RED: Write `tests/test_ticket_service.py` additions — `unclaim_ticket()` sets claimedBy=null, status=open, writes audit; unclaimed ticket raises `ValueError`
- [x] 3.3.2 GREEN: Modify `bot/services/ticket_service.py` — add `unclaim_ticket(ticket_id, actor_id, *, is_mod)` calling invariant then DB update + audit
- [x] 3.3.3 REFACTOR: `uv run pytest tests/test_ticket_service.py` passes

### Phase 3.4: Unclaim Command + Mod Predicate

- [x] 3.4.1 RED: Write `tests/test_tickets_cog.py` additions — `/unclaim` by claimer succeeds; by mod succeeds; by non-claimer non-mod rejected; on unclaimed ticket rejected
- [x] 3.4.2 GREEN: Add shared `is_mod_check` predicate to `bot/utils/checks.py`; modify `bot/cogs/tickets.py` — add `/unclaim` hybrid command using shared predicate
- [x] 3.4.3 REFACTOR: `uv run pytest tests/test_tickets_cog.py` passes

### Phase 3.5: Claim-on-Claimed Transfer Confirm

- [x] 3.5.1 RED: Write `tests/test_ticket_views.py` additions — claim on claimed ticket shows ephemeral transfer confirm; confirm calls `transfer_ticket()`; cancel dismisses
- [x] 3.5.2 GREEN: Modify `bot/views/tickets.py` — claim callback checks if ticket already claimed; if so, sends ephemeral `ConfirmCancelView` with transfer message; confirm calls `transfer_ticket()`
- [x] 3.5.3 Verify: `uv run pytest` — full suite green

---

## PR 4: Channel Naming + Spanish Manual (~320 lines)

### Phase 4.1: Sanitize Helper

- [ ] 4.1.1 RED: Write `tests/test_ticket_helpers.py` — `sanitize_channel_name("Soporte", "DanielXX", 42)` returns `soporte-danielxx-0042`; special chars stripped; empty inputs use fallbacks; long names truncated preserving `-{number:04d}` suffix
- [ ] 4.1.2 GREEN: Modify `bot/utils/ticket_helpers.py` — add `sanitize_channel_name(category, username, ticket_number)` with NFKD fold, lowercase, strip non-`[a-z0-9-]`, collapse hyphens, truncate to 100 preserving suffix
- [ ] 4.1.3 REFACTOR: `uv run pytest tests/test_ticket_helpers.py` passes

### Phase 4.2: Service Wiring

- [ ] 4.2.1 RED: Write `tests/test_ticket_service.py` additions — `create_ticket_channel()` uses `sanitize_channel_name()`; `reopen_ticket()` uses new naming format
- [ ] 4.2.2 GREEN: Modify `bot/services/ticket_service.py` — replace `ticket-{number:04d}` formatting in `create_ticket_channel()`, `reopen_ticket()`, and subticket paths with `sanitize_channel_name()` calls
- [ ] 4.2.3 REFACTOR: `uv run pytest tests/test_ticket_service.py` passes

### Phase 4.3: i18n Keys for Naming

- [ ] 4.3.1 Add channel naming format description key to `bot/locales/en.json` and `bot/locales/es.json` (if needed for panel embed)

### Phase 4.4: Spanish MANUAL.md

- [ ] 4.4.1 RED: Write `tests/test_manual.py` — assert `docs/MANUAL.md` exists, is non-empty, contains headings for close confirmation, `/unclaim`, transfer-on-claim, channel naming, brand palette
- [ ] 4.4.2 GREEN: Modify `docs/MANUAL.md` — update Spanish manual sections 1, 6, 7, 8: add close confirmation dialog behavior (dismiss=cancel), `/unclaim` command docs, claim-on-claimed transfer flow, `{category}-{username}-{number}` naming format, purple/violet brand note
- [ ] 4.4.3 REFACTOR: `uv run pytest tests/test_manual.py` passes; `uv run pytest` — full suite green

---

## Verification (per-PR)

After each PR slice:
1. `uv run pytest` — all tests pass
2. No `COLOR_*` references remain in modified files (PR 1)
3. Manual close shows countdown; auto-close is silent (PR 2)
4. `/unclaim` works for claimer and mods (PR 3)
5. New channels use `{category}-{username}-{number}` (PR 4)
6. `docs/MANUAL.md` covers all new behaviors (PR 4)
