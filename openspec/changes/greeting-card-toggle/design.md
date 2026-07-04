# Design: Greeting Card Toggle

## Technical Approach

Add one conditional branch in each dispatch method after the existing channel-not-found guard and before avatar/card generation. The preserved order is: top-level enabled guard, channel-id guard, channel-not-found guard, then card-enabled check. When the card toggle is disabled, format the existing message template and send text-only if non-empty; if the message is empty or null, return without sending. When enabled, keep the current `asyncio.to_thread(self._image_service.generate_greeting_card, ...)` path unchanged.

Exact insertion points:
- `GreetingService.dispatch_welcome()`: after `channel is None` guard returns at `bot/services/greeting_service.py:110-116`, before current `avatar_url = _resolve_avatar_url(member)` at line 118.
- `GreetingService.dispatch_goodbye()`: after `channel is None` guard returns at `bot/services/greeting_service.py:153-159`, before current `avatar_url = _resolve_avatar_url(member)` at line 161.

## Architecture Decisions

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Branch inside `GreetingService` | Keeps cogs thin and uses already cache-resolved `GreetingConfig`; duplicates a tiny welcome/goodbye pattern | Chosen: cogs stay event-only and service owns dispatch behavior |
| Change `ImageService` or add a card strategy | More abstraction for a two-conditional bug fix | Rejected: no image behavior changes are required |
| Add schema/dashboard changes | Broader surface area, unnecessary risk | Rejected: model fields, DB columns, and dashboard toggles already exist |

## Data Flow

```text
member event -> GreetingsCog -> GreetingService.get_config(guild_id)
    -> cache-first GreetingConfig
    -> welcome_card_enabled / goodbye_card_enabled
    -> false: text-only send or no-op
    -> true: existing generate_greeting_card via asyncio.to_thread + file send
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `bot/services/greeting_service.py` | Modify | Add card toggle branches only in `dispatch_welcome()` and `dispatch_goodbye()` |
| `tests/test_greeting_service.py` | Modify | Add red tests first for toggle dispatch behavior |

No schema, dashboard, `ImageService`, or cog changes.

## Interfaces / Contracts

No new public API. Existing config fields are consumed:

```python
config.welcome_card_enabled: bool
config.goodbye_card_enabled: bool
```

Text-only sends must call `await channel.send(content=content)` with no `file` argument. Empty text with card disabled must not call `channel.send()`.

## Testing Strategy

Strict TDD: add each test in `tests/test_greeting_service.py`, run it red, implement the smallest green change, then refactor.

| Test | Spec scenario |
|------|---------------|
| `TestDispatchWelcome::test_card_enabled_sends_welcome_card` | Welcome card sent when toggle enabled |
| `TestDispatchWelcome::test_card_disabled_with_message_sends_text_only` | Welcome text-only when toggle disabled and message set |
| `TestDispatchWelcome::test_card_disabled_without_message_sends_nothing` | Welcome nothing when toggle disabled and no message |
| `TestDispatchGoodbye::test_card_enabled_sends_goodbye_card` | Goodbye card sent when toggle enabled |
| `TestDispatchGoodbye::test_card_disabled_with_message_sends_text_only` | Goodbye text-only when toggle disabled and message set |
| `TestDispatchGoodbye::test_card_disabled_without_message_sends_nothing` | Goodbye nothing when toggle disabled and no message |
| `TestDispatchWelcome::test_disabled_skips_before_card_toggle` or goodbye equivalent | Top-level greeting guard still applies |

Assertions should verify `mock_image_service.generate_greeting_card` call/no-call and `member.guild.get_channel.return_value.send` content/file behavior.

## Migration / Rollout

No migration required. Defaults are already `True`, so existing card behavior is preserved until a guild disables a card toggle.

Rollback is low risk: revert the two conditional blocks in `bot/services/greeting_service.py`.

## Non-goals

- No dashboard changes.
- No DB schema or migration changes.
- No `ImageService` changes.
- No cog or command changes.
- No cache invalidation or unrelated greeting features.

## Open Questions

None.
