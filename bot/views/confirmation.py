"""Reusable ephemeral Confirm/Cancel view for destructive moderator actions.

Provides a ``ConfirmCancelView`` that displays Confirm and Cancel buttons
with owner-only enforcement and automatic timeout disabling.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import discord

from bot.core.i18n import t
from bot.utils.brand import ERROR, INFO

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ConfirmCancelView(discord.ui.View):
    """Ephemeral view with Confirm and Cancel buttons for destructive actions.

    Only the user who invoked the command (``owner_id``) can interact.
    After confirm, cancel, or timeout, both buttons are disabled.

    Args:
        guild_id: Discord guild ID for i18n resolution.
        owner_id: The user ID of the command invoker.
        on_confirm: Async callback executed on Confirm. Receives the
            :class:`discord.Interaction` as its sole argument.
        timeout: Seconds before the view times out (default: 30).
    """

    __slots__ = ("_guild_id", "_on_confirm", "_owner_id", "message")

    def __init__(
        self,
        *,
        guild_id: str,
        owner_id: int,
        on_confirm: Callable[[discord.Interaction], Awaitable[None]],
        timeout: float = 30,
    ) -> None:
        super().__init__(timeout=timeout)
        self._guild_id = guild_id
        self._owner_id = owner_id
        self._on_confirm = on_confirm
        self.message: discord.Message | None = None

        # Override decorator defaults with localized labels.
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "confirm:confirm":
                    child.label = t(guild_id, "buttons.confirm")
                elif child.custom_id == "confirm:cancel":
                    child.label = t(guild_id, "buttons.cancel")

    def _disable_all(self) -> None:
        """Disable all button children."""
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

    async def _check_owner(self, interaction: discord.Interaction) -> bool:
        """Return ``True`` if the interaction user is the owner.

        Sends an ephemeral rejection message and returns ``False`` otherwise.
        """
        if interaction.user.id == self._owner_id:
            return True
        await interaction.response.send_message(
            embed=discord.Embed(
                title=t(self._guild_id, "confirm.not_owner_title"),
                description=t(self._guild_id, "confirm.not_owner_description"),
                color=ERROR,
            ),
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="Confirmar",
        style=discord.ButtonStyle.danger,
        custom_id="confirm:confirm",
        emoji="✅",
    )
    async def confirm_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[discord.ui.View],
    ) -> None:
        """Execute the confirm callback and disable buttons."""
        if not await self._check_owner(interaction):
            return
        self._disable_all()
        await self._on_confirm(interaction)

    @discord.ui.button(
        label="Cancelar",
        style=discord.ButtonStyle.secondary,
        custom_id="confirm:cancel",
        emoji="❌",
    )
    async def cancel_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[discord.ui.View],
    ) -> None:
        """Disable buttons and send a cancellation message."""
        if not await self._check_owner(interaction):
            return
        self._disable_all()
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=t(self._guild_id, "confirm.cancelled_title"),
                description=t(self._guild_id, "confirm.cancelled_description"),
                color=INFO,
            ),
            view=self,
        )

    async def on_timeout(self) -> None:
        """Disable all buttons and edit the message with a timeout notice."""
        self._disable_all()
        message = self.message or getattr(self, "_message", None)
        if message is not None:
            try:
                await message.edit(
                    embed=discord.Embed(
                        title=t(self._guild_id, "confirm.timeout_title"),
                        description=t(
                            self._guild_id,
                            "confirm.timeout_description",
                        ),
                        color=INFO,
                    ),
                    view=self,
                )
            except discord.HTTPException:
                logger.debug(
                    "Failed to edit message on timeout (may be deleted).",
                )
