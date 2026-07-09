# Exploration: bot-ux

## Current State

NebulosaBot has 8 cogs, 8 services, 24 hybrid commands, and a fully-wired i18n system (`t()` with `es`/`en` locales). The i18n + ephemeral pass from `i18n-and-ephemeral-standard` resolved most string-hardcoding and ephemeral issues. Two HIGH-impact UX gaps and several MEDIUM items remain, identified by `audit-bot-ux-qa` and `audit-docs-gaps`.

This exploration consolidates those findings into a focused first-slice proposal.

---

## First Slice (this change)

### 1. Persistent View Button Labels After Restart — HIGH

**Problem**: `bot/bot.py:215-216` registers `TicketPanelView()` and `TicketActionsView()` without `guild_id`. Both constructors (`views/tickets.py:32-38`, `82-90`) only update button labels when `guild_id is not None`. After restart, the persistent views handle interactions with hardcoded English defaults ("Open Ticket", "Claim", "Close"), even for Spanish guilds.

**Root cause**: Discord restores persistent views from `custom_id` at startup. The `__init__` label override only runs at construction time. The `setup_hook()` call passes no guild context.

**Affected files**:
- `bot/bot.py:215-216` — persistent view registration
- `bot/views/tickets.py:29-90` — `TicketPanelView`, `TicketActionsView` constructors
- `bot/locales/{es,en}.json` — existing label keys (`tickets.panel.open_button`, `tickets.actions.claim_button`, `tickets.actions.close_button`)

**Approach**: Make button callbacks look up labels dynamically at interaction time. The `custom_id` already encodes intent (`ticket:open`, `ticket:claim`, `ticket:close`). In each callback, resolve `guild_id` from `interaction.guild_id` and call `t()` to get the localized label. Optionally call `button.label = t(...)` + `interaction.response.edit_message(view=self)` to update the label for the current interaction (discord.py allows editing the view during a response). The English defaults in decorators remain as fallback for the brief window before first interaction.

**Effort**: MEDIUM — touches 2 files, no new commands, no schema changes.

### 2. `/daily` Exact Cooldown Timer — MEDIUM

**Problem**: `stellar.py:80-83` shows `"come back tomorrow!"` without the exact time remaining. `economy_service.py:204-217` already computes `elapsed` and `cooldown_seconds` but only returns `(False, 0, streak)` — no remaining time.

**Fix**: Add `remaining_seconds` to the return tuple (or return it alongside the cooldown response). In `stellar.py`, format as `"You can claim again in Xh Ym"`. Update i18n keys `stellar.daily.cooldown_description` to accept a `{remaining}` placeholder.

**Affected files**:
- `bot/services/economy_service.py:175-217` — `claim_daily` return value
- `bot/cogs/stellar.py:79-85` — cooldown embed
- `bot/locales/{es,en}.json` — `stellar.daily.cooldown_description`

**Effort**: LOW — small change to one service method + one cog + locale keys.

### 3. Mod Action Confirmations (ban/kick) — MEDIUM

**Problem**: `/ban` (`sentinel.py:484-536`) and `/kick` (`sentinel.py:432-474`) execute immediately with no confirmation. Carl-bot and Dyno both show a confirmation embed with Confirm/Cancel buttons for destructive actions.

**Fix**: Before executing the action, send an ephemeral embed showing target, reason, and two buttons (Confirm / Cancel). On Confirm, proceed with the ban/kick. On Cancel (or timeout), send a cancellation message. Reuse the existing `is_mod_check` inside the confirmation callback.

**Affected files**:
- `bot/cogs/sentinel.py` — `kick`, `ban` command handlers
- `bot/views/confirmation.py` (NEW) — reusable `ConfirmCancelView`
- `bot/locales/{es,en}.json` — new confirmation keys

**Effort**: LOW — new ephemeral view + 2 command modifications.

### 4. Greeting Config Commands — HIGH (if capacity allows)

**Problem**: `greetings.py` has `/welcome_test` and `/goodbye_test` but NO configuration commands. Admins MUST use the dashboard or direct DB edits to set `welcome_channel_id`, `goodbye_channel_id`, enable/disable toggles, etc. `GreetingService` already has `get_config()` and `save_config()` — the service layer is ready.

**Fix**: Add a `/welcome` hybrid group with subcommands: `config` (show current), `channel` (set channel), `toggle` (enable/disable), `message` (set template). Mirror for `/goodbye`. All admin-gated with `@app_commands.default_permissions(administrator=True)`.

**Affected files**:
- `bot/cogs/greetings.py` — add `/welcome` and `/goodbye` command groups
- `bot/locales/{es,en}.json` — new greeting config keys

**Effort**: LOW — service layer exists, only cog commands needed.

---

## Later Backlog (out of scope for this slice)

| Item | Priority | Notes |
|------|----------|-------|
| `/guild_config` view command | MEDIUM | Show all guild config in one embed. Needs new cog command in `setup.py`. |
| Paginator button i18n | LOW | `paginator.py` uses English labels ("Previous", "Next", "Stop"). |
| `/help` description i18n | LOW | `cmd.description` is English from decorator. Needs `locale_map` or runtime override. |
| DM notifications to mod targets | MEDIUM | DM the warned/muted user the reason. Handle DM-disabled gracefully. |
| Setup wizard (interactive) | MEDIUM | Replace single `/setup` with embed + buttons/selects wizard. |
| `/clear` bulk delete | MEDIUM | Staff universally expect this. |
| `/ticket_stats` | MEDIUM | Open/closed/avg resolution time per guild. |
| Confirmation on `/delete_category` | LOW | Destructive action, no current confirmation. |

---

## Approaches

### A. First Slice Only (Recommended)

Ship items 1-3 as a single PR (~300-400 lines). Item 4 (greeting config) as a follow-up PR if the first is clean.

- Pros: Focused, reviewable, addresses the #1 i18n gap + two quick wins.
- Cons: Greeting config deferred to PR2.
- Effort: LOW-MEDIUM.

### B. Full 4-Item Slice

Ship all 4 items in one PR (~500-600 lines).

- Pros: Addresses both HIGH items in one shot.
- Cons: Higher review burden, greeting config adds scope.
- Effort: MEDIUM.

### C. Button Labels Only

Ship only item 1 (persistent view labels). Fastest path to fixing the #1 i18n gap.

- Pros: Minimal, surgical.
- Cons: Leaves MEDIUM items untouched.
- Effort: LOW.

---

## Recommendation

**Approach A** — ship items 1-3 as PR1, item 4 as PR2.

Rationale:
1. The persistent view label bug is the single highest-impact i18n gap — every ticket interaction after restart shows English to Spanish guilds.
2. The `/daily` cooldown fix is a one-method change with high user-visible value.
3. Mod confirmations are a standard expectation and the `ConfirmCancelView` is reusable.
4. Greeting config is important but adds enough scope (2 command groups + 8+ subcommands) to warrant a separate PR.

---

## Risks

- **R1**: Editing button labels at interaction time means the first interaction after restart still shows English briefly, then updates. This is acceptable — the alternative (storing all guild→label mappings at startup) is heavier.
- **R2**: `ConfirmCancelView` introduces a new interaction pattern. Must handle timeout gracefully (disable buttons, send "timed out" ephemeral).
- **R3**: Changing `claim_daily` return type could break callers. Add `remaining_seconds` as optional field (default 0) to maintain backward compat.

---

## Ready for Proposal

**YES**. The orchestrator should tell the user:

1. **PR1 scope**: Fix persistent view button labels (dynamic `t()` at interaction time), `/daily` exact cooldown timer, ban/kick confirmation dialogs. ~300-400 lines.
2. **PR2 scope**: Greeting config commands (`/welcome config|channel|toggle|message`, `/goodbye` mirror). ~200-300 lines.
3. Both PRs are independently shippable and low-risk.
4. Out of scope: setup wizard, `/guild_config`, paginator i18n, `/clear`, `/ticket_stats`, DM notifications.
