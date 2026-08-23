"""Persistent actions seam — TicketActionsView (timeout=None, 4 IDs).

Extraction behind :class:`bot.views.tickets` facade. Keeps claim/close/edit-category
persistent callbacks and add_view() registration contract.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord

from bot.utils.brand import INFO as _INFO_BRAND
from bot.utils.brand import SUCCESS, WARNING
from bot.utils.embeds import error_embed

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)


def _get_t() -> Any:
    try:
        import bot.views.tickets as _facade
    except ImportError:
        from bot.core.i18n import t as _direct

        return _direct
    else:
        return _facade.t


def _get_is_mod_check() -> Any:
    try:
        import bot.views.tickets as _facade
    except ImportError:
        from bot.utils.checks import is_mod_check as _direct

        return _direct
    else:
        return _facade.is_mod_check


class TicketActionsView(discord.ui.View):
    """Persistent per-ticket view with Close and Claim buttons."""

    def __init__(self, guild_id: str | None = None) -> None:
        super().__init__(timeout=None)
        if guild_id is not None:
            _t = _get_t()
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    if child.custom_id == "ticket:claim":
                        child.label = _t(guild_id, "tickets.actions.claim_button")
                    elif child.custom_id == "ticket:close":
                        child.label = _t(guild_id, "tickets.actions.close_button")
                    elif child.custom_id == "ticket:edit-category":
                        child.label = _t(guild_id, "tickets.actions.edit_category_button")

    @staticmethod
    async def _get_ticket(
        bot: NebulosaBot, channel_id: int, guild_id: str | None = None, *, action: str = "claim"
    ) -> tuple[dict[str, Any] | None, str | None]:
        if bot.db is None:
            msg = "db not initialised"
            raise RuntimeError(msg)
        _t = _get_t()
        row = await bot.db.get_ticket_by_channel(str(channel_id), guild_id=guild_id)
        if row is None:
            return None, _t(guild_id, f"tickets.actions.{action}_not_ticket_description")
        if row["status"] == "closed":
            return None, _t(guild_id, f"tickets.actions.{action}_already_closed_description")
        return row, None

    @discord.ui.button(label="Reclamar", style=discord.ButtonStyle.success, custom_id="ticket:claim", emoji="✋")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button[discord.ui.View]) -> None:
        _t = _get_t()
        _is_mod_check = _get_is_mod_check()
        bot: NebulosaBot = interaction.client  # type: ignore[assignment]
        channel_id = interaction.channel_id
        guild = interaction.guild
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        if guild_id is not None:
            button.label = _t(guild_id, "tickets.actions.claim_button")
        if channel_id is None:
            return
        if not await _is_mod_check(interaction):
            await interaction.response.send_message(
                embed=error_embed(
                    _t(guild_id, "tickets.actions.claim_mods_only_title"),
                    _t(guild_id, "tickets.actions.claim_mods_only_description"),
                    guild_id=guild_id,
                    bot=bot,
                    guild=guild,
                ),
                ephemeral=True,
            )
            return
        ticket_row, error = await self._get_ticket(bot, channel_id, guild_id)
        if error is not None:
            await interaction.response.send_message(
                embed=error_embed(
                    _t(guild_id, "tickets.actions.claim_failed_title"),
                    error,
                    guild_id=guild_id,
                    bot=bot,
                    guild=guild,
                ),
                ephemeral=True,
            )
            return
        if ticket_row is None:
            msg = "ticket_row not initialised"
            raise RuntimeError(msg)
        claimed_by_id = ticket_row.get("claimedBy")
        if claimed_by_id:
            from bot.views.confirmation import ConfirmCancelView

            ticket_id = ticket_row["id"]
            staff_id = str(interaction.user.id)

            async def _on_transfer_confirm(confirm_interaction: discord.Interaction) -> None:
                if bot.ticket_service is None:
                    msg = "ticket_service not initialised"
                    raise RuntimeError(msg)
                try:
                    ticket = await bot.ticket_service.transfer_ticket(
                        ticket_id,
                        new_claimed_by=staff_id,
                        actor_id=staff_id,
                        guild=guild,
                        logging_service=getattr(bot, "logging_service", None),
                        guild_id=str(guild.id) if guild else "",
                    )
                except ImportError:
                    logger.exception("Failed to transfer ticket %s", ticket_id)
                    await confirm_interaction.response.edit_message(
                        embed=error_embed(
                            _t(guild_id, "tickets.transfer.failed_title"),
                            _t(guild_id, "tickets.transfer.failed_description"),
                            guild_id=guild_id,
                            bot=bot,
                            guild=guild,
                        ),
                        view=None,
                    )
                    return
                transfer_desc = _t(
                    guild_id,
                    "tickets.transfer.success_description",
                    member=interaction.user.mention,
                )
                await confirm_interaction.response.edit_message(
                    embed=discord.Embed(
                        title=_t(guild_id, "tickets.transfer.success_title"),
                        description=transfer_desc,
                        color=SUCCESS,
                    ),
                    view=None,
                )
                from bot.utils.embeds import build_ticket_embed

                embed = build_ticket_embed(ticket, claimed_by=interaction.user, guild_id=guild_id, bot=bot, guild=guild)
                try:
                    msg = interaction.message
                    if msg is not None:
                        await msg.edit(embed=embed)
                except (discord.HTTPException, AttributeError):
                    logger.warning("Failed to refresh ticket embed after transfer in channel %s", channel_id)

            confirm_view = ConfirmCancelView(
                guild_id=guild_id or "",
                owner_id=interaction.user.id,
                on_confirm=_on_transfer_confirm,
            )
            await interaction.response.send_message(
                embed=discord.Embed(
                    title=_t(guild_id, "tickets.actions.transfer_confirm_title"),
                    description=_t(guild_id, "tickets.actions.transfer_confirm_description", current=claimed_by_id),
                    color=WARNING,
                ),
                view=confirm_view,
                ephemeral=True,
            )
            confirm_view.message = await interaction.original_response()
            return
        ticket_id = ticket_row["id"]
        staff_id = str(interaction.user.id)
        if guild_id is None:
            await interaction.response.send_message(
                embed=error_embed(
                    _t(guild_id, "tickets.actions.claim_failed_title"),
                    _t(guild_id, "tickets.actions.claim_generic_error_description"),
                    guild_id=guild_id,
                    bot=bot,
                    guild=guild,
                ),
                ephemeral=True,
            )
            return
        if bot.ticket_service is None:
            msg = "ticket_service not initialised"
            raise RuntimeError(msg)
        try:
            ticket = await bot.ticket_service.claim_ticket(ticket_id, staff_id, guild_id=guild_id)
        except ImportError:
            logger.exception("Failed to claim ticket %s", ticket_id)
            await interaction.response.send_message(
                embed=error_embed(
                    _t(guild_id, "tickets.actions.claim_failed_title"),
                    _t(guild_id, "tickets.actions.claim_generic_error_description"),
                    guild_id=guild_id,
                    bot=bot,
                    guild=guild,
                ),
                ephemeral=True,
            )
            return
        from bot.utils.embeds import build_ticket_embed

        embed = build_ticket_embed(ticket, claimed_by=interaction.user, guild_id=guild_id, bot=bot, guild=guild)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Cerrar", style=discord.ButtonStyle.danger, custom_id="ticket:close", emoji="🔒")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button[discord.ui.View]) -> None:
        _t = _get_t()
        _is_mod_check = _get_is_mod_check()
        bot: NebulosaBot = interaction.client  # type: ignore[assignment]
        channel_id = interaction.channel_id
        guild = interaction.guild
        guild_id = str(guild.id) if guild else None
        if guild_id is not None:
            button.label = _t(guild_id, "tickets.actions.close_button")
        if channel_id is None or guild is None:
            return
        ticket_row, error = await self._get_ticket(bot, channel_id, guild_id, action="close")
        if error is not None:
            await interaction.response.send_message(
                embed=error_embed(
                    _t(guild_id, "tickets.actions.close_failed_title"),
                    error,
                    guild_id=guild_id,
                    bot=bot,
                    guild=guild,
                ),
                ephemeral=True,
            )
            return
        if ticket_row is None:
            msg = "ticket_row not initialised"
            raise RuntimeError(msg)
        author_id = ticket_row.get("authorId")
        is_author = author_id is not None and interaction.user.id == int(author_id)
        if not is_author and not await _is_mod_check(interaction):
            await interaction.response.send_message(
                embed=error_embed(
                    _t(guild_id, "tickets.actions.close_author_or_mod_title"),
                    _t(guild_id, "tickets.actions.close_author_or_mod_description"),
                    guild_id=guild_id,
                    bot=bot,
                    guild=guild,
                ),
                ephemeral=True,
            )
            return

        ticket_id = ticket_row["id"]
        channel = interaction.channel
        closer_id = str(interaction.user.id)

        async def _on_close_confirm(confirm_interaction: discord.Interaction) -> None:
            if not isinstance(channel, discord.TextChannel):
                return
            if bot.ticket_service is None:
                msg = "ticket_service not initialised"
                raise RuntimeError(msg)
            from bot.models.ticket import Ticket

            ticket = Ticket.from_db_row(ticket_row)
            await confirm_interaction.response.edit_message(
                embed=discord.Embed(
                    title=_t(guild_id, "tickets.actions.close_success_title"),
                    description=_t(guild_id, "tickets.actions.close_success_description"),
                    color=_INFO_BRAND,
                ),
                view=None,
            )
            try:
                await bot.ticket_service.close_ticket_full(channel, ticket, closer_id, bot=bot, manual=True)
            except ImportError:
                logger.exception("Failed to close ticket %s", ticket_id)
                await confirm_interaction.followup.send(
                    embed=error_embed(
                        _t(guild_id, "tickets.actions.close_db_error_title"),
                        _t(guild_id, "tickets.actions.close_db_error_description"),
                        guild_id=guild_id,
                        bot=bot,
                        guild=guild,
                    ),
                    ephemeral=True,
                )
                return

        from bot.views.confirmation import ConfirmCancelView

        confirm_view = ConfirmCancelView(
            guild_id=guild_id or "",
            owner_id=interaction.user.id,
            on_confirm=_on_close_confirm,
        )
        await interaction.response.send_message(
            embed=discord.Embed(
                title=_t(guild_id, "tickets.actions.close_confirm_title"),
                description=_t(guild_id, "tickets.actions.close_confirm_description"),
                color=WARNING,
            ),
            view=confirm_view,
            ephemeral=True,
        )
        confirm_view.message = await interaction.original_response()

    @discord.ui.button(
        label="Editar Categoría",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket:edit-category",
        emoji="✏️",
    )
    async def edit_category_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[discord.ui.View],
    ) -> None:
        _t = _get_t()
        _is_mod_check = _get_is_mod_check()
        bot: NebulosaBot = interaction.client  # type: ignore[assignment]
        channel_id = interaction.channel_id
        guild = interaction.guild
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        if guild_id is not None:
            button.label = _t(guild_id, "tickets.actions.edit_category_button")
        if channel_id is None or guild is None or guild_id is None:
            return
        if not await _is_mod_check(interaction):
            await interaction.response.send_message(
                embed=error_embed(
                    _t(guild_id, "tickets.actions.edit_category_mods_only_title"),
                    _t(guild_id, "tickets.actions.edit_category_mods_only_description"),
                    guild_id=guild_id,
                    bot=bot,
                    guild=guild,
                ),
                ephemeral=True,
            )
            return
        if bot.db is None:
            msg = "db not initialised"
            raise RuntimeError(msg)
        ticket_row = await bot.db.get_ticket_by_channel(str(channel_id), guild_id=guild_id)
        if ticket_row is None:
            await interaction.response.send_message(
                embed=error_embed(
                    _t(guild_id, "tickets.actions.edit_category_mods_only_title"),
                    _t(guild_id, "tickets.actions.claim_not_ticket_description"),
                    guild_id=guild_id,
                    bot=bot,
                    guild=guild,
                ),
                ephemeral=True,
            )
            return
        rows = await bot.db.get_ticket_categories(guild_id)
        from bot.models.ticket_category import TicketCategory

        categories = [TicketCategory.from_db_row(r) for r in rows if r.get("active", True)]
        if not categories:
            await interaction.response.send_message(
                embed=error_embed(
                    _t(guild_id, "tickets.actions.edit_category_no_categories_title"),
                    _t(guild_id, "tickets.actions.edit_category_no_categories_description"),
                    guild_id=guild_id,
                    bot=bot,
                    guild=guild,
                ),
                ephemeral=True,
            )
            return
        options = [
            discord.SelectOption(
                label=cat.name,
                value=cat.id,
                description=(cat.description[:100] if cat.description else None),
                emoji=cat.emoji,
            )
            for cat in categories
        ]
        try:
            import bot.views.tickets as _facade

            _edit_category_view_cls = _facade._EditCategoryView
        except ImportError:
            from bot.views.ticket_category_select import _EditCategoryView as _edit_category_view_cls2

        _ecls = _edit_category_view_cls if "_edit_category_view_cls" in dir() else _edit_category_view_cls2
        view = _ecls(options, guild, categories, ticket_row)
        await interaction.response.send_message(
            _t(guild_id, "tickets.open.select_category"),
            view=view,
            ephemeral=True,
        )
