# Exploration: welcome-card-disabled-cta-guard

## Current State

The archived change `welcome-localization-ux` introduced localized greeting cards and an onboarding CTA system. The CTA is appended to welcome messages via `_compose_welcome_content()`, which always calls `_resolve_welcome_cta()` regardless of the card-toggle state.

The canonical spec (`openspec/specs/greeting-config/spec.md`, lines 129-149) explicitly requires:

> `dispatch_welcome()` MUST check `config.welcome_card_enabled` before generating a greeting card. When `welcome_card_enabled` is `True`, the existing card-generation path is used. When `False`, only a text-only message is sent if `welcome_message` is non-empty; **if `welcome_message` is also empty, nothing is sent.**

The CTA-only behavior was designed and tested exclusively for the **card-enabled path with an empty template** (test at `test_greeting_service.py:427-445`). It was never intended for the card-disabled path.

## Bug: Exact Cause

**Call chain** (`bot/services/greeting_service.py`):

```
dispatch_welcome() [line 120-127]
  → _send_text_only_if_message(channel, config.welcome_message or "", member, onboarding_channel_id=...)  [line 268]
    → _compose_welcome_content(member, message_template="", onboarding_channel_id=...)  [line 268]
      → _format_template("", member) → ""  [line 279]
      → _resolve_welcome_cta(member, channel_id) → "Start here: <#999>"  [line 280-282]
      → returns "Start here: <#999>"  (CTA-only)  [line 282]
    → if content:  → sends CTA-only message  [line 269-270]
```

**Root cause**: `_send_text_only_if_message()` delegates to `_compose_welcome_content()`, which **unconditionally resolves and appends the CTA**. The function name and docstring say "send text only if message", but the implementation sends CTA-only content even when the message template is empty.

The CTA resolution is appropriate in the card-enabled path (line 148) where it was explicitly designed, but it leaks into the card-disabled text-only path where the spec mandates silence.

## Affected Areas

- `bot/services/greeting_service.py` — `_send_text_only_if_message()` (line 256-270): calls `_compose_welcome_content` which always resolves CTA; `_compose_welcome_content()` (line 273-283): unconditional CTA resolution
- `tests/test_greeting_service.py` — missing RED test for `card_disabled + empty message + resolvable onboarding_channel_id`

## Approaches

### Approach A: Guard CTA resolution in `_send_text_only_if_message` (Recommended)

Change `_send_text_only_if_message` to NOT use `_compose_welcome_content`. Instead, format the template directly and send only if non-empty, without CTA resolution.

```python
async def _send_text_only_if_message(
    channel: discord.abc.Messageable,
    message_template: str,
    member: discord.Member,
    *,
    onboarding_channel_id: str | None = None,  # kept for signature compat, unused
) -> None:
    content = _format_template(message_template, member) if message_template else ""
    if content:
        await channel.send(content=content)
```

- **Pros**: Minimal change; isolates CTA to the card path; function name matches behavior; no signature change for callers
- **Cons**: `onboarding_channel_id` parameter becomes unused in this function (but kept for call-site compatibility)
- **Effort**: Low

### Approach B: Add `include_cta` parameter to `_compose_welcome_content`

Add a `include_cta: bool = True` parameter. `_send_text_only_if_message` passes `include_cta=False`.

- **Pros**: Explicit control; function signature documents intent
- **Cons**: Adds parameter to shared helper; callers must remember to pass it; more surface area
- **Effort**: Low

### Approach C: Separate `_compose_text_only_content` helper

Create a new helper that formats template without CTA, used exclusively by `_send_text_only_if_message`.

- **Pros**: Clear separation; no risk of CTA leaking
- **Cons**: More code; duplication of template formatting logic
- **Effort**: Low-Medium

## Recommendation

**Approach A**. It's the simplest fix with the clearest semantics: `_send_text_only_if_message` should send text only if there's a message — the function name is the spec. The CTA belongs to the card-enabled path where it was designed and tested. The unused `onboarding_channel_id` parameter is a minor cosmetic debt that doesn't affect behavior.

## Scenarios

### RED (must fail before fix)

**Scenario: Card disabled with empty message and resolvable onboarding channel sends nothing**

- GIVEN `welcome_enabled=True`, `welcome_channel_id` set, `welcome_card_enabled=False`, `welcome_message=None`, and `onboarding_channel_id` points to a resolvable channel
- WHEN a member joins
- THEN no message is sent to the welcome channel

### GREEN (must pass after fix)

Same scenario as RED — must now pass (nothing sent).

**Existing tests that must remain green:**
- `test_card_disabled_with_message_sends_text_only` (line 499) — text-only path with message still works
- `test_card_disabled_without_message_sends_nothing` (line 522) — works today because no onboarding channel in fixture
- `test_empty_welcome_message_with_resolvable_onboarding_channel_is_cta_only` (line 427) — card-enabled CTA-only path preserved
- `test_resolvable_onboarding_channel_appends_localized_cta` (line 376) — card + message + CTA preserved
- All goodbye tests — unaffected (no CTA in goodbye path)

## Files Affected

- `bot/services/greeting_service.py` — `_send_text_only_if_message()` (line 256-270): primary fix location
- `tests/test_greeting_service.py` — add RED test for the bug scenario; verify all existing tests remain green

## No-goles

- Do NOT change `_compose_welcome_content()` — it works correctly for the card path
- Do NOT change `_resolve_welcome_cta()` — CTA resolution logic is sound
- Do NOT change `dispatch_welcome()` card-enabled path — CTA there is by design
- Do NOT modify the canonical spec (`openspec/specs/greeting-config/spec.md`) — it already has the correct contract
- Do NOT modify the archived change — it's history

## Compatibility with Existing CTA

The fix is fully backwards-compatible with the CTA system:

| Path | CTA behavior | After fix |
|------|-------------|-----------|
| Card enabled + empty message + onboarding | CTA-only sent | **Unchanged** |
| Card enabled + message + onboarding | Message + CTA sent | **Unchanged** |
| Card enabled + no onboarding | Message only (or card only) | **Unchanged** |
| Card disabled + message + onboarding | Message sent (CTA leaks) | Message only (no CTA) — **fixed** |
| Card disabled + empty message + onboarding | CTA-only sent (BUG) | Nothing sent — **fixed** |
| Card disabled + message + no onboarding | Message only | **Unchanged** |

## Risks of Not Fixing

- **Spec violation**: The archived spec explicitly requires "nothing is sent" when card disabled + empty message. Current behavior violates this.
- **User confusion**: Guilds that disabled the card and cleared the message still get a CTA-only message on every join — unexpected and spammy.
- **Regression surface**: Future changes that assume the card-disabled path is silent will build on a broken foundation.

## Ready for Proposal

**Yes.** The bug is clearly located (`_send_text_only_if_message` → `_compose_welcome_content` → unconditional CTA), the fix is minimal (Approach A, ~3 lines changed), the RED/GREEN scenarios are defined, and the existing test suite provides a safety net. The orchestrator should proceed to `sdd-propose` for `welcome-card-disabled-cta-guard`.
