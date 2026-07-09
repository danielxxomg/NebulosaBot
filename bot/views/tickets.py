"""Persistent and ephemeral views for the ticket system.

Moved from ``bot/cogs/tickets.py`` to separate Discord UI components
from command logic. Views call service methods via ``interaction.client``
(the :class:`~bot.bot.NebulosaBot` instance).
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

import discord

from bot.core.i18n import t
from bot.models.ticket_category import TicketCategory
from bot.utils.checks import is_mod_check
from bot.utils.embeds import error_embed, info_embed, success_embed

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)

CHANNEL_DELETE_DELAY = 5  # seconds


async def _create_ticket_after_modal(
    interaction: discord.Interaction,
    guild: discord.Guild,
    category_id: str,
    subject: str | None,
    description: str | None,
) -> None:
    """Shared ticket creation flow used by TicketIntakeModal.on_submit.

    Validates guild config, creates the channel via the service, sends the
    welcome embed, pins it, and sends the ephemeral success followup.
    """
    bot: NebulosaBot = interaction.client  # type: ignore[assignment]
    guild_id = str(guild.id)
    assert bot.db is not None and bot.guild_service is not None and bot.ticket_service is not None

    try:
        config = await bot.guild_service.get_config(guild_id)
    except Exception:
        logger.exception("Failed to fetch guild config for ticket creation (guild=%s)", guild.id)
        await interaction.followup.send(
            embed=error_embed(
                t(guild_id, "tickets.open.config_error_title"),
                t(guild_id, "tickets.open.config_error_description"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )
        return

    if not config.ticket_category_id:
        await interaction.followup.send(
            embed=error_embed(
                t(guild_id, "tickets.config_missing.title"),
                t(guild_id, "tickets.config_missing.description"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )
        return

    ticket_category_channel = guild.get_channel(int(config.ticket_category_id))
    if ticket_category_channel is None or not isinstance(ticket_category_channel, discord.CategoryChannel):
        await interaction.followup.send(
            embed=error_embed(
                t(guild_id, "tickets.open.invalid_category_title"),
                t(guild_id, "tickets.open.invalid_category_description"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )
        return

    mod_role: discord.Role | None = None
    if config.mod_role_id:
        with contextlib.suppress(ValueError, TypeError):
            mod_role = guild.get_role(int(config.mod_role_id))

    author = interaction.user
    assert isinstance(author, discord.Member)
    tentative_max = await bot.db.get_max_ticket_number(guild_id)
    channel_name = f"ticket-{tentative_max + 1:04d}"

    try:
        channel, ticket = await bot.ticket_service.create_ticket_channel(
            guild,
            ticket_category_channel,
            author,
            channel_name,
            guild_id=guild_id,
            category_id=category_id,
            mod_role=mod_role,
            subject=subject,
            description=description,
        )
    except discord.Forbidden:
        await interaction.followup.send(
            embed=error_embed(
                t(guild_id, "tickets.open.permission_denied_title"),
                t(guild_id, "tickets.open.permission_denied_description"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )
        return
    except discord.HTTPException:
        logger.exception("Failed to create ticket channel")
        await interaction.followup.send(
            embed=error_embed(
                t(guild_id, "tickets.open.channel_failed_title"),
                t(guild_id, "tickets.open.channel_failed_description"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )
        return
    except Exception:
        logger.exception("Failed to create ticket in DB")
        await interaction.followup.send(
            embed=error_embed(
                t(guild_id, "tickets.open.creation_failed_title"),
                t(guild_id, "tickets.open.creation_failed_description"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )
        return

    actions_view = TicketActionsView(guild_id=guild_id)
    from bot.utils.embeds import build_ticket_embed

    embed = build_ticket_embed(ticket, guild_id=guild_id)
    message = await channel.send(content=author.mention, embed=embed, view=actions_view)

    # Pin the welcome embed — failure is logged, not fatal.
    try:
        await message.pin()
    except discord.HTTPException:
        logger.warning("Failed to pin welcome message in ticket channel %s", channel.id)

    await interaction.followup.send(
        embed=success_embed(
            t(guild_id, "tickets.open.success_title"),
            t(guild_id, "tickets.open.success_description", channel=channel.mention),
            guild_id=guild_id,
        ),
        ephemeral=True,
    )
    logger.info(
        "Ticket #%d created (guild=%s, channel=%s, author=%s)",
        ticket.ticket_number,
        guild.id,
        channel.id,
        author.id,
    )


class TicketIntakeModal(discord.ui.Modal):
    """Modal shown after category selection to collect ticket title and description."""

    def __init__(
        self,
        guild: discord.Guild,
        category_id: str,
        category_name: str,
    ) -> None:
        guild_id = str(guild.id)
        super().__init__(
            title=t(guild_id, "tickets.modal.title", category=category_name),
            timeout=120,
        )
        self._guild = guild
        self._category_id = category_id

        self.title_input: discord.ui.TextInput[TicketIntakeModal] = discord.ui.TextInput(
            label=t(guild_id, "tickets.modal.subject_label"),
            placeholder=t(guild_id, "tickets.modal.subject_placeholder"),
            style=discord.TextStyle.short,
            required=True,
            max_length=100,
        )
        self.add_item(self.title_input)

        self.description_input: discord.ui.TextInput[TicketIntakeModal] = discord.ui.TextInput(
            label=t(guild_id, "tickets.modal.description_label"),
            placeholder=t(guild_id, "tickets.modal.description_placeholder"),
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=2000,
        )
        self.add_item(self.description_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        subject = self.title_input.value.strip()
        if not subject:
            guild_id = str(self._guild.id)
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "tickets.modal.empty_title"),
                    t(guild_id, "tickets.modal.empty_title_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        description_raw = self.description_input.value.strip() if self.description_input.value else None
        description = description_raw or None

        await interaction.response.defer(ephemeral=True)
        await _create_ticket_after_modal(
            interaction,
            self._guild,
            self._category_id,
            subject=subject,
            description=description,
        )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, *args: Any
    ) -> None:
        logger.exception("TicketIntakeModal error (guild=%s)", self._guild.id, exc_info=error)
        if not interaction.response.is_done():
            guild_id = str(self._guild.id)
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "common.error.unexpected_title"),
                    t(guild_id, "common.error.unexpected_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )


class TicketPanelView(discord.ui.View):
    """Persistent view for the ticket panel message."""

    def __init__(self, guild_id: str | None = None) -> None:
        super().__init__(timeout=None)
        if guild_id is not None:
            for child in self.children:
                if isinstance(child, discord.ui.Button) and child.custom_id == "ticket:open":
                    child.label = t(guild_id, "tickets.panel.open_button")

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, custom_id="ticket:open", emoji="🎫")
    async def open_ticket_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[discord.ui.View]
    ) -> None:
        bot: NebulosaBot = interaction.client  # type: ignore[assignment]
        guild = interaction.guild
        guild_id = str(guild.id) if guild else None
        # Dynamic label resolution at interaction time.
        if guild_id is not None:
            button.label = t(guild_id, "tickets.panel.open_button")
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "tickets.open.server_only_title"), t(guild_id, "tickets.open.server_only_description")
                ),
                ephemeral=True,
            )
            return
        assert bot.db is not None
        rows = await bot.db.get_ticket_categories(str(guild.id))
        categories = [TicketCategory.from_db_row(r) for r in rows if r.get("active", True)]
        if not categories:
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "tickets.panel.no_categories_title"),
                    t(guild_id, "tickets.panel.no_categories_description"),
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
        view = _CategorySelectView(options, guild)
        await interaction.response.send_message(t(guild_id, "tickets.open.select_category"), view=view, ephemeral=True)


class TicketActionsView(discord.ui.View):
    """Persistent per-ticket view with Close and Claim buttons."""

    def __init__(self, guild_id: str | None = None) -> None:
        super().__init__(timeout=None)
        if guild_id is not None:
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    if child.custom_id == "ticket:claim":
                        child.label = t(guild_id, "tickets.actions.claim_button")
                    elif child.custom_id == "ticket:close":
                        child.label = t(guild_id, "tickets.actions.close_button")

    @staticmethod
    async def _get_ticket(
        bot: NebulosaBot, channel_id: int, guild_id: str | None = None, *, action: str = "claim"
    ) -> tuple[dict[str, Any] | None, str | None]:
        assert bot.db is not None
        row = await bot.db.get_ticket_by_channel(str(channel_id))
        if row is None:
            return None, t(guild_id, f"tickets.actions.{action}_not_ticket_description")
        if row["status"] == "closed":
            return None, t(guild_id, f"tickets.actions.{action}_already_closed_description")
        return row, None

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, custom_id="ticket:claim", emoji="✋")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button[discord.ui.View]) -> None:
        bot: NebulosaBot = interaction.client  # type: ignore[assignment]
        channel_id = interaction.channel_id
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        # Dynamic label resolution at interaction time.
        if guild_id is not None:
            button.label = t(guild_id, "tickets.actions.claim_button")
        if channel_id is None:
            return
        if not await is_mod_check(interaction):
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "tickets.actions.claim_mods_only_title"),
                    t(guild_id, "tickets.actions.claim_mods_only_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        ticket_row, error = await self._get_ticket(bot, channel_id, guild_id)
        if error is not None:
            await interaction.response.send_message(
                embed=error_embed(t(guild_id, "tickets.actions.claim_failed_title"), error, guild_id=guild_id),
                ephemeral=True,
            )
            return
        assert ticket_row is not None
        claimed_by_id = ticket_row.get("claimedBy")
        if claimed_by_id:
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "tickets.actions.claim_already_claimed_title"),
                    t(guild_id, "tickets.actions.claim_already_claimed_description", user=claimed_by_id),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        ticket_id = ticket_row["id"]
        staff_id = str(interaction.user.id)
        assert bot.ticket_service is not None
        try:
            ticket = await bot.ticket_service.claim_ticket(ticket_id, staff_id)
        except Exception:
            logger.exception("Failed to claim ticket %s", ticket_id)
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "tickets.actions.claim_failed_title"),
                    t(guild_id, "tickets.actions.claim_generic_error_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        from bot.utils.embeds import build_ticket_embed

        embed = build_ticket_embed(ticket, claimed_by=interaction.user, guild_id=guild_id)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="ticket:close", emoji="🔒")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button[discord.ui.View]) -> None:
        bot: NebulosaBot = interaction.client  # type: ignore[assignment]
        channel_id = interaction.channel_id
        guild = interaction.guild
        guild_id = str(guild.id) if guild else None
        # Dynamic label resolution at interaction time.
        if guild_id is not None:
            button.label = t(guild_id, "tickets.actions.close_button")
        if channel_id is None or guild is None:
            return
        ticket_row, error = await self._get_ticket(bot, channel_id, guild_id, action="close")
        if error is not None:
            await interaction.response.send_message(
                embed=error_embed(t(guild_id, "tickets.actions.close_failed_title"), error, guild_id=guild_id),
                ephemeral=True,
            )
            return
        assert ticket_row is not None
        author_id = ticket_row.get("authorId")
        is_author = author_id is not None and interaction.user.id == int(author_id)
        if not is_author and not await is_mod_check(interaction):
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "tickets.actions.close_author_or_mod_title"),
                    t(guild_id, "tickets.actions.close_author_or_mod_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        ticket_id = ticket_row["id"]
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return
        await interaction.response.defer(ephemeral=True)
        assert bot.ticket_service is not None
        from bot.models.ticket import Ticket

        ticket = Ticket.from_db_row(ticket_row)
        closer_id = str(interaction.user.id)
        try:
            transcript_url = await bot.ticket_service.close_ticket_full(
                channel, ticket, closer_id, bot=bot
            )
        except Exception:
            logger.exception("Failed to close ticket %s", ticket_id)
            await interaction.followup.send(
                embed=error_embed(
                    t(guild_id, "tickets.actions.close_db_error_title"),
                    t(guild_id, "tickets.actions.close_db_error_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        close_msg = t(guild_id, "tickets.actions.closed_channel_message")
        if transcript_url:
            close_msg += t(guild_id, "tickets.actions.closed_channel_transcript", url=transcript_url)
        await channel.send(
            embed=info_embed(t(guild_id, "tickets.actions.closed_channel_title"), close_msg, guild_id=guild_id)
        )
        await interaction.followup.send(
            embed=success_embed(
                t(guild_id, "tickets.actions.close_success_title"),
                t(guild_id, "tickets.actions.close_success_description"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )


class _CategorySelectView(discord.ui.View):
    """Ephemeral view with a category select dropdown."""

    __slots__ = ()

    def __init__(self, options: list[discord.SelectOption], guild: discord.Guild) -> None:
        super().__init__(timeout=300)
        self.add_item(_CategorySelect(options, guild))


class _CategorySelect(discord.ui.Select[discord.ui.View]):
    """Select dropdown populated with ticket categories."""

    __slots__ = ("_guild",)

    def __init__(self, options: list[discord.SelectOption], guild: discord.Guild) -> None:
        guild_id = str(guild.id)
        super().__init__(
            placeholder=t(guild_id, "tickets.open.select_category"), min_values=1, max_values=1, options=options
        )
        self._guild = guild

    async def callback(self, interaction: discord.Interaction) -> None:
        category_id = self.values[0]
        guild = self._guild
        guild_id = str(guild.id)

        # Resolve category name from the select options.
        category_name = next(
            (opt.label for opt in self.options if opt.value == category_id),
            category_id,
        )

        await interaction.response.send_modal(
            TicketIntakeModal(guild, category_id, category_name)
        )
