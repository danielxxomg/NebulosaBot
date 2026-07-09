# Design: bot-ux

## Technical Approach

Ship `bot-ux` as two reviewable PRs. PR1 fixes the highest-risk user-facing gaps without schema changes: persistent ticket button labels localize at interaction time, `/daily` reports exact cooldown, and `/kick`/`/ban` require confirmation. PR2 adds greeting configuration command groups on top of the existing `GreetingService` cache-first API.

No migration required. `bot/bot.py` should keep registering `TicketPanelView()` and `TicketActionsView()` in `setup_hook()` without guild context; callbacks will resolve guild language dynamically.

## Architecture Decisions

| Decision | Option | Tradeoff | Choice |
|---|---|---|---|
| Persistent labels | Register one view per guild at startup | Heavy, brittle across guild changes | Keep global persistent views; update button labels in callbacks via `t(guild_id, key)` before responding/editing |
| Daily return contract | Dataclass result | Cleaner, but larger refactor/tests | Extend tuple to `(success, coins, streak, remaining_seconds)` and update all callers/mocks |
| Destructive action safety | Inline duplicate confirmation code | Fast but duplicates timeout/cancel logic | New reusable `ConfirmCancelView` with owner-only buttons, timeout disable, and async `on_confirm` callback |
| Greeting commands | Direct DB calls in cog | Violates service boundary | Use `GreetingService.get_config()`/`save_config()` and mutate `GreetingConfig` dataclass |
| Delivery | One large PR | Review budget risk | PR1: tickets/daily/sentinel. PR2: greetings commands/locales/tests |

## Data Flow

PR1 — persistent ticket labels:

    setup_hook add_view(no guild) -> button click -> interaction.guild_id
      -> t(guild_id, label_key) -> mutate Button.label -> edit/respond with same view

PR1 — moderation confirmation:

    /kick or /ban -> validate target -> ephemeral ConfirmCancelView
      -> Confirm by original moderator -> execute existing action/log/infraction
      -> Cancel/timeout -> disable buttons + localized status

PR2 — greeting config:

    /welcome channel|toggle|message -> GreetingService.get_config()
      -> mutate GreetingConfig -> save_config() -> DB upsert + cache invalidation

## File Changes

| File | PR | Action | Description |
|---|---:|---|---|
| `bot/bot.py` | PR1 | Verify | Keep `setup_hook()` persistent view registration without guild context. |
| `bot/views/tickets.py` | PR1 | Modify | Add helper to localize `ticket:open`, `ticket:claim`, `ticket:close` labels from `interaction.guild_id` inside callbacks. |
| `bot/services/economy_service.py` | PR1 | Modify | Return remaining cooldown seconds from `claim_daily()`; success path returns `0`. |
| `bot/cogs/stellar.py` | PR1 | Modify | Unpack `remaining_seconds`; format `Xh Ym` and pass `{remaining}` to cooldown i18n. |
| `bot/views/confirmation.py` | PR1 | Create | Reusable ephemeral `ConfirmCancelView`. |
| `bot/cogs/sentinel.py` | PR1 | Modify | Wrap `/kick` and `/ban` execution behind confirm dialog; extract execution helpers if needed. |
| `bot/cogs/greetings.py` | PR2 | Modify | Add `/welcome` and `/goodbye` hybrid groups with `config`, `channel`, `toggle`, `message`. |
| `bot/locales/en.json`, `bot/locales/es.json` | PR1/PR2 | Modify | Add confirmation, cooldown `{remaining}`, and greeting config strings. |
| `tests/test_*` | PR1/PR2 | Modify/Create | Update affected unit/i18n tests; add confirmation view tests. |

## Interfaces / Contracts

```python
async def claim_daily(guild_id: str, user_id: str) -> tuple[bool, int, int, int]: ...

class ConfirmCancelView(discord.ui.View):
    def __init__(self, *, guild_id: str, owner_id: int,
                 on_confirm: Callable[[discord.Interaction], Awaitable[None]],
                 timeout: float = 30) -> None: ...
```

Greeting groups use `@commands.hybrid_group(..., fallback="config")`, `@app_commands.default_permissions(administrator=True)`, and an explicit runtime admin guard matching existing `welcome_test`/`goodbye_test` behavior.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | label helper, cooldown math/formatting, confirm/cancel/timeout, greeting config mutation | pytest + pytest-asyncio with Discord mocks |
| Integration | command callbacks call services/Discord actions only after confirm | existing cog tests with `AsyncMock` |
| E2E | Not applicable | Discord API is mocked per project rules |

Strict TDD applies: add failing tests before implementation and run `uv run pytest`.

## Migration / Rollout

No database migration. PR1 and PR2 are independently revertable.

## Open Questions

- [ ] Non-blocking: keep 30-second confirmation timeout unless user requests a different value.
