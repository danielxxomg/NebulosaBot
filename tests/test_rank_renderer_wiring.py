"""Behavioral guard — RankRenderer ownership (GGA C Round 4 blocker 3).

The rank renderer-selection policy used to be duplicated in the cog:
``stellar.rank`` lazily imported ``RankRenderer`` per call and carried a
dead legacy fallback, while ``bot.py`` built a throwaway local that was
never stored.

Consolidation note (cycle-5 S5b/c): the six source-grep assertions were
replaced by behavioral twins —

- bot ownership is proven by the ``__slots__`` introspection below;
- cog-side usage (``/rank`` renders through the bot-owned
  ``self.bot.rank_renderer`` with no per-call construction) is proven by
  the spec'd ``RankRenderer`` mock wiring in ``tests/test_stellar_cog.py``
  and ``tests/test_stellar_i18n.py``, whose rank tests fail if the cog
  stops using the injected renderer.
"""

from __future__ import annotations

from bot.bot import NebulosaBot


class TestRankRendererWiring:
    """RankRenderer must be owned by the bot, not built per-call in the cog."""

    def test_bot_slot_declares_rank_renderer(self) -> None:
        """NebulosaBot.__slots__ includes 'rank_renderer' so setup_hook can store it."""
        slots = getattr(NebulosaBot, "__slots__", ())
        assert "rank_renderer" in slots, (
            "NebulosaBot.__slots__ must include 'rank_renderer' so the "
            "renderer is stored as a real instance attribute owned by the bot."
        )
