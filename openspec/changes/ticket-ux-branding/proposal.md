# Proposal: Ticket UX & Branding Overhaul

## Intent

Ticket system lacks close confirmation, unclaim, descriptive channel names, and brand colors. Adds safety, staff control, and visual identity.

## Scope

### In Scope
- Ephemeral Confirm/Cancel before manual close (dismiss = cancel)
- Single-edit countdown (5→1) then channel delete
- `/unclaim` — claimer OR mods
- Claim-on-claimed → confirm → `transfer_ticket`
- Channel naming: `{category}-{username}-{number}`, sanitized
- Brand palette: purple/violet embeds; `bot.user.display_avatar` footer; `guild.icon` for guild-context
- Update `docs/MANUAL.md` (Spanish absolute manual) for new/changed ticket UX: close confirm + countdown, `/unclaim`, claim-on-claimed transfer, channel naming, branding notes as user-facing behavior

### Out of Scope
- Button colors (Discord limit), logo CDN, per-user buttons, auto-close countdown
- Full marketing rewrite of MANUAL beyond the behaviors this change ships

## Capabilities

### New
- `close-confirmation`: Ephemeral Confirm/Cancel; reuse `ConfirmCancelView`
- `close-countdown`: One message edited 5→1 then delete; auto-close silent
- `unclaim-command`: `/unclaim` hybrid; claimer OR mods; resets to `open`/`null`
- `channel-naming`: `{category}-{username}-{number}`; sanitize + truncate 100 chars; all create/rename paths
- `brand-tokens`: Purple/violet palette replacing `COLOR_*`

### Modified
- `ticket-views`: Close → confirm; claim-on-claimed → transfer confirm
- `ticket-service`: `unclaim_ticket()`, countdown, channel naming
- `ticket-invariants`: `check_can_unclaim()` — claimer OR mods

## Approach

Ephemeral follow-up for close confirm (dismiss=cancel). Countdown: post one message, edit each second, delete channel. `/unclaim` follows `/transfer` pattern. Claim-on-claimed: ephemeral transfer confirmation. `sanitize_channel_name()` helper in `ticket_helpers.py`. Replace `COLOR_*` in `embeds.py`; default footer to `bot.user.display_avatar.url`.

## Affected Areas

- `bot/utils/embeds.py` — brand palette, guild footer
- `bot/views/tickets.py` — close confirm, claim transfer
- `bot/services/ticket_service.py` — unclaim, countdown, naming
- `bot/services/ticket_invariants.py` — `check_can_unclaim()`
- `bot/utils/ticket_helpers.py` — `sanitize_channel_name()`
- `bot/cogs/tickets.py` — `/unclaim` command
- `bot/cogs/{sentinel,stellar,core}.py` — color tokens
- `bot/services/logging_service.py` — brand palette
- `tests/test_ticket_*.py` — new coverage
- `docs/MANUAL.md` — document new/changed ticket staff and user flows

## Risks

- Button state after restart: Low — Discord caches message state
- Countdown rate limits: Low — 1s sleep between edits
- Name sanitization edge cases: Med — robust function + truncation

## Rollback Plan

Each PR independent: restore `COLOR_*`; remove confirm view; restore direct close; remove `/unclaim`; restore `ticket-{number}` naming.

## Dependencies

- `ConfirmCancelView` from `confirm-dialog` spec
- `transfer_ticket()` existing method

## Success Criteria

- [ ] Close → ephemeral confirm; dismiss = no close
- [ ] Confirm → countdown 5→1 → delete; auto-close silent
- [ ] `/unclaim` for claimer + mods → `open`/`null`
- [ ] Claim-on-claimed → transfer confirmation
- [ ] Channels: `{category}-{username}-{number}`
- [ ] Embeds: brand palette + bot avatar footer; guild embeds use `guild.icon`
- [ ] `docs/MANUAL.md` updated for close confirm/countdown, `/unclaim`, transfer-on-claim, channel naming
- [ ] Tests pass (existing + new)

## Multi-PR Forecast

4–5 PRs under review budget 1500 (prefer ~300–400 lines each when chaining): (1) Brand palette, (2) Close confirm + countdown, (3) Unclaim + claim transfer, (4) Channel naming, (5) MANUAL.md docs slice (or fold MANUAL into the last behavior PR). Chained: auto-forecast if a slice exceeds budget.
