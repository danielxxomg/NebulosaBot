"""Ephemeral category seams — _CategorySelectView/_CategorySelect/_EditCategoryView/_EditCategorySelect (300s).

Extraction behind :class:`bot.views.tickets` facade. Keeps is_mod_check
revalidation and closed-state re-fetch before mutation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord

from bot.models.ticket_category import TicketCategory
from bot.utils.embeds import error_embed, info_embed, success_embed

if TYPE_CHECKING:
    pass

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


class _CategorySelectView(discord.ui.View):
    """Ephemeral view with a category select dropdown."""

    __slots__ = ()

    def __init__(
        self,
        options: list[discord.SelectOption],
        guild: discord.Guild,
        categories: list[TicketCategory],
    ) -> None:
        super().__init__(timeout=300)
        self.add_item(_CategorySelect(options, guild, categories))


class _CategorySelect(discord.ui.Select[discord.ui.View]):
    """Select dropdown populated with ticket categories."""

    __slots__ = ("_categories", "_guild")

    def __init__(
        self,
        options: list[discord.SelectOption],
        guild: discord.Guild,
        categories: list[TicketCategory],
    ) -> None:
        _t = _get_t()
        guild_id = str(guild.id)
        super().__init__(
            placeholder=_t(guild_id, "tickets.open.select_category"), min_values=1, max_values=1, options=options
        )
        self._guild = guild
        self._categories = categories

    async def callback(self, interaction: discord.Interaction) -> None:
        _t = _get_t()
        category_id = self.values[0]
        guild = self._guild

        category_name = next(
            (opt.label for opt in self.options if opt.value == category_id),
            category_id,
        )

        field_definitions: list[dict[str, Any]] = []
        for cat in self._categories:
            if cat.id == category_id:
                field_definitions = cat.field_definitions
                break

        # Lazy modal import to avoid circular.
        try:
            import bot.views.tickets as _facade

            _modal_cls = _facade.TicketIntakeModal
        except ImportError:
            from bot.views.ticket_panel import TicketIntakeModal as _modal_cls2  # noqa: N813

        _mcls = _modal_cls if "_modal_cls" in dir() else _modal_cls2
        await interaction.response.send_modal(
            _mcls(guild, category_id, category_name, field_definitions=field_definitions)
        )


class _EditCategoryView(discord.ui.View):
    """Ephemeral view (300s) with a category select for editing ticket category."""

    __slots__ = ()

    def __init__(
        self,
        options: list[discord.SelectOption],
        guild: discord.Guild,
        categories: list[TicketCategory],
        ticket_row: dict[str, Any],
    ) -> None:
        super().__init__(timeout=300)
        self.add_item(_EditCategorySelect(options, guild, categories, ticket_row))


class _EditCategorySelect(discord.ui.Select[discord.ui.View]):
    """Select dropdown for editing a ticket's category."""

    __slots__ = ("_categories", "_guild", "_ticket_row")

    def __init__(
        self,
        options: list[discord.SelectOption],
        guild: discord.Guild,
        categories: list[TicketCategory],
        ticket_row: dict[str, Any],
    ) -> None:
        _t = _get_t()
        guild_id = str(guild.id)
        super().__init__(
            placeholder=_t(guild_id, "tickets.open.select_category"),
            min_values=1,
            max_values=1,
            options=options,
        )
        self._guild = guild
        self._categories = categories
        self._ticket_row = ticket_row

    async def callback(self, interaction: discord.Interaction) -> None:
        _t = _get_t()
        _is_mod_check = _get_is_mod_check()
        from bot.bot import NebulosaBot

        new_category_id = self.values[0]
        guild = self._guild
        guild_id = str(guild.id)
        bot: NebulosaBot = interaction.client  # type: ignore[assignment]

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

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return
        if bot.db is None:
            msg = "db not initialised"
            raise RuntimeError(msg)
        ticket_row = await bot.db.get_ticket_by_channel(str(channel.id), guild_id=guild_id)
        if ticket_row is None:
            await interaction.response.send_message(
                embed=error_embed(
                    _t(guild_id, "tickets.actions.edit_category_closed_title"),
                    _t(guild_id, "tickets.actions.edit_category_closed_description"),
                    guild_id=guild_id,
                    bot=bot,
                    guild=guild,
                ),
                ephemeral=True,
            )
            return
        if ticket_row.get("status") == "closed":
            await interaction.response.send_message(
                embed=error_embed(
                    _t(guild_id, "tickets.actions.edit_category_closed_title"),
                    _t(guild_id, "tickets.actions.edit_category_closed_description"),
                    guild_id=guild_id,
                    bot=bot,
                    guild=guild,
                ),
                ephemeral=True,
            )
            return

        ticket_id = ticket_row["id"]
        actor_id = str(interaction.user.id)
        if bot.ticket_service is None:
            msg = "ticket_service not initialised"
            raise RuntimeError(msg)

        category_name = next(
            (opt.label for opt in self.options if opt.value == new_category_id),
            new_category_id,
        )

        try:
            _ticket, rename_succeeded = await bot.ticket_service.edit_ticket_category(
                ticket_id,
                new_category_id,
                channel=channel,
                actor_id=actor_id,
                is_mod=True,
                guild_id=guild_id,
            )
        except ValueError as exc:
            msg = str(exc).lower()
            if "closed" in msg:
                title = _t(guild_id, "tickets.actions.edit_category_closed_title")
                description = _t(
                    guild_id,
                    "tickets.actions.edit_category_closed_description",
                )
            elif "already has an open" in msg:
                title = _t(guild_id, "tickets.actions.edit_category_limit_title")
                description = _t(
                    guild_id,
                    "tickets.actions.edit_category_limit_description",
                )
            else:
                title = _t(guild_id, "common.error.unexpected_title")
                description = str(exc)
            await interaction.response.send_message(
                embed=error_embed(
                    title,
                    description,
                    guild_id=guild_id,
                    bot=bot,
                    guild=guild,
                ),
                ephemeral=True,
            )
            return

        description = _t(
            guild_id,
            "tickets.actions.edit_category_success_description",
            category=category_name,
        )
        if not rename_succeeded:
            description += _t(guild_id, "tickets.actions.edit_category_rename_warning")

        await interaction.response.send_message(
            embed=success_embed(
                _t(guild_id, "tickets.actions.edit_category_success"),
                description,
                guild_id=guild_id,
                bot=bot,
                guild=guild,
            ),
            ephemeral=True,
        )

        old_category_id = ticket_row.get("categoryId")
        old_label = next(
            (opt.label for opt in self.options if opt.value == old_category_id),
            None,
        )
        old_category_name = old_label if old_label is not None else "—"

        try:
            audit_embed = info_embed(
                _t(guild_id, "tickets.actions.edit_category_audit_title"),
                _t(
                    guild_id,
                    "tickets.actions.edit_category_audit_description",
                    old_category=old_category_name,
                    new_category=category_name,
                    actor=interaction.user.mention,
                ),
                guild_id=guild_id,
                bot=bot,
                guild=guild,
            )
            await channel.send(embed=audit_embed)
        except discord.HTTPException:
            logger.warning(
                "Failed to send audit embed in channel %s",
                channel.id,
                exc_info=True,
            )
