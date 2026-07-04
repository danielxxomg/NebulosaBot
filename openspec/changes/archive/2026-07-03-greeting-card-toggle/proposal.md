# Proposal: Greeting Card Toggle

## Intent

The dashboard exposes `welcomeCardEnabled` / `goodbyeCardEnabled` toggles (DB columns in `greeting_config`, model fields in `GreetingConfig`, UI in the dashboard greeting page). However, `GreetingService.dispatch_welcome()` and `dispatch_goodbye()` never read these fields — the card is ALWAYS generated and sent regardless of the toggle state. The dashboard toggle silently does nothing. This is a user-facing bug: admins who disable the card toggle expect text-only or no message, but still receive the full card.

## Scope

### In Scope
- Wire `config.welcome_card_enabled` check into `dispatch_welcome()` (`bot/services/greeting_service.py:105-132`)
- Wire `config.goodbye_card_enabled` check into `dispatch_goodbye()` (`bot/services/greeting_service.py:148-175`)
- Behavior when card disabled: send text-only message (if `welcome_message`/`goodbye_message` is set); send nothing if message is also empty
- Behavior when card enabled: unchanged (generate card + optional text overlay)
- Tests: 3 scenarios per dispatch method (card=true sends card, card=false sends text only, card=false+empty sends nothing)

### Out of Scope
- Dashboard UI changes (toggles already exist and work)
- Database schema / migration changes (columns already exist)
- ImageService changes
- Any other greeting features
- Cache invalidation logic (unrelated)

## Capabilities

### New Capabilities
None

### Modified Capabilities
- `greeting-config`: `dispatch_welcome()` and `dispatch_goodbye()` now respect `welcome_card_enabled` / `goodbye_card_enabled` flags

## Approach

Minimal conditional branching in `GreetingService`:

```python
# dispatch_welcome (same pattern for dispatch_goodbye)
if config.welcome_card_enabled:
    # existing card generation path (lines 119-132)
    buffer = await asyncio.to_thread(...)
    file = discord.File(buffer, filename="welcome.png")
    await channel.send(content=content or None, file=file)
else:
    # text-only path
    if content:
        await channel.send(content=content)
    # else: no message configured + no card → send nothing
```

No new dependencies. Respects AGENTS.md: `asyncio.to_thread` for Pillow (already used), cache-first config (already used), `logging` not `print`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/services/greeting_service.py:105-132` | Modified | Add `welcome_card_enabled` branch in `dispatch_welcome()` |
| `bot/services/greeting_service.py:148-175` | Modified | Add `goodbye_card_enabled` branch in `dispatch_goodbye()` |
| `tests/test_greeting_service.py` | Modified | Add 6 tests covering card toggle scenarios |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Existing guilds with `welcomeCardEnabled` default `True` — no behavior change for them | N/A | Default is `True` in model (line 23), safe |
| Edge case: card disabled + no message → silent skip. User might expect *something* | Low | This is correct behavior — if admin disabled card AND has no text message, nothing to send |
| Channel-not-found guard (line 110-116) still applies before card check | N/A | Order unchanged: config → channel exists → card toggle → generate/send |

## Rollback Plan

Revert the two conditional blocks in `bot/services/greeting_service.py`. The card toggle fields remain in the model/DB untouched — they're simply ignored again. No schema changes.

## Dependencies

None. All infrastructure (model fields, DB columns, dashboard toggles) already exists.

## Success Criteria

- [ ] `welcome_card_enabled=False` + message set → text-only message sent (no card file)
- [ ] `welcome_card_enabled=False` + no message → nothing sent
- [ ] `welcome_card_enabled=True` → card + optional text sent (unchanged behavior)
- [ ] Same 3 scenarios pass for `goodbye_card_enabled`
- [ ] All existing tests still pass: `uv run pytest`
- [ ] New tests: 6 additional test cases covering toggle scenarios
