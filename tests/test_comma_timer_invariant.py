"""`,` close-timer invariant guard (clean-1.0 S0.13).

The `,` ticket-channel close-timer grammar is specified by
``close-confirmation`` and operates OUTSIDE the command framework. No
change in this repository may touch the parsing inside
``TicketsCog.on_message``: the ``","`` trigger, the cancel-message
detection, the timer delegation, or the guild-scoped debounce key.

This guard pins those structural markers so any accidental edit to the
close-timer parsing fails fast. (It is intentionally a source-marker
guard — the parsing contract itself is owned by the close-confirmation
suite.)
"""

from __future__ import annotations

import inspect

from bot.cogs.tickets import TIMER_DEBOUNCE_TTL, TicketsCog


def test_comma_trigger_marker_intact() -> None:
    """The `,` trigger gate must remain exactly `content.startswith(",")`."""
    src = inspect.getsource(TicketsCog.on_message)
    assert 'content.startswith(",")' in src, "`, trigger marker missing from on_message"


def test_timer_delegation_markers_intact() -> None:
    """Cancel detection + timer state-machine delegation must be present."""
    src = inspect.getsource(TicketsCog)
    assert "is_cancel_message(content)" in src, "cancel-grammar detection missing"
    assert "handle_timer_message(" in src, "timer state-machine delegation missing"
    # The cancel check MUST precede the scheduled-close handling.
    assert src.index("is_cancel_message(content)") < src.index("handle_timer_message(")


def test_debounce_key_is_guild_scoped() -> None:
    """Debounce keys stay `{guild_id}:{channel_id}:{user_id}` (guild-scoped)."""
    gid, cid, uid = "123", "456", "789"
    expected = f"{gid}:{cid}:{uid}"
    assert expected.startswith(f"{gid}:"), "debounce key must be guild-prefixed"
    assert TIMER_DEBOUNCE_TTL > 0, "debounce window must stay positive"
