# Exploration: Ticket UX & Branding Overhaul

## Current State

### Close Flow
- `TicketActionsView.close_button()` at `bot/views/tickets.py:466` does **immediate close** — no confirmation step.
- It defers ephemeral, calls `ticket_service.close_ticket_full()`, sends a closing embed, then sleeps 5s and deletes the channel.
- `close_ticket_full()` at `bot/services/ticket_service.py:863` orchestrates: transcript → upload → DB close → `asyncio.sleep(CHANNEL_DELETE_DELAY)` → `channel.delete()`.
- `CHANNEL_DELETE_DELAY = 5` exists in both `ticket_service.py:42` and `tickets.py:27`.
- **No countdown spam** — the 5-second delay is a silent `asyncio.sleep`.

### Claim Flow
- `TicketActionsView.claim_button()` at `bot/views/tickets.py:406` — single "Claim" button.
- If ticket is already claimed (`claimedBy != None`), it rejects with an ephemeral error embed.
- `claim_ticket()` at `ticket_service.py:211` — invariant: must be `open` + `claimedBy=None`.
- `transfer_ticket()` at `ticket_service.py:570` — exists but is only accessible via `/transfer` slash command (cog command at `tickets.py:554`), NOT via a button.
- **No unclaim** — there is no unclaim functionality anywhere. Once claimed, only `/transfer` can reassign.
- **No per-user button rendering** — Discord message components are SHARED. All users see the same buttons on the same message.

### Channel Naming
- Created at `tickets.py:136`: `channel_name = f"ticket-{tentative_max + 1:04d}"`
- Reopen at `ticket_service.py:519`: `channel_name = f"ticket-{int(ticket_number):04d}"`
- Subticket at `tickets.py:494`: `f"ticket-{tmax + 1:04d}"`
- Post-create rename at `ticket_service.py:854-859` if tentative number differs from actual.
- **No category or username in channel name.**

### Branding / Colors
- `bot/utils/embeds.py` defines 4 generic colors:
  - `COLOR_ERROR = 0xE74C3C` (red)
  - `COLOR_SUCCESS = 0x2ECC71` (green)
  - `COLOR_INFO = 0x3498DB` (blue)
  - `COLOR_WARNING = 0xF1C40F` (yellow)
- `FOOTER_ICON = "https://i.imgur.com/fvE4b0c.png"` — placeholder imgur URL.
- Logo assets exist at `logo/Nebulosa-4x4.png` and `logo/Nebulosa-Banner.png`.
- `build_ticket_embed()` at `embeds.py:137` — uses `COLOR_SUCCESS` for open, `COLOR_INFO` for claimed.
- Some embeds bypass `_make_embed()` and build raw `discord.Embed` directly (e.g., `tickets.py:250`, `tickets.py:643`).
- All 7 cogs + 2 listeners build embeds; heavy consumers: `tickets.py`, `sentinel.py`, `stellar.py`, `core.py`.
- `logging_service.py` builds embeds without using the embed helpers at all.
- **No guild-specific asset handling.** `FOOTER_ICON` is a single hardcoded global URL.

### Guild vs Bot Assets
- `guild.icon` is available on `discord.Guild` objects — each guild has its own icon.
- `bot.user.display_avatar` gives the bot's avatar — consistent across guilds.
- Current code never uses `guild.icon` for embeds (only `utility.py:86` uses it for the `/server` command).
- Greeting cards use user avatars, not guild/bot branding.

### Test Coverage
- 10 test files for tickets (unit, contract, integration).
- `test_ticket_views.py` — 481 lines covering panel deploy, modal, embed rendering.
- `test_ticket_service.py` — 1899 lines covering all service methods.
- `test_ticket_invariants.py` + `tests/contract/test_ticket_invariants.py` — invariant contract tests.

### Existing Specs
- `openspec/specs/ticket-views/spec.md` — 241 lines, covers panel, actions, reopen, persistence.
- `openspec/specs/ticket-service/spec.md` — 311 lines, covers create, claim, close, transfer, notes, audit.

## Affected Areas

- `bot/views/tickets.py` — Close confirmation, countdown, claim/unclaim buttons, view construction.
- `bot/services/ticket_service.py` — Close flow with countdown, unclaim method, channel naming.
- `bot/services/ticket_invariants.py` — New `check_can_unclaim()` invariant.
- `bot/utils/embeds.py` — Brand palette, footer icon, guild-aware asset helpers.
- `bot/cogs/tickets.py` — Slash commands, embed usage.
- `bot/cogs/sentinel.py`, `bot/cogs/stellar.py`, `bot/cogs/core.py`, `bot/cogs/greetings.py`, `bot/cogs/utility.py`, `bot/cogs/ocio.py` — All use embed helpers.
- `bot/services/logging_service.py` — Builds embeds without helpers.
- `bot/bot.py` — `setup_hook()` view registration, potential bot asset preload.
- `bot/models/ticket.py` — No structural change needed (subject already stored).
- `logo/Nebulosa-4x4.png`, `logo/Nebulosa-Banner.png` — Source assets for branding.
- `tests/test_ticket_views.py`, `tests/test_ticket_service.py` — New tests for close confirm, countdown, unclaim.
- `openspec/specs/ticket-views/spec.md`, `openspec/specs/ticket-service/spec.md` — Delta specs needed.

## Approaches

### 1. Close Confirmation + Countdown

**Approach A: View Edit (replace buttons)**
- On Close press → edit the message to show Confirm/Cancel buttons (new persistent view or ephemeral).
- On Confirm → proceed with `close_ticket_full()` + countdown messages.
- Pros: Clean UX, visible to all in channel, no ephemeral complexity.
- Cons: Requires a new `CloseConfirmView` with static `custom_id`s for persistence, or ephemeral-only (not persistent — disappears on restart).
- Effort: **Low**

**Approach B: Ephemeral Confirm Follow-up**
- On Close press → send ephemeral "Are you sure?" with Confirm/Cancel buttons.
- On Confirm → run close + countdown.
- Pros: Simple, doesn't modify the main message. Ephemeral views don't need persistence.
- Cons: Only the closer sees the confirmation. If they dismiss it, nothing happens (clean cancel).
- Effort: **Low**

**Recommendation**: **Approach B (Ephemeral Confirm)** — simpler, doesn't require a new persistent view, naturally handles "dismiss = cancel". The countdown messages are sent to the channel so everyone sees them.

**Countdown implementation**: After confirm, loop 5→1 sending one message per second to the channel, then delete. This means 5 extra messages in the channel before deletion — acceptable for a channel about to be destroyed.

### 2. Claim / Unclaim UX

**Discord Constraint (CRITICAL)**:
- Message components (buttons) are **SHARED** — every user sees the same buttons on the same message.
- You CANNOT render different buttons per user on a public message.
- Ephemeral messages are per-user but cannot replace/modify a public message's components.

**Approach A: Single Toggle Button (Claim/Unclaim)**
- Button always says "Claim" when unclaimed, "Unclaim" when claimed.
- On click: if unclaimed → claim it. If claimed by YOU → unclaim. If claimed by OTHER → ephemeral error "Already claimed by X, use /transfer".
- The button label changes via `interaction.response.edit_message()` after each action.
- **Problem**: After claim, the button says "Unclaim" — but ALL users see "Unclaim", not just the claimer. A non-claimer clicking "Unclaim" would need an ephemeral rejection. Confusing UX.
- Effort: **Medium**

**Approach B: Claim Button + Status Embed (Recommended)**
- Keep a single "Claim" button (current behavior).
- After claim: edit the embed to show "Claimed by @Daniel" (already done in `build_ticket_embed`).
- Add an "Unclaim" button that appears ONLY after claim (via view edit — add/remove buttons dynamically).
- **Problem**: Adding/removing buttons on a persistent view with `timeout=None` and static `custom_id` is tricky. Discord.py does support editing a message's view to add/remove components.
- **Better**: Use a fixed set of 3 buttons: Claim, Unclaim, Transfer. Disable/hide the irrelevant ones.
- Effort: **Medium**

**Approach C: Claim Button + /unclaim Slash Command**
- Keep the existing Claim button as-is.
- Add `/unclaim` slash command (mod-only) that clears `claimedBy` and resets status to `open`.
- No button complexity — slash commands are per-user by nature.
- Button shows "Claim" always; status shown in embed.
- Effort: **Low**

**Approach D: Fixed 3-Button Layout (Claim / Unclaim / Transfer)**
- Three persistent buttons on every ticket: ✋ Claim, 🔓 Unclaim, 🔄 Transfer.
- Claim: enabled when `open` + `claimedBy=None`. Disabled otherwise.
- Unclaim: enabled when `claimedBy == interaction.user.id`. Disabled otherwise.
- Transfer: enabled when ticket is claimed. Opens a member select.
- **Key insight**: We can disable buttons conditionally by editing the view on each action. BUT persistent views with `timeout=None` reuse the same `custom_id` — the button state (enabled/disabled) is per-message, not per-view-instance. So after claim, we edit the message to disable Claim and enable Unclaim.
- **Problem**: On bot restart, `add_view()` re-registers the view with default button states. The message in Discord still shows the OLD button states (from the last edit), so this actually works — Discord caches the message component state independently of the view registration.
- Effort: **Medium-High**

**Recommendation**: **Approach C (Slash command for unclaim)** is the most pragmatic. It avoids button complexity entirely, follows existing patterns (`/transfer` already exists as a slash command), and is clear about what it does. For v1, this is the sensible choice. Approach D is the premium UX but adds significant complexity.

### 3. Channel Naming

**Current**: `ticket-{number:04d}` (e.g., `ticket-0042`)

**Option A: `{category-slug}-{username}-{number}`**
- Example: `support-danielxxomg-0042`
- Requires: category name from `TicketCategory`, username from `interaction.user`.
- Sanitization: lowercase, replace spaces with `-`, strip non-alphanumeric except `-`, truncate to fit 100 chars.
- Pros: Immediately identifiable — who opened it, what category.
- Cons: Longer names, username changes won't auto-update (cosmetic only, acceptable).
- Effort: **Low**

**Option B: `{category-slug}-{number}`**
- Example: `support-0042`
- Simpler, still shows category context.
- Pros: Shorter, no username dependency.
- Cons: Less context about who opened the ticket.
- Effort: **Low**

**Option C: `{username}-{number}` (no category)**
- Example: `danielxxomg-0042`
- Pros: Shows who, keeps number for reference.
- Cons: No category context.
- Effort: **Low**

**Discord constraints**:
- Channel name max 100 chars.
- Must be lowercase.
- Allowed: `a-z`, `0-9`, `-`, `_` (spaces become `-` on creation).
- Unicode is technically allowed but unreliable across clients.

**Recommendation**: **Option A** — most informative. Keep ticket number as suffix for uniqueness and reference. The category slug comes from `TicketCategory.name` (already stored). Sanitize with: `name.lower().replace(" ", "-")`, strip non `[a-z0-9-]`, truncate to leave room for username and number.

### 4. Brand Assets Strategy

**Discord ButtonStyle limitation**: Only 5 styles exist — `primary` (blurple), `secondary` (grey), `success` (green), `danger` (red), `link` (grey, opens URL). You CANNOT set arbitrary hex colors on buttons.

**Embed colors**: Fully customizable via hex int — can use any palette.

**Approach: Brand Tokens Module**
- Create `bot/utils/brand.py` with named constants:
  ```python
  PRIMARY = 0x9B5DE5      # Main purple
  ACCENT = 0xA855F7        # Brighter purple
  SUCCESS = 0x7C3AED       # Deep violet (mapped to success context)
  WARNING = 0xF59E0B       # Amber (warm, palette-adjacent)
  ERROR = 0xEF4444         # Red (keep distinct for errors)
  INFO = 0x8B5CF6          # Light violet
  SURFACE = 0x1E1B2E       # Dark surface (for embed backgrounds — N/A, Discord sets bg)
  ```
- Replace `COLOR_*` constants in `embeds.py` with brand tokens.
- `FOOTER_ICON`: Use `bot.user.display_avatar.url` (resolved at runtime, not hardcoded).
- Guild-specific: Use `guild.icon.url` for guild-context embeds (server info, logging). Use bot avatar for bot-context embeds (help, status).

**Where guild icon vs bot icon**:
| Context | Asset | Reason |
|---------|-------|--------|
| Ticket panel embed | Guild icon | Per-server identity |
| Ticket welcome embed | Bot icon | Bot is the "host" |
| Error/success/info embeds | Bot icon | Bot responses |
| Logging/audit embeds | Guild icon | Server context |
| Greeting cards | User avatar (already done) | Personal |
| `/server` command | Guild icon (already done) | Server info |
| `/botinfo` command | Bot icon | Bot identity |
| Ticket panel footer | Bot icon | Bot branding |

**File attachments for local assets**: Discord embeds can reference URLs or use `attachment://filename.ext` with a file attachment. For `set_footer(icon_url=...)` and `set_thumbnail(url=...)`, we need a publicly accessible URL. Options:
1. Upload logo to a CDN once, hardcode the URL (simplest, but not multi-server aware).
2. Use `bot.user.display_avatar.url` for bot branding (always available, no hosting needed).
3. For guild icons: `guild.icon.url` (Discord-hosted, always available).

**Recommendation**: Use `bot.user.display_avatar.url` for bot brand footer icon (replaces the placeholder imgur URL). Use `guild.icon.url` where guild context is appropriate. No need to host logo files separately for embed icons — the bot's avatar IS the brand. For the banner (e.g., ticket panel embed image), upload once to Discord via a command or use the bot's asset URL.

### 5. Visual Palette

**Brand palette from logo** (estimated):
- Primary: `#9B5DE5` (purple)
- Accent: `#A855F7` (bright violet)
- Deep: `#7C3AED` (deep violet)
- Lavender highlight: `#C4B5FD`
- Background: `#0A0A0A` / `#1A1A2E` (dark, near-black)

**Mapping to embed roles**:
| Role | Current | Proposed | Notes |
|------|---------|----------|-------|
| Error | `#E74C3C` (red) | `#EF4444` (slightly warmer red) | Keep red for errors — must be distinct |
| Success | `#2ECC71` (green) | `#10B981` (emerald) | Warmer green, palette-adjacent |
| Info | `#3498DB` (blue) | `#8B5CF6` (violet) | Brand primary for info |
| Warning | `#F1C40F` (yellow) | `#F59E0B` (amber) | Warmer, less jarring |
| Ticket open | `#2ECC71` | `#10B981` | Same as success |
| Ticket claimed | `#3498DB` | `#8B5CF6` | Brand violet |
| Panel/brand | `#3498DB` | `#9B5DE5` | Brand primary |

**Button styles** (what we CAN control):
- `ButtonStyle.primary` = blurple (~#5865F2) — close to brand, but NOT customizable.
- `ButtonStyle.success` = green — we can't change this to purple.
- `ButtonStyle.danger` = red — stays red.
- `ButtonStyle.secondary` = grey — neutral.

**Conclusion**: Buttons are NOT recolorable. We can only choose which semantic style to assign. Embeds are fully recolorable. This is a Discord platform limitation, not a discord.py limitation.

## Key Decisions for Proposal Phase

1. **Close confirmation**: Ephemeral follow-up (recommended) vs view edit. Ephemeral is simpler and handles dismiss-as-cancel naturally.

2. **Countdown spam**: 5 messages (5,4,3,2,1) in the channel before delete. Should these be individual messages or one message that's edited? Individual messages = more API calls but dramatic effect. One edited message = cleaner but less "spam" feel. **Recommend individual messages** — the channel is being destroyed anyway.

3. **Unclaim UX**: Slash command `/unclaim` (recommended for v1) vs button approach. Slash command is simpler, follows existing `/transfer` pattern, avoids button state management complexity.

4. **Channel naming**: `{category}-{username}-{number}` (recommended). Needs sanitization function. Ticket number kept for uniqueness and reference.

5. **Brand palette**: Create `bot/utils/brand.py` with token constants. Replace `COLOR_*` in `embeds.py`. Use `bot.user.display_avatar.url` for footer icon. Use `guild.icon.url` for guild-context embeds.

6. **Banner image**: Upload `logo/Nebulosa-Banner.png` to Discord CDN (via bot command or one-time upload) and store the URL. Or use `bot.user.banner.url` if the bot has a banner set on Discord.

## Open Product Questions

1. **Countdown format**: Individual messages (5,4,3,2,1) or single edited message? (Recommend: individual for drama)
2. **Auto-close countdown**: Should the 48h auto-close also get a countdown, or stay silent? (Recommend: silent — auto-close is already non-interactive)
3. **Unclaim clears status**: Does unclaim reset status to `open` or keep it `claimed` with `claimedBy=None`? (Recommend: reset to `open` — consistent with invariant `check_can_claim` which requires status=`open`)
4. **Channel name on reopen**: Should reopened tickets get the new naming format, or keep the old `ticket-NNNN`? (Recommend: new format — consistency)
5. **Banner hosting**: Upload to Discord CDN once and hardcode URL, or use bot's Discord profile banner? (Recommend: profile banner if available, fallback to CDN URL)
6. **Brand adoption scope**: Apply brand palette to ALL cogs immediately, or tickets-first? (Recommend: all at once — it's just color constant replacement)

## Risks

- **Persistent view button state after restart**: Editing button enabled/disabled state on a persistent view works, but `add_view()` on restart registers default states. The MESSAGE retains its edited component state in Discord, so this is actually safe — but needs testing.
- **Countdown API rate limits**: 5 rapid messages + delete = 6 API calls in 5 seconds. Within Discord's rate limits (50 messages/second per channel) but should add a small buffer (1.0s sleep between countdown messages).
- **Channel name sanitization edge cases**: Unicode usernames, extremely long names, special characters. Need robust sanitization.
- **Multi-server brand consistency**: If bot avatar changes, all embeds update. If we use CDN URLs for banner, they're static. Design decision: avatar-based is self-updating.
- **400-line PR budget**: This change touches many files. Likely needs chained PRs (brand palette, close UX, claim/unclaim, channel naming as separate slices).

## Ready for Proposal

**Yes** — exploration is complete. The orchestrator should proceed to `sdd-propose` with:
- 6 workstreams identified (close confirm, countdown, unclaim, channel naming, brand palette, brand assets)
- Recommended approaches for each with clear tradeoffs
- Discord platform constraints documented
- Open questions listed above need user/product decisions before spec phase
