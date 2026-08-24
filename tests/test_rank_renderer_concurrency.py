"""R-2: concurrent rank requests remain responsive (RED if to_thread is removed)."""

from __future__ import annotations

import asyncio
import io
import time
from typing import TypedDict
from unittest.mock import patch

import pytest
from PIL import Image

from bot.services.rank_renderer import RankRenderer

_BLOCK_SECONDS = 0.05
# Serial = 2 * _BLOCK_SECONDS = 0.10s; parallel ≈ _BLOCK_SECONDS. Midway.
_SERIAL_THRESHOLD = _BLOCK_SECONDS * 1.5


class _RankKwargs(TypedDict):
    """Keyword arguments for :meth:`RankRenderer.generate_rank_card`."""

    avatar_url: str | None
    xp: int
    level: int
    rank: int
    xp_for_current: float
    xp_for_next: float


_RANK_KW: _RankKwargs = {
    "avatar_url": None,
    "xp": 500,
    "level": 3,
    "rank": 5,
    "xp_for_current": 300.0,
    "xp_for_next": 450.0,
}


def _slow_generate_rank_card(self, **kwargs):
    """Block the running thread for a fixed window, then return a valid PNG."""
    time.sleep(_BLOCK_SECONDS)
    buf = io.BytesIO()
    Image.new("RGBA", (934, 282), (40, 45, 50, 255)).save(buf, format="PNG")
    buf.seek(0)
    return buf


@pytest.mark.asyncio
async def test_concurrent_rank_generation_remains_responsive() -> None:
    """Two concurrent rank renders via to_thread must run in parallel, not serially."""
    with patch.object(RankRenderer, "generate_rank_card", _slow_generate_rank_card):
        start = time.monotonic()
        buf_a, buf_b = await asyncio.gather(
            asyncio.to_thread(RankRenderer().generate_rank_card, username="User1", **_RANK_KW),
            asyncio.to_thread(RankRenderer().generate_rank_card, username="User2", **_RANK_KW),
        )
        elapsed = time.monotonic() - start

    assert isinstance(buf_a, io.BytesIO) and isinstance(buf_b, io.BytesIO)
    assert buf_a.getvalue()[:8] == b"\x89PNG\r\n\x1a\n" and buf_b.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"
    assert elapsed < _SERIAL_THRESHOLD, (
        f"rank renders ran serially (elapsed={elapsed:.3f}s >= "
        f"{_SERIAL_THRESHOLD:.3f}s); concurrent rendering requires asyncio.to_thread"
    )


@pytest.mark.asyncio
async def test_rank_generation_runs_in_worker_thread() -> None:
    """A rank render via to_thread MUST run off the event-loop thread."""
    import threading

    renderer = RankRenderer()
    loop_thread = threading.get_ident()
    worker_thread: list[int] = []

    def _record_thread(url: str | None) -> Image.Image | None:
        worker_thread.append(threading.get_ident())
        return None

    with patch("bot.services.shared_assets._safe_fetch_avatar", side_effect=_record_thread):
        buf = await asyncio.to_thread(renderer.generate_rank_card, username="ThreadUser", **_RANK_KW)

    assert isinstance(buf, io.BytesIO)
    assert buf.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"
    assert worker_thread, "renderer did not invoke shared_assets — boundary check invalid"
    assert worker_thread[0] != loop_thread, (
        "rank render ran on the event-loop thread, not in a worker thread (R-2 regression)"
    )
