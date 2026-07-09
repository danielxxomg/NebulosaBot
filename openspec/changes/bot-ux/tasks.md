# Tasks: bot-ux

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 550-700 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 |
| Delivery strategy | auto-forecast |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Confirm dialog, daily cooldown, ban/kick confirmation | PR 1 | base: main; ~350-450 lines; tests + locales included |
| 2 | Greeting config commands + locales + tests | PR 2 | base: main (after PR 1 merges); ~200-250 lines |

---

## Phase 1: Foundation — ConfirmCancelView (PR 1)

- [x] 1.1 RED: write `tests/test_confirm_view.py` — test confirm executes callback, cancel sends ephemeral, timeout disables buttons, non-owner rejected
- [x] 1.2 GREEN: create `bot/views/confirmation.py` with `ConfirmCancelView(guild_id, owner_id, on_confirm, timeout=30)`
- [x] 1.3 REFACTOR: ensure owner-only guard uses `interaction.user.id == self.owner_id`

## Phase 2: Daily Cooldown (PR 1)

- [x] 2.1 RED: update `tests/test_economy_service.py` — `claim_daily` returns `(bool, int, int, int)` with `remaining_seconds=0` on success, `remaining_seconds > 0` on cooldown
- [x] 2.2 GREEN: modify `bot/services/economy_service.py:claim_daily()` to return `remaining_seconds` as 4th tuple element (default 0 for success)
- [x] 2.3 RED: update `tests/test_stellar_cog.py` — cooldown embed contains formatted `Xh Ym` string
- [x] 2.4 GREEN: modify `bot/cogs/stellar.py:79-85` to unpack `remaining_seconds`, format as `Xh Ym`, pass `{remaining}` to i18n key
- [x] 2.5 Add `stellar.daily.cooldown_description` with `{remaining}` placeholder to `bot/locales/en.json` and `bot/locales/es.json`

## Phase 3: Ban/Kick Confirmation (PR 1)

- [x] 3.1 RED: update `tests/test_sentinel_cog.py` — `/kick` shows ephemeral confirm before executing; cancel/timeout does not kick
- [x] 3.2 GREEN: modify `bot/cogs/sentinel.py` kick handler to send `ConfirmCancelView` before `guild.ban()`
- [x] 3.3 RED: update `tests/test_sentinel_cog.py` — `/ban` shows ephemeral confirm with `delete_days`; cancel/timeout does not ban
- [x] 3.4 GREEN: modify `bot/cogs/sentinel.py` ban handler to send `ConfirmCancelView` before `guild.ban()`
- [x] 3.5 Add confirmation/cancel/timeout locale keys to `bot/locales/en.json` and `bot/locales/es.json`

## Phase 4: Ticket View i18n (PR 1)

- [x] 4.1 RED: add `tests/test_tickets_i18n.py` — `TicketPanelView` button label resolves via `t()` at callback time using `interaction.guild_id`
- [x] 4.2 GREEN: modify `bot/views/tickets.py` — in each button callback, call `t(guild_id, key)`, set `button.label`, then `interaction.response.edit_message(view=self)`
- [x] 4.3 RED: add test — `TicketActionsView` claim/close labels resolve dynamically at interaction time
- [x] 4.4 GREEN: update `TicketActionsView` callbacks with same dynamic label pattern

## Phase 5: Greeting Config Commands (PR 2)

- [ ] 5.1 RED: update `tests/test_greetings_cog.py` — `/welcome config` returns embed with channel, toggle, message; `/welcome channel #x` saves; `/welcome toggle` flips; `/welcome message template` saves
- [ ] 5.2 GREEN: modify `bot/cogs/greetings.py` — add `@commands.hybrid_group(fallback="config")` for `/welcome` with `config`, `channel`, `toggle`, `message` subcommands using `GreetingService`
- [ ] 5.3 RED: update `tests/test_greetings_cog.py` — `/goodbye` group mirrors `/welcome` with same subcommands
- [ ] 5.4 GREEN: modify `bot/cogs/greetings.py` — add `/goodbye` hybrid group with same pattern
- [ ] 5.5 Add greeting config locale keys to `bot/locales/en.json` and `bot/locales/es.json`
- [ ] 5.6 REFACTOR: extract shared admin guard and config embed builder if duplication exists

## Phase 6: Final Verification

- [x] 6.1 Run `uv run pytest` — all 994 tests pass, no regressions
- [x] 6.2 Run `uv run pytest --cov=bot --cov-report=term` — coverage 84.34% >= 70%
- [x] 6.3 Verify `python -m py_compile bot/__main__.py` compiles clean
