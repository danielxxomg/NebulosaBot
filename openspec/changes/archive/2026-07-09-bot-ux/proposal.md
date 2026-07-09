# Proposal: bot-ux

## Intent

Fix three UX gaps blocking guild admins and users: (1) ticket panel/action buttons show English labels to Spanish guilds after bot restart — the #1 i18n bug; (2) `/daily` gives a vague "come back tomorrow" with no countdown; (3) `/ban` and `/kick` execute instantly with no confirmation, risking accidental destructive actions.

## Scope

### In Scope — PR1 (primary slice, ~300-400 lines)

1. **Persistent view button labels** — resolve `t()` dynamically at interaction time using `interaction.guild_id`, so labels are correct even after restart.
2. **`/daily` exact cooldown** — return `remaining_seconds` from `EconomyService.claim_daily()`, format as `Xh Ym` in the cooldown embed.
3. **Ban/kick confirmation dialogs** — new `ConfirmCancelView` (ephemeral), reused by both commands. Timeout disables buttons.

### In Scope — PR2 (optional, same change, ~200-300 lines)

4. **Greeting config commands** — `/welcome config|channel|toggle|message` and `/goodbye` mirror. Admin-gated. Service layer already exists.

### Out of Scope

- Setup wizard rewrite
- `/guild_config` view command
- Paginator button i18n
- `/help` description i18n
- `/clear` bulk delete
- `/ticket_stats`
- DM notifications to mod targets

## Capabilities

### New Capabilities

- `confirm-dialog`: Reusable ephemeral Confirm/Cancel view for destructive mod actions (timeout, button disable, callback pattern).

### Modified Capabilities

- `ticket-views`: Persistent view requirement gains dynamic label resolution — button labels MUST be resolved via `t()` at interaction time, not only at construction.
- `economy-commands`: `/daily` cooldown scenario MUST include exact remaining time (`{remaining}` placeholder).
- `sentinel-commands`: `/ban` and `/kick` requirements gain confirmation step before execution.
- `welcome-goodbye`: Gains `ADDED` requirements for `/welcome` and `/goodbye` hybrid command groups with config, channel, toggle, message subcommands.

## Approach

- **Labels**: In each button callback, read `interaction.guild_id`, call `t(key, guild_id)`, set `button.label`, and `edit_message(view=self)`. English decorator defaults remain as fallback.
- **Cooldown**: Add `remaining_seconds` to `claim_daily()` return tuple (default 0 for backward compat). Format in cog with `h`/`m`.
- **Confirmations**: New `bot/views/confirmation.py` with `ConfirmCancelView(timeout=30)`. Sentinel `kick`/`ban` send ephemeral confirm embed before executing.
- **Greetings**: Leverage existing `GreetingService.get_config()`/`save_config()`. Add hybrid command groups in `greetings.py`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/bot.py:215-216` | Modified | Persistent view registration — no structural change, labels resolved at callback |
| `bot/views/tickets.py:29-90` | Modified | `TicketPanelView`, `TicketActionsView` callbacks add dynamic `t()` |
| `bot/services/economy_service.py:175-217` | Modified | `claim_daily()` returns `remaining_seconds` |
| `bot/cogs/stellar.py:79-85` | Modified | Cooldown embed shows formatted time |
| `bot/cogs/sentinel.py:432-536` | Modified | `kick`/`ban` add confirmation step |
| `bot/views/confirmation.py` | New | Reusable `ConfirmCancelView` |
| `bot/cogs/greetings.py` | Modified | Add `/welcome` and `/goodbye` command groups |
| `bot/locales/{es,en}.json` | Modified | New keys for confirmations, cooldown placeholder, greeting config |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| First interaction after restart still shows English briefly | Low | Acceptable — alternative (storing all guild→label mappings at startup) is heavier |
| `ConfirmCancelView` timeout edge case | Low | Disable buttons + send ephemeral "timed out" on timeout |
| `claim_daily` return type change breaks callers | Low | Add field as optional (default 0), existing callers ignore it |

## Rollback Plan

Each PR is independently revertable. PR1 touches views/service/cog without schema changes — `git revert` is clean. PR2 adds new commands only — revert removes commands, no data loss. No migrations required.

## Dependencies

- None. All i18n keys already exist or will be added to existing locale files.

## Success Criteria

- [ ] Spanish guild ticket buttons show localized labels after bot restart
- [ ] `/daily` cooldown embed shows exact `Xh Ym` remaining
- [ ] `/ban` and `/kick` show ephemeral confirmation before executing
- [ ] All existing tests pass (`uv run pytest`)
- [ ] No new `print()` calls, no blocking I/O in async context

## Proposal Question Round

Assumptions needing user review (execution_mode is auto, so questions are deferred):

1. **Confirmation timeout**: 30 seconds for ban/kick confirm — is that enough, or should it be longer for careful admins?
2. **Greeting subcommand count**: `/welcome` gets `config`, `channel`, `toggle`, `message` — should `embed_color` or `thumbnail` be configurable too, or is that dashboard-only?
3. **PR2 scope**: Greeting config is ~200-300 lines. Ship it in the same change (chained PR) or spin off as a separate change entirely?
