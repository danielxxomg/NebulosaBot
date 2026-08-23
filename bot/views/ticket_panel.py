"""Panel/intake seam — TicketIntakeModal + TicketPanelView + deploy helpers.

Thin extraction behind :class:`bot.views.tickets` facade. Keeps persistent
panel view and intake modal together (lines 255-419 in original).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import discord

from bot.core.i18n import t as _i18n_t
from bot.models.ticket_category import TicketCategory
from bot.utils.brand import INFO
from bot.utils.embeds import error_embed, guild_footer_icon, success_embed
from bot.utils.ticket_helpers import resolve_mod_role

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger: logging.Logger = logging.getLogger(__name__)


def _get_logger() -> logging.Logger:
    try:
        import bot.views.tickets as _facade
    except ImportError:
        return logger
    else:
        return _facade.logger


CHANNEL_DELETE_DELAY = 5  # seconds


async def deploy_ticket_panel(
    channel: discord.abc.Messageable,
    guild_id: str,
    *,
    bot: NebulosaBot,
    guild: discord.Guild | None = None,
    title: str | None = None,
    description_text: str | None = None,
) -> discord.Message:
    """Deploy a ticket panel embed with a persistent TicketPanelView."""
    # Use direct i18n for deploy (also patched via facade when needed).
    # Resolve via facade t when available to honor patches.
    try:
        import bot.views.tickets as _facade

        _t = _facade.t
    except ImportError:
        _t = _i18n_t  # fallback
    resolved_title = title if title is not None else _t(guild_id, "tickets.panel.default_title")
    resolved_description = (
        description_text if description_text is not None else _t(guild_id, "tickets.panel.default_description")
    )

    embed = discord.Embed(
        title=resolved_title,
        description=resolved_description,
        color=INFO,
        timestamp=datetime.now(UTC),
    )
    embed.set_footer(text=_t(guild_id, "tickets.open.footer"), icon_url=guild_footer_icon(guild, bot))

    msg = await channel.send(embed=embed, view=TicketPanelView(guild_id=guild_id))

    if bot.guild_service is not None:
        await bot.guild_service.update_guild_panel(guild_id, str(msg.id), str(msg.channel.id))

    logger.info("Ticket panel deployed in guild %s (msg=%s)", guild_id, msg.id)
    return msg


async def _create_ticket_after_modal(  # noqa: C901 -- modal orchestration: validation + branching + audit
    interaction: discord.Interaction,
    guild: discord.Guild,
    category_id: str,
    category_name: str,
    subject: str | None,
    description: str | None,
    *,
    custom_fields: dict[str, str] | None = None,
    field_definitions: list[dict[str, Any]] | None = None,
) -> None:
    """Shared ticket creation flow used by TicketIntakeModal.on_submit."""
    try:
        import bot.views.tickets as _facade

        _t = _facade.t
    except ImportError:
        _t = _i18n_t
    bot: NebulosaBot = interaction.client  # type: ignore[assignment]
    guild_id = str(guild.id)
    if bot.db is None:
        msg = "db not initialised"
        raise RuntimeError(msg)
    if bot.guild_service is None:
        msg = "guild_service not initialised"
        raise RuntimeError(msg)
    if bot.ticket_service is None:
        msg = "ticket_service not initialised"
        raise RuntimeError(msg)

    try:
        config = await bot.guild_service.get_config(guild_id)
    except ImportError:
        logger.exception("Failed to fetch guild config for ticket creation (guild=%s)", guild.id)
        await interaction.followup.send(
            embed=error_embed(
                _t(guild_id, "tickets.open.config_error_title"),
                _t(guild_id, "tickets.open.config_error_description"),
                guild_id=guild_id,
                bot=bot,
                guild=guild,
            ),
            ephemeral=True,
        )
        return

    if not config.ticket_category_id:
        await interaction.followup.send(
            embed=error_embed(
                _t(guild_id, "tickets.config_missing.title"),
                _t(guild_id, "tickets.config_missing.description"),
                guild_id=guild_id,
                bot=bot,
                guild=guild,
            ),
            ephemeral=True,
        )
        return

    ticket_category_channel = guild.get_channel(int(config.ticket_category_id))
    if ticket_category_channel is None or not isinstance(ticket_category_channel, discord.CategoryChannel):
        await interaction.followup.send(
            embed=error_embed(
                _t(guild_id, "tickets.open.invalid_category_title"),
                _t(guild_id, "tickets.open.invalid_category_description"),
                guild_id=guild_id,
                bot=bot,
                guild=guild,
            ),
            ephemeral=True,
        )
        return

    mod_role = resolve_mod_role(guild, config.mod_role_id)

    author = interaction.user
    if not isinstance(author, discord.Member):
        msg = "author must be discord.Member"
        raise TypeError(msg)

    try:
        channel, ticket = await bot.ticket_service.create_ticket_channel(
            guild,
            ticket_category_channel,
            author,
            guild_id=guild_id,
            category_name=category_name,
            category_id=category_id,
            mod_role=mod_role,
            subject=subject,
            description=description,
            custom_fields=custom_fields,
        )
    except discord.Forbidden:
        await interaction.followup.send(
            embed=error_embed(
                _t(guild_id, "tickets.open.permission_denied_title"),
                _t(guild_id, "tickets.open.permission_denied_description"),
                guild_id=guild_id,
                bot=bot,
                guild=guild,
            ),
            ephemeral=True,
        )
        return
    except discord.HTTPException:
        logger.exception("Failed to create ticket channel")
        await interaction.followup.send(
            embed=error_embed(
                _t(guild_id, "tickets.open.channel_failed_title"),
                _t(guild_id, "tickets.open.channel_failed_description"),
                guild_id=guild_id,
                bot=bot,
                guild=guild,
            ),
            ephemeral=True,
        )
        return
    except ValueError as exc:
        msg = str(exc).lower()
        if "already has an open" in msg:
            await interaction.followup.send(
                embed=error_embed(
                    _t(guild_id, "tickets.open.limit_title"),
                    _t(
                        guild_id,
                        "tickets.open.limit_description",
                        category=category_name,
                    ),
                    guild_id=guild_id,
                    bot=bot,
                    guild=guild,
                ),
                ephemeral=True,
            )
            return
        logger.exception("Ticket creation rejected by service invariant")
        await interaction.followup.send(
            embed=error_embed(
                _t(guild_id, "tickets.open.creation_failed_title"),
                _t(guild_id, "tickets.open.creation_failed_description"),
                guild_id=guild_id,
                bot=bot,
                guild=guild,
            ),
            ephemeral=True,
        )
        return
    except ImportError:
        logger.exception("Failed to create ticket in DB")
        await interaction.followup.send(
            embed=error_embed(
                _t(guild_id, "tickets.open.creation_failed_title"),
                _t(guild_id, "tickets.open.creation_failed_description"),
                guild_id=guild_id,
                bot=bot,
                guild=guild,
            ),
            ephemeral=True,
        )
        return

    # Use facade's TicketActionsView when patched by tests (patch("bot.views.tickets.TicketActionsView")).
    try:
        import bot.views.tickets as _facade2

        _actions_view_cls = _facade2.TicketActionsView
    except ImportError:
        from bot.views.ticket_actions import TicketActionsView as _actions_view_cls2  # noqa: N813

    _cls = _actions_view_cls if "_actions_view_cls" in dir() else _actions_view_cls2  # ty: ignore[possibly-unresolved-reference]
    actions_view = _cls(guild_id=guild_id)
    from bot.utils.embeds import build_ticket_embed

    embed = build_ticket_embed(ticket, guild_id=guild_id, field_definitions=field_definitions, bot=bot, guild=guild)
    message = await channel.send(content=author.mention, embed=embed, view=actions_view)

    try:
        await message.pin()
    except discord.HTTPException:
        _get_logger().warning("Failed to pin welcome message in ticket channel %s", channel.id)

    await interaction.followup.send(
        embed=success_embed(
            _t(guild_id, "tickets.open.success_title"),
            _t(guild_id, "tickets.open.success_description", channel=channel.mention),
            guild_id=guild_id,
            bot=bot,
            guild=guild,
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
        field_definitions: list[dict[str, Any]] | None = None,
    ) -> None:
        guild_id = str(guild.id)
        # Use facade t when patched, otherwise direct.
        try:
            import bot.views.tickets as _facade

            _t = _facade.t
        except ImportError:
            _t = _i18n_t
        super().__init__(
            title=_t(guild_id, "tickets.modal.title", category=category_name),
            timeout=120,
        )
        self._guild = guild
        self._category_id = category_id
        self._category_name = category_name
        self._field_definitions = field_definitions or []

        self.title_input: discord.ui.TextInput[TicketIntakeModal] = discord.ui.TextInput(
            label=_t(guild_id, "tickets.modal.subject_label"),
            placeholder=_t(guild_id, "tickets.modal.subject_placeholder"),
            style=discord.TextStyle.short,
            required=True,
            max_length=100,
        )
        self.add_item(self.title_input)

        self.description_input: discord.ui.TextInput[TicketIntakeModal] = discord.ui.TextInput(
            label=_t(guild_id, "tickets.modal.description_label"),
            placeholder=_t(guild_id, "tickets.modal.description_placeholder"),
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=2000,
        )
        self.add_item(self.description_input)

        self._custom_inputs: list[discord.ui.TextInput[TicketIntakeModal]] = []
        for defn in self._field_definitions:
            style = discord.TextStyle.paragraph if defn.get("style") == "paragraph" else discord.TextStyle.short
            inp: discord.ui.TextInput[TicketIntakeModal] = discord.ui.TextInput(
                label=defn["label"],
                style=style,
                required=defn.get("required", False),
                max_length=min(defn.get("max_length", 100), 4000),
                placeholder=defn.get("placeholder"),
            )
            self._custom_inputs.append(inp)
            self.add_item(inp)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            import bot.views.tickets as _facade

            _t = _facade.t
        except ImportError:
            _t = _i18n_t
        subject = self.title_input.value.strip()
        if not subject:
            guild_id = str(self._guild.id)
            await interaction.response.send_message(
                embed=error_embed(
                    _t(guild_id, "tickets.modal.empty_title"),
                    _t(guild_id, "tickets.modal.empty_title_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        custom_fields: dict[str, str] = {}
        guild_id = str(self._guild.id)
        for defn, inp in zip(self._field_definitions, self._custom_inputs, strict=True):
            val = inp.value.strip() if inp.value else ""
            if not val:
                if defn.get("required"):
                    await interaction.response.send_message(
                        embed=error_embed(
                            _t(guild_id, "tickets.modal.field_required_title"),
                            _t(guild_id, "tickets.modal.field_required_description", field=defn["label"]),
                            guild_id=guild_id,
                        ),
                        ephemeral=True,
                    )
                    return
                continue
            custom_fields[defn["key"]] = val

        description_raw = self.description_input.value.strip() if self.description_input.value else None
        description = description_raw or None

        await interaction.response.defer(ephemeral=True)
        # Call via facade when patched (patch("bot.views.tickets._create_ticket_after_modal"))
        try:
            import bot.views.tickets as _facade_create

            _creator = _facade_create._create_ticket_after_modal
        except AttributeError:
            _creator = _create_ticket_after_modal
        await _creator(
            interaction,
            self._guild,
            self._category_id,
            self._category_name,
            subject=subject,
            description=description,
            custom_fields=custom_fields,
            field_definitions=self._field_definitions,
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception, *_args: Any) -> None:
        try:
            import bot.views.tickets as _facade

            _t = _facade.t
        except ImportError:
            _t = _i18n_t
        logger.exception("TicketIntakeModal error (guild=%s)", self._guild.id, exc_info=error)
        if not interaction.response.is_done():
            guild_id = str(self._guild.id)
            await interaction.response.send_message(
                embed=error_embed(
                    _t(guild_id, "common.error.unexpected_title"),
                    _t(guild_id, "common.error.unexpected_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )


class TicketPanelView(discord.ui.View):
    """Persistent view for the ticket panel message."""

    def __init__(self, guild_id: str | None = None) -> None:
        super().__init__(timeout=None)
        if guild_id is not None:
            try:
                import bot.views.tickets as _facade

                _t = _facade.t
            except ImportError:
                _t = _i18n_t
            for child in self.children:
                if isinstance(child, discord.ui.Button) and child.custom_id == "ticket:open":
                    child.label = _t(guild_id, "tickets.panel.open_button")

    @discord.ui.button(label="Abrir Ticket", style=discord.ButtonStyle.primary, custom_id="ticket:open", emoji="🎫")
    async def open_ticket_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[discord.ui.View]
    ) -> None:
        try:
            import bot.views.tickets as _facade

            _t = _facade.t
        except ImportError:
            _t = _i18n_t
        bot: NebulosaBot = interaction.client  # type: ignore[assignment]
        guild = interaction.guild
        guild_id = str(guild.id) if guild else None
        if guild_id is not None:
            button.label = _t(guild_id, "tickets.panel.open_button")
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    _t(guild_id, "tickets.open.server_only_title"), _t(guild_id, "tickets.open.server_only_description")
                ),
                ephemeral=True,
            )
            return
        if bot.db is None:
            msg = "db not initialised"
            raise RuntimeError(msg)
        rows = await bot.db.get_ticket_categories(str(guild.id))
        categories = [TicketCategory.from_db_row(r) for r in rows if r.get("active", True)]
        if not categories:
            await interaction.response.send_message(
                embed=error_embed(
                    _t(guild_id, "tickets.panel.no_categories_title"),
                    _t(guild_id, "tickets.panel.no_categories_description"),
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
        # Lazy via facade so patch works and to break circular.
        try:
            import bot.views.tickets as _facade2

            _category_select_view_cls = _facade2._CategorySelectView
        except ImportError:
            from bot.views.ticket_category_select import _CategorySelectView as _category_select_view_cls2

        _ccls = _category_select_view_cls if "_category_select_view_cls" in dir() else _category_select_view_cls2  # ty: ignore[possibly-unresolved-reference]
        view = _ccls(options, guild, categories)
        await interaction.response.send_message(_t(guild_id, "tickets.open.select_category"), view=view, ephemeral=True)
