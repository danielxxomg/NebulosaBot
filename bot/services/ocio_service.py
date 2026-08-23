"""OcioService — pool banana + 8ball (services layer, no Discord imports).

Pillow fallback runs via asyncio.to_thread (G0.1 strict TDD, services layer).
"""

from __future__ import annotations

import asyncio
import logging
import random
from pathlib import Path

from bot.core.i18n import t

logger = logging.getLogger(__name__)

_BANANA_PLACEHOLDER_SIZE = (256, 256)
_DORADA_CM = 30
_EMPTY_FILE_MSG = "empty file"


def _pillow_banana_placeholder() -> bytes:
    """Render a Pillow placeholder banana image → PNG bytes."""
    from io import BytesIO

    from PIL import Image, ImageDraw

    img = Image.new("RGB", _BANANA_PLACEHOLDER_SIZE, color=(255, 225, 100))
    draw = ImageDraw.Draw(img)
    draw.ellipse((40, 80, 216, 176), fill=(255, 215, 0), outline=(200, 150, 0), width=3)
    draw.arc((50, 90, 206, 166), start=20, end=160, fill=(180, 130, 0), width=2)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# 20 8ball keys — uniform random pick, localized via t()
_8BALL_KEYS: list[str] = [f"ocio.8ball.r{i}" for i in range(1, 21)]


class OcioService:
    """Service owning non-Discord ocio logic (pool + 8ball)."""

    def __init__(self, banana_dir: Path | None = None) -> None:
        self._banana_dir = Path(banana_dir) if banana_dir is not None else Path("assets/images/banana")

    async def get_random_banana(self) -> tuple[bytes, str, int]:
        """Return (bytes, filename, cm) for a random banana.

        1% path → dorada.webp + 30cm.  99% path → random pool pick.
        Empty / missing / corrupt → Pillow placeholder via asyncio.to_thread.
        """
        # 1% dorada weighted pick
        if random.random() < 0.01:  # noqa: S311 — entertainment randomness
            dorada = self._banana_dir / "dorada.webp"
            try:

                def _read_dorada() -> bytes:
                    return dorada.read_bytes()

                data = await asyncio.to_thread(_read_dorada)
                if data:
                    return data, "dorada.webp", _DORADA_CM
            except Exception:
                logger.debug("dorada read failed — falling back to placeholder", exc_info=True)
            # fallback: placeholder but still dorada name + 30cm
            data = await asyncio.to_thread(_pillow_banana_placeholder)
            return data, "dorada.webp", _DORADA_CM

        # 99% pool path — glob is blocking filesystem I/O: run it off the
        # event loop via asyncio.to_thread (sibling read_bytes calls already do).
        # sorted() gives a deterministic order so random.choice is stable across calls.
        try:
            pool = await asyncio.to_thread(lambda: sorted(self._banana_dir.glob("*.webp")))
        except Exception:
            pool = []
        if not pool:
            data = await asyncio.to_thread(_pillow_banana_placeholder)
            cm = random.randint(2, 30)  # noqa: S311
            return data, "banana.webp", cm
        # Keep uniform; dorada already handled via 1% branch.
        chosen: Path = random.choice(pool)  # noqa: S311
        try:

            def _read_chosen() -> bytes:
                return chosen.read_bytes()

            data = await asyncio.to_thread(_read_chosen)
            if not data:
                msg = _EMPTY_FILE_MSG
                raise ValueError(msg)  # noqa: TRY301
        except Exception:
            logger.debug("banana pool read failed for %s — placeholder", chosen, exc_info=True)
            data = await asyncio.to_thread(_pillow_banana_placeholder)
            cm = random.randint(2, 30)  # noqa: S311
            return data, chosen.name or "banana.webp", cm
        else:
            cm = random.randint(2, 30)  # noqa: S311
            return data, chosen.name, cm

    def get_8ball_response(self, guild_id: str | None = None, question: str | None = None) -> str:  # noqa: ARG002
        """Return one of 20 localized 8ball responses (uniform random)."""
        key = random.choice(_8BALL_KEYS)  # noqa: S311
        return t(guild_id, key)

    def get_eight_ball_response(self, guild_id: str | None = None, question: str | None = None) -> str:
        """Alias for RED alternative name."""
        return self.get_8ball_response(guild_id=guild_id, question=question)
