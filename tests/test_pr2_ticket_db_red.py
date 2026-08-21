"""RED for PR2 2.6 get_scheduled_close_candidates explicit cols batch 50."""

import inspect

from bot.core.db.ticket_db import TicketDBMixin


def test_has_get_scheduled_close_candidates():
    assert hasattr(TicketDBMixin, "get_scheduled_close_candidates")
    sig = inspect.signature(TicketDBMixin.get_scheduled_close_candidates)
    # guild_id required, batch 50 default
    assert "guild_id" in sig.parameters


def test_source_no_select_star():
    import pathlib

    src = pathlib.Path("bot/core/db/ticket_db.py").read_text()
    # method must exist and must not use select("*") — explicit cols
    assert "get_scheduled_close_candidates" in src
    # The method's select should be explicit cols, not "*"
    # Heuristic: no select("*") in the method body
    # We check that the file no longer has select("*") inside get_scheduled_close_candidates
    # Simplest: file still has select("*") elsewhere (legacy), but new method must not.
    # So find the method segment.
    # Exclude docstring line: check only code after the closing triple-quote
    seg = src[src.index("get_scheduled_close_candidates") : src.index("get_scheduled_close_candidates") + 1800]
    # Find code after docstring (after second triple quote)
    code_start = seg.find("if self._client is None")
    code_seg = seg[code_start:] if code_start != -1 else seg
    assert 'select("*")' not in code_seg and "select('*')" not in code_seg
    assert "scheduledCloseAt" in seg
    assert ".lte(" in seg or ".lt(" in seg or "lte" in seg.lower()
    assert "limit(50" in seg or "batch" in seg.lower() or ".limit(" in seg
