"""Setup modules registry — SetupModule protocol + MODULES dict."""

from __future__ import annotations

from typing import Protocol

import discord

# pylint: disable=too-few-public-methods


class SetupModule(Protocol):
    """Protocol for setup panel modules."""

    key: str
    permission_key: str | None

    def render(self, guild_id: str) -> discord.Embed:
        """Return embed for guild_id (cache-first re-read inside)."""
        ...

    def components(self, guild_id: str) -> list[discord.ui.Item]:
        """Return interactive components for this module."""
        ...

    async def handle(self, interaction: discord.Interaction, action: str) -> None:
        """Handle a module action."""
        ...


MODULES: dict[str, SetupModule] = {}
