"""Structural guard — RankRenderer wiring (GGA C Round 4 blocker 3).

The rank renderer-selection policy was duplicated in the cog: ``stellar.rank``
lazily imported ``RankRenderer`` each call, probed ``getattr(self.bot,
"rank_renderer", None)``, and carried an unreachable legacy-shim fallback
branch.  Meanwhile ``bot.py`` created a throwaway ``_rank_renderer = RankRenderer()``
local (``# noqa: F841``) that was never stored, so the cog always built a fresh
``RankRenderer`` per ``/rank`` invocation and the fallback path was dead code.

AGENTS.md mandates "Cogs handle Discord interaction only — no business logic"
and the bot owns service/renderer lifecycle in ``setup_hook``.  The renderer
must be stored on the bot instance (respecting ``__slots__``) and the cog must
use ``self.bot.rank_renderer`` directly with no lazy-import or fallback.

This guard proves the wiring is fixed:
    - ``bot.py`` defines ``rank_renderer`` in ``__slots__``.
    - ``bot.py`` assigns ``self.rank_renderer`` in ``setup_hook``.
    - ``bot.py`` has no throwaway ``_rank_renderer =`` local.
    - ``stellar.py`` ``rank()`` uses ``self.bot.rank_renderer`` directly.
    - ``stellar.py`` has no lazy ``from bot.services.rank_renderer import``
      inside ``rank()`` and no legacy fallback branch.
"""

from __future__ import annotations

from pathlib import Path

_BOT_PATH = Path(__file__).resolve().parent.parent / "bot" / "bot.py"
_COG_PATH = Path(__file__).resolve().parent.parent / "bot" / "cogs" / "stellar.py"


def _bot_source() -> str:
    if not _BOT_PATH.exists():
        return ""
    return _BOT_PATH.read_text(encoding="utf-8")


def _cog_source() -> str:
    if not _COG_PATH.exists():
        return ""
    return _COG_PATH.read_text(encoding="utf-8")


class TestRankRendererWiring:
    """RankRenderer must be owned by the bot, not built per-call in the cog."""

    def test_bot_defines_rank_renderer_slot(self) -> None:
        src = _bot_source()
        assert src, "bot/bot.py not found"
        assert '"rank_renderer"' in src, (
            "bot/bot.py __slots__ must include 'rank_renderer' so the "
            "renderer can be stored as a real instance attribute."
        )

    def test_bot_assigns_self_rank_renderer_in_setup_hook(self) -> None:
        src = _bot_source()
        assert src, "bot/bot.py not found"
        assert "self.rank_renderer" in src, (
            "bot/bot.py must assign self.rank_renderer in setup_hook so the "
            "cog can reach it via self.bot.rank_renderer."
        )

    def test_bot_has_no_throwaway_rank_renderer_local(self) -> None:
        src = _bot_source()
        assert src, "bot/bot.py not found"
        assert "_rank_renderer =" not in src, (
            "bot/bot.py must not keep the throwaway '_rank_renderer = RankRenderer()' "
            "local — store it on self.rank_renderer instead."
        )

    def test_cog_uses_bot_rank_renderer_directly(self) -> None:
        src = _cog_source()
        assert src, "bot/cogs/stellar.py not found"
        assert "self.bot.rank_renderer" in src, (
            "bot/cogs/stellar.py rank() must use self.bot.rank_renderer "
            "directly instead of lazily importing RankRenderer each call."
        )

    def test_cog_has_no_lazy_rank_renderer_import(self) -> None:
        src = _cog_source()
        assert src, "bot/cogs/stellar.py not found"
        assert "from bot.services.rank_renderer import RankRenderer" not in src, (
            "bot/cogs/stellar.py must not lazily import RankRenderer inside rank() — the renderer is owned by the bot."
        )

    def test_cog_has_no_legacy_fallback_branch(self) -> None:
        src = _cog_source()
        assert src, "bot/cogs/stellar.py not found"
        # The deleted legacy shim's fallback branch keyed on a generate_rank_card
        # delegation inside rank(); guard against any fallback wording returning.
        assert "falling back" not in src, (
            "bot/cogs/stellar.py must not carry a legacy rank-card fallback "
            "branch — RankRenderer owns generation and the bot owns the "
            "renderer instance."
        )
