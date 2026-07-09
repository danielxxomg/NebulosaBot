"""EmbedPaginator — reusable paginated embed view for discord.py.

Replaces the duplicated ``_HelpPaginator`` (core.py) and
``_ModlogsPaginator`` (sentinel.py) with a single, configurable
``discord.ui.View`` that provides prev/next/stop buttons.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class EmbedPaginator(discord.ui.View):
    """Paginated embed view with Previous, Next, and Stop buttons.

    Args:
        pages: List of :class:`discord.Embed` pages to paginate through.
        timeout: Seconds of inactivity before :meth:`on_timeout` fires.
            Defaults to 120.
        custom_id_prefix: Prefix for stable ``custom_id`` values on each
            button, enabling persistent view registration.  Defaults to
            ``"paginator:"``.
    """

    __slots__ = ("_message", "_pages", "current_page")

    def __init__(
        self,
        pages: list[discord.Embed],
        *,
        timeout: float = 120.0,
        custom_id_prefix: str = "paginator:",
    ) -> None:
        super().__init__(timeout=timeout)
        self._pages = pages
        self.current_page = 0
        self._message: discord.Message | None = None

        # Build stable custom_ids for persistent view support.
        self._custom_id_prefix = custom_id_prefix

        # Set custom_ids on the buttons after init.
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id is None or child.custom_id == "paginator:prev":
                    child.custom_id = f"{custom_id_prefix}prev"
                elif child.custom_id == "paginator:next":
                    child.custom_id = f"{custom_id_prefix}next"
                elif child.custom_id == "paginator:stop":
                    child.custom_id = f"{custom_id_prefix}stop"

        self.update_buttons()

    # -- Button definitions ---------------------------------------------

    @discord.ui.button(
        label="\u25c0 Previous",
        style=discord.ButtonStyle.secondary,
        custom_id="paginator:prev",
    )
    async def prev_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[EmbedPaginator],
    ) -> None:
        """Go to the previous page."""
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self._pages[self.current_page],
            view=self,
        )

    @discord.ui.button(
        label="Next \u25b6",
        style=discord.ButtonStyle.secondary,
        custom_id="paginator:next",
    )
    async def next_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[EmbedPaginator],
    ) -> None:
        """Go to the next page."""
        self.current_page = min(len(self._pages) - 1, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self._pages[self.current_page],
            view=self,
        )

    @discord.ui.button(
        label="\u23f9 Stop",
        style=discord.ButtonStyle.danger,
        custom_id="paginator:stop",
    )
    async def stop_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[EmbedPaginator],
    ) -> None:
        """Stop pagination and disable all buttons."""
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.response.edit_message(view=self)

    # -- Helpers --------------------------------------------------------

    def update_buttons(self) -> None:
        """Enable/disable prev and next based on current page position."""
        buttons = [c for c in self.children if isinstance(c, discord.ui.Button)]
        if len(buttons) >= 2:
            buttons[0].disabled = self.current_page == 0  # prev
            buttons[1].disabled = self.current_page == len(self._pages) - 1  # next

    async def on_timeout(self) -> None:
        """Disable all buttons when the view times out."""
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self._message is not None:
            try:
                await self._message.edit(view=self)
            except discord.HTTPException:
                logger.debug("Failed to edit message on timeout")
