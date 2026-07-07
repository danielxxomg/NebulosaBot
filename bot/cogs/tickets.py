"""TicketsCog — ticket system commands, persistent views, and auto-close.

Provides the full ticket lifecycle exposed to Discord users:
  - TicketPanelView (persistent): "Open Ticket" button → category select →
    channel creation with correct permissions.
  - TicketActionsView (persistent): per-channel "Close" and "Claim" buttons.
  - Slash commands: /ticket_panel, /create_category, /list_categories,
    /delete_category — all gated with @is_mod().
  - Auto-close task: ``@tasks.loop(hours=1)`` closing idle tickets (48 h).
  - ``on_message`` listener: updates ``lastActivity`` for ticket channels
    with O(1) early-return via the ticket channel cache.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.models.ticket_category import TicketCategory
from bot.services.ticket_invariants import parse_ticket_ref
from bot.utils.checks import is_mod, is_mod_check
from bot.utils.embeds import (
    COLOR_INFO,
    COLOR_SUCCESS,
    error_embed,
    info_embed,
    success_embed,
)

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)

AUTO_CLOSE_HOURS = 48
CHANNEL_DELETE_DELAY = 5  # seconds


# ======================================================================
# Persistent Views
# ======================================================================


class TicketPanelView(discord.ui.View):
    """Persistent view for the ticket panel message.

    Shows an "Open Ticket" button.  Category selection is handled in
    an ephemeral follow-up message.  One instance registered globally
    in ``setup_hook()``.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Open Ticket",
        style=discord.ButtonStyle.primary,
        custom_id="ticket:open",
        emoji="🎫",
    )
    async def open_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Show category selection then create the ticket channel."""
        bot: NebulosaBot = interaction.client  # type: ignore[assignment]
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed("Server Only", "Tickets can only be opened in a server."),
                ephemeral=True,
            )
            return

        assert bot.db is not None
        # Fetch active ticket categories for this guild.
        rows = await bot.db.get_ticket_categories(str(guild.id))
        categories = [TicketCategory.from_db_row(r) for r in rows if r.get("active", True)]

        if not categories:
            await interaction.response.send_message(
                embed=error_embed(
                    "No Categories",
                    "No ticket categories are configured. Ask an admin to set them up with `/create_category`.",
                ),
                ephemeral=True,
            )
            return

        # Build select options from categories.
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
        await interaction.response.send_message("Select a ticket category:", view=view, ephemeral=True)


class TicketActionsView(discord.ui.View):
    """Persistent per-ticket view with Close and Claim buttons.

    Identifies the ticket via ``interaction.channel_id`` — a single
    globally-registered instance handles all ticket channels.
    Register in ``setup_hook()`` with ``bot.add_view(TicketActionsView())``.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)

    # -- helpers -------------------------------------------------------

    @staticmethod
    async def _get_ticket(bot: NebulosaBot, channel_id: int) -> tuple[dict | None, str | None]:
        """Fetch the ticket row (raw dict) and build a user-facing error.

        Returns ``(row, error_message)`` — exactly one is non-None.
        """
        assert bot.db is not None
        row = await bot.db.get_ticket_by_channel(str(channel_id))
        if row is None:
            return None, "This channel is not an active ticket channel."
        if row["status"] == "closed":
            return None, "This ticket is already closed."
        return row, None

    # -- button callbacks ----------------------------------------------

    @discord.ui.button(
        label="Claim",
        style=discord.ButtonStyle.success,
        custom_id="ticket:claim",
        emoji="✋",
    )
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Claim the ticket, assigning it to the clicking staff member.

        Permission gate (design.md L33-38): Claim is mod-only — the clicking
        user MUST be an admin OR hold the configured moderator role. Non-mods
        receive an ephemeral rejection.
        """
        bot: NebulosaBot = interaction.client  # type: ignore[assignment]
        channel_id = interaction.channel_id
        if channel_id is None:
            return

        # Inline mod gate — @is_mod() cannot decorate discord.ui.button callbacks.
        if not await is_mod_check(interaction):
            await interaction.response.send_message(
                embed=error_embed(
                    "Mods Only",
                    "Only moderators can claim tickets.",
                ),
                ephemeral=True,
            )
            return

        ticket_row, error = await self._get_ticket(bot, channel_id)
        if error is not None:
            await interaction.response.send_message(embed=error_embed("Claim Failed", error), ephemeral=True)
            return

        assert ticket_row is not None
        # Check if already claimed.
        claimed_by_id = ticket_row.get("claimedBy")
        if claimed_by_id:
            await interaction.response.send_message(
                embed=error_embed(
                    "Already Claimed",
                    f"This ticket is already claimed by <@{claimed_by_id}>.",
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
                embed=error_embed("Claim Failed", "Could not claim the ticket. Please try again."),
                ephemeral=True,
            )
            return

        # Update the embed to show the claimed status.
        embed = _build_ticket_embed(ticket, claimed_by=interaction.user)
        await interaction.response.edit_message(embed=embed, view=self)
        logger.info(
            "Ticket %s claimed by %s in channel %s",
            ticket_id,
            staff_id,
            channel_id,
        )

    @discord.ui.button(
        label="Close",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:close",
        emoji="🔒",
    )
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Close the ticket: generate transcript, upload, delete channel.

        Permission gate (design.md L40-44): Close is author OR mod — the
        clicking user MUST be the ticket author OR an admin / configured mod.
        Non-author non-mod users receive an ephemeral rejection.
        """
        bot: NebulosaBot = interaction.client  # type: ignore[assignment]
        channel_id = interaction.channel_id
        guild = interaction.guild
        if channel_id is None or guild is None:
            return

        ticket_row, error = await self._get_ticket(bot, channel_id)
        if error is not None:
            await interaction.response.send_message(embed=error_embed("Close Failed", error), ephemeral=True)
            return

        assert ticket_row is not None
        # Inline author-or-mod gate — @is_mod() cannot decorate button callbacks.
        author_id = ticket_row.get("authorId")
        is_author = author_id is not None and interaction.user.id == int(author_id)
        if not is_author and not await is_mod_check(interaction):
            await interaction.response.send_message(
                embed=error_embed(
                    "Author or Mod Only",
                    "Only the ticket author or a moderator can close this ticket.",
                ),
                ephemeral=True,
            )
            return

        ticket_id = ticket_row["id"]
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return

        await interaction.response.defer(ephemeral=True)

        # 1. Generate transcript.
        assert bot.transcript_service is not None
        assert bot.guild_service is not None
        assert bot.ticket_service is not None
        transcript_url: str | None = None
        try:
            transcript_file = await bot.transcript_service.generate(channel)

            # Resolve log channel for transcript upload.
            log_channel: discord.TextChannel | None = None
            try:
                config = await bot.guild_service.get_config(str(guild.id))
                if config.log_channel_id:
                    ch = guild.get_channel(int(config.log_channel_id))
                    if isinstance(ch, discord.TextChannel):
                        log_channel = ch
            except Exception:
                pass

            if log_channel is not None:
                transcript_url = await bot.transcript_service.upload(transcript_file, log_channel)
            else:
                logger.warning(
                    "No log channel configured for guild %s — skipping transcript upload",
                    guild.id,
                )
        except Exception:
            logger.exception("Transcript generation/upload failed for ticket %s", ticket_id)

        # 2. Close ticket in DB.
        closer_id = str(interaction.user.id)
        try:
            await bot.ticket_service.close_ticket(ticket_id, closed_by=closer_id, transcript_url=transcript_url)
        except Exception:
            logger.exception("Failed to close ticket %s in DB", ticket_id)
            await interaction.followup.send(
                embed=error_embed(
                    "Close Failed",
                    "Could not close the ticket in the database.",
                ),
                ephemeral=True,
            )
            return

        # 3. Notify in channel (non-ephemeral, visible to all).
        close_msg = "Ticket closed"
        if transcript_url:
            close_msg += f" — [Transcript]({transcript_url})"
        await channel.send(embed=info_embed("Ticket Closed", close_msg))

        # 4. Delete channel after a short delay.
        await interaction.followup.send(
            embed=success_embed("Ticket Closed", "The ticket has been closed."),
            ephemeral=True,
        )
        await asyncio.sleep(CHANNEL_DELETE_DELAY)
        try:
            await channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.HTTPException:
            logger.exception("Failed to delete ticket channel %s", channel.id)


# ======================================================================
# Category Select (ephemeral, one-shot)
# ======================================================================


class _CategorySelectView(discord.ui.View):
    """Ephemeral view with a category select dropdown.

    Shown to the user after clicking "Open Ticket".  Expires after
    5 minutes — not persistent.
    """

    __slots__ = ()

    def __init__(self, options: list[discord.SelectOption], guild: discord.Guild) -> None:
        super().__init__(timeout=300)
        self.add_item(_CategorySelect(options, guild))


class _CategorySelect(discord.ui.Select):
    """Select dropdown populated with ticket categories.

    When the user picks a category the ticket is created immediately.
    """

    __slots__ = ("_guild",)

    def __init__(self, options: list[discord.SelectOption], guild: discord.Guild) -> None:
        super().__init__(
            placeholder="Choose a ticket category...",
            min_values=1,
            max_values=1,
            options=options,
        )
        self._guild = guild

    async def callback(self, interaction: discord.Interaction) -> None:
        """Create the ticket channel and DB record."""
        category_id = self.values[0]
        bot: NebulosaBot = interaction.client  # type: ignore[assignment]
        guild = self._guild
        assert bot.db is not None
        assert bot.guild_service is not None
        assert bot.ticket_service is not None

        await interaction.response.defer(ephemeral=True)

        # --- Fetch guild config for ticket category channel & mod role. ---
        try:
            config = await bot.guild_service.get_config(str(guild.id))
        except Exception:
            logger.exception(
                "Failed to fetch guild config for ticket creation (guild=%s)",
                guild.id,
            )
            await interaction.followup.send(
                embed=error_embed("Config Error", "Could not load guild configuration."),
                ephemeral=True,
            )
            return

        if not config.ticket_category_id:
            await interaction.followup.send(
                embed=error_embed(
                    "Not Configured",
                    "The ticket category channel has not been configured. Ask an admin to set it up.",
                ),
                ephemeral=True,
            )
            return

        ticket_category_channel = guild.get_channel(int(config.ticket_category_id))
        if ticket_category_channel is None or not isinstance(ticket_category_channel, discord.CategoryChannel):
            await interaction.followup.send(
                embed=error_embed(
                    "Invalid Category",
                    "The configured Discord category for tickets no longer exists.",
                ),
                ephemeral=True,
            )
            return

        # Resolve mod role for channel permission overwrites.
        mod_role: discord.Role | None = None
        if config.mod_role_id:
            with contextlib.suppress(ValueError, TypeError):
                mod_role = guild.get_role(int(config.mod_role_id))

        author = interaction.user
        assert isinstance(author, discord.Member)

        # --- Get tentative ticket number for channel naming. ---
        tentative_max = await bot.db.get_max_ticket_number(str(guild.id))
        tentative_number = tentative_max + 1
        channel_name = f"ticket-{tentative_number:04d}"

        # --- Build permission overwrites. ---
        overwrites: dict[
            discord.Role | discord.Member | discord.Object,
            discord.PermissionOverwrite,
        ] = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        if mod_role is not None:
            overwrites[mod_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # --- Create the Discord channel. ---
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=ticket_category_channel,
                overwrites=overwrites,
                reason=f"Ticket opened by {author}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed(
                    "Permission Denied",
                    "I don't have permission to create channels in the ticket category.",
                ),
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            logger.exception("Failed to create ticket channel")
            await interaction.followup.send(
                embed=error_embed(
                    "Channel Creation Failed",
                    "Could not create the ticket channel. Please try again.",
                ),
                ephemeral=True,
            )
            return

        # --- Create ticket in DB (MAX+1 with retry). ---
        try:
            ticket = await bot.ticket_service.create_ticket(
                guild_id=str(guild.id),
                author_id=str(author.id),
                category_id=category_id,
                channel_id=str(channel.id),
            )
        except Exception:
            logger.exception("Failed to create ticket in DB")
            # Clean up the orphan channel.
            with contextlib.suppress(discord.HTTPException):
                await channel.delete(reason="Ticket creation failed — cleanup")
            await interaction.followup.send(
                embed=error_embed(
                    "Ticket Creation Failed",
                    "Could not create the ticket. Please try again.",
                ),
                ephemeral=True,
            )
            return

        # --- Rename channel if the actual number differs. ---
        actual_name = f"ticket-{ticket.ticket_number:04d}"
        if channel.name != actual_name:
            try:
                await channel.edit(name=actual_name)
            except discord.HTTPException:
                logger.warning(
                    "Failed to rename ticket channel %s → %s",
                    channel.id,
                    actual_name,
                )

        # --- Register actions view for this channel. ---
        # The persistent view is already registered globally; just attach
        # it to the welcome message.
        actions_view = TicketActionsView()
        embed = _build_ticket_embed(ticket)
        await channel.send(
            content=author.mention,
            embed=embed,
            view=actions_view,
        )

        # --- Confirm to the user (ephemeral). ---
        await interaction.followup.send(
            embed=success_embed(
                "Ticket Created",
                f"Your ticket has been created: {channel.mention}",
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


# ======================================================================
# Embed builders
# ======================================================================


def _build_ticket_embed(
    ticket,  # Ticket model (or dict with ticketNumber, status, etc.)
    *,
    claimed_by: discord.User | discord.Member | None = None,
) -> discord.Embed:
    """Build the welcome / info embed for a ticket channel.

    Called when the channel is created and after claim.
    """
    # Support both Ticket model and raw dict.
    if isinstance(ticket, dict):
        number = ticket.get("ticketNumber", "?")
        status = ticket.get("status", "open")
        author_id = ticket.get("authorId", "unknown")
    else:
        number = ticket.ticket_number
        status = ticket.status
        author_id = ticket.author_id

    if status == "claimed":
        color = COLOR_INFO
        title = f"🎫 Ticket #{number} — Claimed"
        description = "A staff member has claimed this ticket and will assist you shortly."
        if claimed_by is not None:
            description += f"\n**Claimed by:** {claimed_by.mention}"
    else:
        color = COLOR_SUCCESS
        title = f"🎫 Ticket #{number}"
        description = "Welcome! A staff member will assist you soon.\nDescribe your issue and a moderator will respond."

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(UTC),
    )
    embed.add_field(name="Author", value=f"<@{author_id}>", inline=True)
    embed.set_footer(text="NebulosaBot • Tickets")
    return embed


# ======================================================================
# TicketsCog
# ======================================================================


class TicketsCog(commands.Cog, name="Tickets"):
    """Ticket system commands, views, and background tasks."""

    __slots__ = ("bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot

    # ==================================================================
    # Lifecycle
    # ==================================================================

    async def cog_load(self) -> None:
        """Start background tasks and sync the ticket channel cache."""
        logger.info("TicketsCog loading — syncing channel cache ...")

        # Populate the ticket channel cache from the database.
        await self._sync_channel_cache()

        # Start the auto-close loop.
        if not self.auto_close_stale_tickets.is_running():
            self.auto_close_stale_tickets.start()
            logger.info("Auto-close task started (interval: %d h)", AUTO_CLOSE_HOURS)

    async def cog_unload(self) -> None:
        """Cancel background tasks."""
        if self.auto_close_stale_tickets.is_running():
            self.auto_close_stale_tickets.cancel()
            logger.info("Auto-close task cancelled")

    async def _sync_channel_cache(self) -> None:
        """Rebuild the ``_ticket_channel_cache`` from the database.

        Queries all guilds the bot is in and collects open/claimed ticket
        channel IDs.
        """
        all_channel_ids: set[int] = set()
        assert self.bot.db is not None
        assert self.bot.ticket_service is not None
        for guild in self.bot.guilds:
            try:
                ids = await self.bot.db.get_open_ticket_channel_ids(str(guild.id))
                for cid in ids:
                    with contextlib.suppress(ValueError, TypeError):
                        all_channel_ids.add(int(cid))
            except Exception:
                logger.exception(
                    "Failed to load open ticket channel IDs for guild %s",
                    guild.id,
                )
        self.bot.ticket_service.sync_channel_cache(all_channel_ids)
        logger.info("Ticket channel cache synced: %d active channels", len(all_channel_ids))

    # ==================================================================
    # Tasks
    # ==================================================================

    @tasks.loop(hours=1)
    async def auto_close_stale_tickets(self) -> None:
        """Close tickets with no activity for ``AUTO_CLOSE_HOURS`` hours.

        For each stale ticket: generate a transcript, upload it to the
        log channel, close the DB record, and delete the Discord channel.
        """
        logger.info("Auto-close task: checking for stale tickets ...")
        closed_count = 0
        assert self.bot.guild_service is not None
        assert self.bot.ticket_service is not None
        assert self.bot.transcript_service is not None

        for guild in self.bot.guilds:
            guild_id = str(guild.id)

            # Resolve the log channel (optional).
            log_channel: discord.TextChannel | None = None
            try:
                config = await self.bot.guild_service.get_config(guild_id)
                if config.log_channel_id:
                    try:
                        ch = guild.get_channel(int(config.log_channel_id))
                        if isinstance(ch, discord.TextChannel):
                            log_channel = ch
                    except (ValueError, TypeError):
                        pass
            except Exception:
                logger.exception(
                    "Failed to fetch guild config for auto-close (guild=%s)",
                    guild_id,
                )
                continue

            # Fetch stale tickets.
            try:
                stale = await self.bot.ticket_service.get_stale_tickets(guild_id, hours=AUTO_CLOSE_HOURS)
            except Exception:
                logger.exception("Failed to query stale tickets for guild %s", guild_id)
                continue

            for ticket in stale:
                try:
                    await self._close_one_ticket(
                        ticket,
                        guild,
                        log_channel,
                        reason="Auto-closed due to inactivity (48 h)",
                    )
                    closed_count += 1
                except Exception:
                    logger.exception("Failed to auto-close stale ticket %s", ticket.id)

        if closed_count:
            logger.info("Auto-close task: closed %d stale ticket(s)", closed_count)
        else:
            logger.debug("Auto-close task: no stale tickets found")

    @auto_close_stale_tickets.before_loop
    async def _before_auto_close(self) -> None:
        """Wait until the bot is ready before starting the auto-close loop."""
        await self.bot.wait_until_ready()

    async def _close_one_ticket(
        self,
        ticket,
        guild: discord.Guild,
        log_channel: discord.TextChannel | None,
        *,
        reason: str,
    ) -> None:
        """Close a single ticket: transcript → upload → DB update → delete channel."""
        assert self.bot.ticket_service is not None
        assert self.bot.transcript_service is not None
        channel = self.bot.get_channel(int(ticket.channel_id))
        if channel is None or not isinstance(channel, discord.TextChannel):
            # Channel was deleted externally — just close the DB record.
            await self.bot.ticket_service.close_ticket(ticket.id)
            logger.info(
                "Ticket %s closed (channel %s already deleted)",
                ticket.id,
                ticket.channel_id,
            )
            return

        # 1. Transcript.
        transcript_url: str | None = None
        try:
            transcript_file = await self.bot.transcript_service.generate(channel)
            if log_channel is not None:
                transcript_url = await self.bot.transcript_service.upload(transcript_file, log_channel)
        except Exception:
            logger.exception("Transcript generation failed for stale ticket %s", ticket.id)

        # 2. Close in DB.
        await self.bot.ticket_service.close_ticket(ticket.id, transcript_url=transcript_url)

        # 3. Delete channel silently after delay.
        await asyncio.sleep(CHANNEL_DELETE_DELAY)
        try:
            await channel.delete(reason=reason)
        except discord.HTTPException:
            logger.exception("Failed to delete stale ticket channel %s", channel.id)

    # ==================================================================
    # Listeners
    # ==================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Update ``lastActivity`` for messages sent in ticket channels.

        Uses the cached channel set from ``TicketService`` for O(1)
        early exit when the message is not in a ticket channel.
        """
        if message.author.bot:
            return

        if message.guild is None:
            return

        ticket_service = getattr(self.bot, "ticket_service", None)
        if ticket_service is None:
            return

        # O(1) set lookup.
        if not ticket_service.is_ticket_channel(message.channel.id):
            return

        assert self.bot.db is not None
        try:
            await self.bot.db.update_ticket_last_activity(str(message.channel.id))
            logger.debug(
                "lastActivity updated for ticket channel %s",
                message.channel.id,
            )
        except Exception:
            logger.exception(
                "Failed to update lastActivity for channel %s",
                message.channel.id,
            )

    # ==================================================================
    # Slash Commands
    # ==================================================================

    # -- /ticket_panel --------------------------------------------------

    @commands.hybrid_command(
        name="ticket_panel",
        description="Deploy the ticket panel to the current channel",
    )
    @app_commands.describe(
        title="Optional title for the panel embed",
        description_text="Optional description for the panel embed",
    )
    @is_mod()
    async def ticket_panel(
        self,
        ctx: commands.Context,
        *,
        title: str = "Support Tickets",
        description_text: str = (
            "Click the button below to open a support ticket. A staff member will assist you shortly."
        ),
    ) -> None:
        """Deploy (or redeploy) the ticket panel in the current channel.

        Stores the message and channel IDs in the guild configuration
        so the panel survives bot restarts.
        """
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Server Only", "The ticket panel can only be deployed in a server."))
            return

        assert self.bot.db is not None
        # Build the panel embed.
        embed = discord.Embed(
            title=title,
            description=description_text,
            color=COLOR_INFO,
            timestamp=datetime.now(UTC),
        )
        embed.set_footer(text="NebulosaBot • Tickets")

        view = TicketPanelView()

        try:
            message = await ctx.send(embed=embed, view=view)
        except discord.Forbidden:
            await ctx.send(
                embed=error_embed(
                    "Permission Denied",
                    "I don't have permission to send messages here.",
                )
            )
            return

        # Persist panel IDs so the view re-attaches after restart.
        try:
            await self.bot.db.update_guild_panel(
                str(ctx.guild.id),
                str(message.id),
                str(message.channel.id),
            )
            logger.info(
                "Ticket panel deployed in guild %s (msg=%s, ch=%s)",
                ctx.guild.id,
                message.id,
                message.channel.id,
            )
        except Exception:
            logger.exception("Failed to persist ticket panel for guild %s", ctx.guild.id)
            await ctx.send(
                embed=error_embed(
                    "Persistence Error",
                    "The panel was sent but the IDs could not be saved. It will not survive a bot restart.",
                )
            )
            return

        await ctx.send(
            embed=success_embed(
                "Panel Deployed",
                "The ticket panel has been deployed successfully.",
            ),
            delete_after=10,
        )

    # -- /create_category -----------------------------------------------

    @commands.hybrid_command(
        name="create_category",
        description="Create a new ticket category",
    )
    @app_commands.describe(
        name="Category name (e.g. 'Support', 'Bug Report')",
        emoji="Optional emoji to display in the panel",
        description="Optional short description",
        position="Display order (lower = first). Auto-increments if omitted",
    )
    @is_mod()
    async def create_category(
        self,
        ctx: commands.Context,
        name: str,
        emoji: str | None = None,
        description: str | None = None,
        position: int | None = None,
    ) -> None:
        """Create a new ticket category for the guild."""
        if ctx.guild is None:
            return

        assert self.bot.db is not None
        guild_id = str(ctx.guild.id)

        # Validate emoji (discord.py doesn't enforce this on str params).
        if emoji is not None and len(emoji) > 2:
            # Could be a custom emoji like <:name:id> — allow it.
            pass

        # Check for duplicate category name in this guild.
        try:
            existing = await self.bot.db.get_ticket_categories(guild_id)
            if any(cat.get("name", "").lower() == name.lower() for cat in existing):
                await ctx.send(
                    embed=error_embed(
                        "Duplicate Name",
                        f"A ticket category named **{name}** already exists in this server.",
                    )
                )
                return

            # Auto-increment position if not explicitly provided.
            if position is None:
                max_pos = max((cat.get("position", 0) for cat in existing), default=0)
                position = max_pos + 1
        except Exception:
            logger.exception("Failed to check for duplicate category name")
            await ctx.send(
                embed=error_embed(
                    "Check Failed",
                    "Could not verify category uniqueness. Please try again.",
                )
            )
            return

        try:
            row = await self.bot.db.insert_ticket_category(
                guild_id=guild_id,
                name=name,
                emoji=emoji,
                description=description,
                position=position,
            )
            category = TicketCategory.from_db_row(row)
        except Exception:
            logger.exception("Failed to create ticket category")
            await ctx.send(
                embed=error_embed(
                    "Creation Failed",
                    "Could not create the ticket category. Please try again.",
                )
            )
            return

        await ctx.send(
            embed=success_embed(
                "Category Created",
                f"Ticket category **{category.name}** has been created.\nID: `{category.id}`",
            )
        )

    # -- /list_categories -----------------------------------------------

    @commands.hybrid_command(
        name="list_categories",
        description="List all active ticket categories",
    )
    @is_mod()
    async def list_categories(self, ctx: commands.Context) -> None:
        """List all active ticket categories for the guild."""
        if ctx.guild is None:
            return

        assert self.bot.db is not None
        guild_id = str(ctx.guild.id)

        try:
            rows = await self.bot.db.get_ticket_categories(guild_id)
            categories = [TicketCategory.from_db_row(r) for r in rows if r.get("active", True)]
        except Exception:
            logger.exception("Failed to fetch ticket categories")
            await ctx.send(
                embed=error_embed(
                    "Query Failed",
                    "Could not retrieve ticket categories. Please try again.",
                )
            )
            return

        if not categories:
            await ctx.send(
                embed=info_embed(
                    "No Categories",
                    "No ticket categories have been created yet. Use `/create_category` to add one.",
                )
            )
            return

        # Build a clean listing embed.
        lines: list[str] = []
        for cat in categories:
            emoji_str = f"{cat.emoji} " if cat.emoji else ""
            desc_str = f" — {cat.description}" if cat.description else ""
            lines.append(f"{emoji_str}**{cat.name}**{desc_str}\n　↳ ID: `{cat.id}` · Position: {cat.position}")

        embed = discord.Embed(
            title="📋 Ticket Categories",
            description="\n".join(lines),
            color=COLOR_INFO,
            timestamp=datetime.now(UTC),
        )
        embed.set_footer(text="NebulosaBot • Tickets")
        await ctx.send(embed=embed)

    # -- /delete_category -----------------------------------------------

    @commands.hybrid_command(
        name="delete_category",
        description="Delete a ticket category by ID",
    )
    @app_commands.describe(
        category_id="The UUID of the category to delete (from /list_categories)",
    )
    @is_mod()
    async def delete_category(self, ctx: commands.Context, category_id: str) -> None:
        """Delete a ticket category by its UUID.

        This is a hard delete — the category is removed from the database.
        """
        if ctx.guild is None:
            return

        assert self.bot.db is not None
        # Verify the category exists and belongs to this guild.
        try:
            row = await self.bot.db.get_ticket_category(category_id)
        except Exception:
            logger.exception("Failed to fetch ticket category %s", category_id)
            await ctx.send(embed=error_embed("Query Failed", "Could not verify the category. Please try again."))
            return

        if row is None:
            await ctx.send(
                embed=error_embed(
                    "Not Found",
                    f"No ticket category found with ID `{category_id}`.",
                )
            )
            return

        guild_id = str(ctx.guild.id)
        if row.get("guildId") != guild_id:
            await ctx.send(
                embed=error_embed(
                    "Wrong Guild",
                    "That category belongs to a different server.",
                )
            )
            return

        cat_name = row.get("name", category_id)

        # Check for open tickets referencing this category.
        try:
            open_count = await self.bot.db.count_open_tickets_by_category(category_id)
        except Exception:
            logger.exception("Failed to count open tickets for category %s", category_id)
            await ctx.send(
                embed=error_embed(
                    "Check Failed",
                    "Could not verify open tickets for this category. Please try again.",
                )
            )
            return

        if open_count > 0:
            await ctx.send(
                embed=error_embed(
                    "Category In Use",
                    f"Cannot delete category **{cat_name}** because it has **{open_count}** open ticket(s).",
                )
            )
            return

        try:
            await self.bot.db.delete_ticket_category(category_id)
        except Exception:
            logger.exception("Failed to delete ticket category %s", category_id)
            await ctx.send(
                embed=error_embed(
                    "Deletion Failed",
                    "Could not delete the category. Please try again.",
                )
            )
            return

        await ctx.send(
            embed=success_embed(
                "Category Deleted",
                f"Ticket category **{cat_name}** has been deleted.",
            )
        )

    # ==================================================================
    # Subsidiados commands (slice 2): subticket, reopen, transfer, note
    # ==================================================================

    # -- /subticket create ----------------------------------------------

    @commands.hybrid_group(name="subticket", fallback="help")
    @is_mod()
    async def subticket(self, ctx: commands.Context) -> None:
        """Sub-ticket commands (staff-only).

        With ``fallback="help"`` the group callback is bound as the
        ``help`` subcommand — both ``/subticket`` and ``/subticket help``
        show this message (discord.py requires ``fallback`` for slash
        groups to be directly invokable).
        """
        await ctx.send(
            embed=info_embed(
                "Sub-tickets",
                "Use `/subticket create` to create a sub-ticket from the current ticket channel.",
            )
        )

    @staticmethod
    async def _resolve_parent_owner(
        guild: discord.Guild,
        parent_author_id: str,
        ctx: commands.Context,
    ) -> discord.Member | None:
        """Resolve the parent ticket author as a guild Member (B3).

        Uses the guild member cache first, then ``fetch_member`` for
        offline members. On resolution failure, logs the exception and
        sends a user-safe ``error_embed`` to *ctx*; the caller MUST
        return early when this returns ``None``.
        """
        if not parent_author_id:
            await ctx.send(
                embed=error_embed(
                    "Owner Not Found",
                    "The parent ticket has no recorded author.",
                )
            )
            return None
        try:
            member = guild.get_member(int(parent_author_id))
            if member is not None:
                return member
            return await guild.fetch_member(int(parent_author_id))
        except (discord.NotFound, discord.HTTPException, ValueError, TypeError):
            logger.exception("Failed to resolve parent ticket owner %s", parent_author_id)
            await ctx.send(
                embed=error_embed(
                    "Owner Not Found",
                    "Could not resolve the parent ticket owner. "
                    "Please verify the parent ticket author is still "
                    "in this server.",
                )
            )
            return None

    @subticket.command(name="create")
    @app_commands.describe(
        parent_id="The UUID of the parent ticket (omitted: uses current channel)",
    )
    @is_mod()
    async def subticket_create(self, ctx: commands.Context, parent_id: str | None = None) -> None:
        """Create a sub-ticket linked to the current ticket channel's ticket.

        The parent is resolved from the current channel unless an explicit
        ``parent_id`` is given. A new Discord channel is created and the
        sub-ticket is inserted via :meth:`TicketService.create_subticket`,
        which performs the four ``parentId`` FK validations.
        """
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Server Only", "Sub-tickets can only be created in a server."))
            return

        guild = ctx.guild
        author = ctx.author
        assert isinstance(author, discord.Member)
        assert self.bot.db is not None
        assert self.bot.guild_service is not None
        assert self.bot.ticket_service is not None

        # Resolve guild config + Discord ticket category.
        try:
            config = await self.bot.guild_service.get_config(str(guild.id))
        except Exception:
            logger.exception("Failed to fetch guild config for sub-ticket (guild=%s)", guild.id)
            await ctx.send(embed=error_embed("Config Error", "Could not load guild configuration."))
            return

        if not config.ticket_category_id:
            await ctx.send(
                embed=error_embed(
                    "Not Configured",
                    "The ticket category channel has not been configured.",
                )
            )
            return

        try:
            category_channel = guild.get_channel(int(config.ticket_category_id))
        except (ValueError, TypeError):
            category_channel = None
        if not isinstance(category_channel, discord.CategoryChannel):
            await ctx.send(
                embed=error_embed(
                    "Invalid Category",
                    "The configured Discord category for tickets no longer exists.",
                )
            )
            return

        # Resolve the parent ticket (explicit id or current channel).
        # B4: wrap the parent lookup so a DB failure does not surface a
        # raw traceback.
        try:
            if parent_id is None:
                parent_row = await self.bot.db.get_ticket_by_channel(str(ctx.channel.id))
            else:
                parent_row = await self.bot.db.get_ticket(parent_id)
        except Exception:
            logger.exception(
                "Failed to look up parent ticket (channel=%s, parent_id=%s)",
                ctx.channel.id,
                parent_id,
            )
            await ctx.send(
                embed=error_embed(
                    "Lookup Failed",
                    "Could not look up the parent ticket. Please try again.",
                )
            )
            return
        if parent_row is None or parent_row.get("status") == "closed":
            await ctx.send(
                embed=error_embed(
                    "Not a Ticket",
                    "This command must be used in an open ticket channel.",
                )
            )
            return
        parent_id = parent_row["id"]
        parent_author_id = parent_row.get("authorId", str(author.id))

        # B3: resolve the parent ticket author as a Member for overwrites +
        # mention. The sub-ticket belongs to the parent owner, not the
        # invoker (staff). If the invoker IS the parent owner, reuse the
        # author object directly; otherwise resolve via the guild cache
        # and fall back to fetch_member for offline members.
        if str(author.id) == parent_author_id:
            parent_owner: discord.Member = author
        else:
            parent_owner = await self._resolve_parent_owner(guild, parent_author_id, ctx)
            if parent_owner is None:
                return

        # Build permission overwrites.
        overwrites: dict[
            discord.Role | discord.Member | discord.Object,
            discord.PermissionOverwrite,
        ] = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            parent_owner: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        if config.mod_role_id:
            try:
                mod_role = guild.get_role(int(config.mod_role_id))
                if mod_role is not None:
                    overwrites[mod_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            except (ValueError, TypeError):
                pass

        # Tentative channel name (renamed after the real number is known).
        # B4: wrap the max-number lookup so a DB failure is user-safe.
        try:
            tentative_max = await self.bot.db.get_max_ticket_number(str(guild.id))
        except Exception:
            logger.exception("Failed to fetch max ticket number (guild=%s)", guild.id)
            await ctx.send(
                embed=error_embed(
                    "Lookup Failed",
                    "Could not determine the next ticket number. Please try again.",
                )
            )
            return
        channel_name = f"ticket-{tentative_max + 1:04d}"

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category_channel,
                overwrites=overwrites,
                reason=f"Sub-ticket opened by {author} (parent={parent_id})",
            )
        except discord.HTTPException:
            logger.exception("Failed to create sub-ticket channel")
            await ctx.send(
                embed=error_embed(
                    "Channel Creation Failed",
                    "Could not create the sub-ticket channel.",
                )
            )
            return

        # Create the sub-ticket in the DB (4 FK validations live in the service).
        try:
            ticket = await self.bot.ticket_service.create_subticket(
                parent_id=parent_id,
                author_id=parent_author_id,
                category_id=None,
                channel_id=str(channel.id),
                guild_id=str(guild.id),
            )
        except Exception:
            logger.exception("Failed to create sub-ticket in DB (parent=%s)", parent_id)
            # Clean up the orphan channel.
            with contextlib.suppress(discord.HTTPException):
                await channel.delete(reason="Sub-ticket creation failed — cleanup")
            await ctx.send(
                embed=error_embed(
                    "Sub-ticket Creation Failed",
                    "Could not create the sub-ticket. Please try again.",
                )
            )
            return

        # Rename if the actual number differs from the tentative one.
        actual_name = f"ticket-{ticket.ticket_number:04d}"
        if channel.name != actual_name:
            try:
                await channel.edit(name=actual_name)
            except discord.HTTPException:
                logger.warning(
                    "Failed to rename sub-ticket channel %s → %s",
                    channel.id,
                    actual_name,
                )

        await channel.send(content=parent_owner.mention, embed=_build_ticket_embed(ticket))
        await ctx.send(
            embed=success_embed(
                "Sub-ticket Created",
                f"Sub-ticket has been created: {channel.mention}",
            )
        )
        logger.info(
            "Sub-ticket #%d created (parent=%s, guild=%s, author=%s)",
            ticket.ticket_number,
            parent_id,
            guild.id,
            author.id,
        )

    # -- /reopen -------------------------------------------------------

    @commands.hybrid_command(name="reopen")
    @app_commands.describe(
        ticket_ref=(
            "Optional ticket reference: '#0003', '0003', a UUID, or "
            "'ticket:#0003' (the dashboard-guidance form). Omit to reopen "
            "the ticket in the current channel (5-second close window only)."
        ),
    )
    @is_mod()
    async def reopen(self, ctx: commands.Context, *, ticket_ref: str | None = None) -> None:
        """Reopen a closed ticket, creating a new Discord channel.

        With *ticket_ref* the ticket is resolved by guild+number (``#0003`` /
        ``0003`` / ``ticket:#0003``) or by UUID (with a guild-scope check) —
        usable from any channel since the original ticket channel is deleted
        on close. Without *ticket_ref* the legacy channel-scoped lookup is
        preserved for the 5-second window between ``status=closed`` and
        ``channel.delete()``. The service owns the status guard.
        """
        if ctx.guild is None:
            await ctx.send(
                embed=error_embed("Server Only", "Tickets can only be reopened in a server."),
            )
            return

        assert self.bot.db is not None
        assert self.bot.ticket_service is not None
        guild_id = str(ctx.guild.id)

        ticket_row = await self._resolve_ticket_for_reopen(ctx, ticket_ref, guild_id)
        if ticket_row is None:
            return  # _resolve_ticket_for_reopen already sent an error_embed

        ticket_id = ticket_row["id"]
        try:
            await self.bot.ticket_service.reopen_ticket(ticket_id, guild=ctx.guild)
        except ValueError as e:
            # Expected business-rule violation (non-closed, no category
            # configured, ticket not found) — surface the service message
            # verbatim. No logger.exception: this is a handled case, not an
            # unexpected failure.
            await ctx.send(embed=error_embed("Reopen Failed", str(e)))
            return
        except Exception:
            logger.exception("Failed to reopen ticket %s", ticket_id)
            await ctx.send(
                embed=error_embed(
                    "Reopen Failed",
                    "Could not reopen the ticket. Please try again.",
                )
            )
            return

        await ctx.send(
            embed=success_embed(
                "Ticket Reopened",
                "The ticket has been reopened in a new channel.",
            )
        )

    async def _resolve_ticket_for_reopen(
        self,
        ctx: commands.Context,
        ticket_ref: str | None,
        guild_id: str,
    ) -> dict | None:
        """Resolve the ticket row for ``/reopen`` by ref or channel (legacy).

        Returns the ticket row dict on success (caller proceeds to
        :meth:`TicketService.reopen_ticket`) or ``None`` after sending an
        ``error_embed`` for missing/wrong-guild/non-closed refs.

        Resolution order:
            1. *ticket_ref* parses to a number → ``get_ticket_by_number(guild_id, n)``
            2. *ticket_ref* parses to a UUID → ``get_ticket(uuid)`` + guild-scope check
            3. *ticket_ref* is ``None`` (omit) → legacy
               ``get_ticket_by_channel(str(ctx.channel.id))`` for the 5s close window
            4. *ticket_ref* is unparseable → bad-ref ``error_embed``
        """
        assert self.bot.db is not None
        ref = parse_ticket_ref(ticket_ref)

        if ticket_ref is not None and ref is None:
            # Caller supplied an arg we could not parse — surface a clear error.
            await ctx.send(
                embed=error_embed(
                    "Invalid Ticket Reference",
                    f"Could not parse `{ticket_ref}`. Use `#0003`, `0003`, "
                    f"or a UUID (optionally with a `ticket:` prefix).",
                )
            )
            return None

        if ref is not None and ref.number is not None:
            try:
                row = await self.bot.db.get_ticket_by_number(guild_id, ref.number)
            except Exception:
                logger.exception("Failed to look up ticket by number %d", ref.number)
                await ctx.send(
                    embed=error_embed(
                        "Lookup Failed",
                        "Could not look up the ticket. Please try again.",
                    )
                )
                return None
            if row is None:
                await ctx.send(
                    embed=error_embed(
                        "Not Found",
                        f"No ticket #{ref.number} found in this server.",
                    )
                )
                return None
            return row

        if ref is not None and ref.uuid is not None:
            try:
                row = await self.bot.db.get_ticket(ref.uuid)
            except Exception:
                logger.exception("Failed to look up ticket by UUID %s", ref.uuid)
                await ctx.send(
                    embed=error_embed(
                        "Lookup Failed",
                        "Could not look up the ticket. Please try again.",
                    )
                )
                return None
            if row is None:
                await ctx.send(
                    embed=error_embed(
                        "Not Found",
                        f"No ticket found with ID `{ref.uuid}`.",
                    )
                )
                return None
            if row.get("guildId") != guild_id:
                await ctx.send(
                    embed=error_embed(
                        "Wrong Guild",
                        "That ticket belongs to a different server.",
                    )
                )
                return None
            return row

        # ref is None and ticket_ref is None → legacy channel-scoped lookup.
        try:
            ticket_row = await self.bot.db.get_ticket_by_channel(str(ctx.channel.id))
        except Exception:
            logger.exception("Failed to look up ticket by channel %s", ctx.channel.id)
            await ctx.send(
                embed=error_embed(
                    "Lookup Failed",
                    "Could not look up the ticket. Please try again.",
                )
            )
            return None
        if ticket_row is None:
            await ctx.send(
                embed=error_embed(
                    "Not a Ticket",
                    "This command must be used in a ticket channel.",
                )
            )
            return None
        # Caller (``reopen()``) owns the reopen_ticket call + success/failure
        # sends; the resolver only resolves the row.
        return ticket_row

    # -- /transfer -----------------------------------------------------

    @commands.hybrid_command(name="transfer")
    @app_commands.describe(member="The staff member to transfer the ticket to")
    @is_mod()
    async def transfer(self, ctx: commands.Context, member: discord.Member) -> None:
        """Transfer the current ticket's claim to another staff member.

        Mutates ``claimedBy`` and emits a :class:`LoggingService` audit
        embed (no DB audit table — see design.md decision).
        """
        if ctx.guild is None:
            await ctx.send(
                embed=error_embed("Server Only", "Tickets can only be transferred in a server."),
            )
            return

        assert self.bot.db is not None
        assert self.bot.ticket_service is not None
        try:
            ticket_row = await self.bot.db.get_ticket_by_channel(str(ctx.channel.id))
        except Exception:
            logger.exception("Failed to look up ticket by channel %s", ctx.channel.id)
            await ctx.send(
                embed=error_embed(
                    "Lookup Failed",
                    "Could not look up the ticket. Please try again.",
                )
            )
            return
        if ticket_row is None:
            await ctx.send(
                embed=error_embed(
                    "Not a Ticket",
                    "This command must be used in a ticket channel.",
                )
            )
            return

        ticket_id = ticket_row["id"]
        try:
            await self.bot.ticket_service.transfer_ticket(
                ticket_id,
                new_claimed_by=str(member.id),
                actor_id=str(ctx.author.id),
                guild=ctx.guild,
                logging_service=self.bot.logging_service,
            )
        except Exception:
            logger.exception("Failed to transfer ticket %s", ticket_id)
            await ctx.send(
                embed=error_embed(
                    "Transfer Failed",
                    "Could not transfer the ticket. Please try again.",
                )
            )
            return

        await ctx.send(
            embed=success_embed(
                "Ticket Transferred",
                f"The ticket has been transferred to {member.mention}.",
            )
        )

    # -- /note add | list | delete -------------------------------------

    @commands.hybrid_group(name="note", fallback="help")
    @is_mod()
    async def note(self, ctx: commands.Context) -> None:
        """Staff note commands (staff-only).

        With ``fallback="help"`` the group callback is bound as the
        ``help`` subcommand — both ``/note`` and ``/note help`` show this
        message (discord.py requires ``fallback`` for slash groups to be
        directly invokable).
        """
        await ctx.send(
            embed=info_embed(
                "Staff Notes",
                "Use `/note add`, `/note list`, or `/note delete`.",
            )
        )

    @note.command(name="add")
    @app_commands.describe(content="The note text")
    @is_mod()
    async def note_add(self, ctx: commands.Context, content: str) -> None:
        """Add a staff note to the current ticket (not visible to the opener)."""
        assert self.bot.db is not None
        assert self.bot.ticket_service is not None
        try:
            ticket_row = await self.bot.db.get_ticket_by_channel(str(ctx.channel.id))
        except Exception:
            logger.exception("Failed to look up ticket by channel %s", ctx.channel.id)
            await ctx.send(
                embed=error_embed(
                    "Lookup Failed",
                    "Could not look up the ticket. Please try again.",
                )
            )
            return
        if ticket_row is None:
            await ctx.send(
                embed=error_embed(
                    "Not a Ticket",
                    "This command must be used in a ticket channel.",
                )
            )
            return

        ticket_id = ticket_row["id"]
        try:
            note = await self.bot.ticket_service.create_note(ticket_id, str(ctx.author.id), content)
        except Exception:
            logger.exception("Failed to add note to ticket %s", ticket_id)
            await ctx.send(embed=error_embed("Note Failed", "Could not add the note. Please try again."))
            return

        await ctx.send(embed=success_embed("Note Added", f"Note `{note.id}` has been added to the ticket."))

    async def _send_notes_private(self, ctx: commands.Context, embed: discord.Embed) -> None:
        """Route a notes embed privately (B1).

        Slash invocations reply ephemerally. Prefix invocations DM the
        embed to the author and post a confirmation-only embed in the
        channel — the embed content (notes OR the empty-state) MUST NOT
        appear in a non-ephemeral channel message. On DM failure, log and
        send a user-safe error embed without leaking the embed content.
        """
        if ctx.interaction is not None:
            await ctx.send(embed=embed, ephemeral=True)
            return
        try:
            await ctx.author.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("Failed to DM staff notes to %s", ctx.author.id)
            await ctx.send(
                embed=error_embed(
                    "DM Failed",
                    "Could not send the notes to your DMs. Please enable DMs from server members.",
                )
            )
            return
        await ctx.send(
            embed=success_embed(
                "Notes Sent",
                "Staff notes were sent to your DMs.",
            )
        )

    @note.command(name="list")
    @is_mod()
    async def note_list(self, ctx: commands.Context) -> None:
        """List all staff notes on the current ticket (newest-first).

        Privacy (B1): slash replies ephemerally; prefix DMs the notes to
        the author and posts a confirmation-only embed in the channel.
        Note content MUST NOT appear in a non-ephemeral channel message.
        """
        assert self.bot.db is not None
        assert self.bot.ticket_service is not None
        # B4: wrap the channel-ticket lookup so a DB failure does not
        # surface a raw traceback.
        try:
            ticket_row = await self.bot.db.get_ticket_by_channel(str(ctx.channel.id))
        except Exception:
            logger.exception("Failed to look up ticket by channel %s", ctx.channel.id)
            await ctx.send(
                embed=error_embed(
                    "Lookup Failed",
                    "Could not look up the ticket. Please try again.",
                )
            )
            return
        if ticket_row is None:
            await ctx.send(
                embed=error_embed(
                    "Not a Ticket",
                    "This command must be used in a ticket channel.",
                )
            )
            return

        ticket_id = ticket_row["id"]
        # B4: wrap get_notes so a DB failure yields a user-safe error embed.
        try:
            notes = await self.bot.ticket_service.get_notes(ticket_id)
        except Exception:
            logger.exception("Failed to fetch notes for ticket %s", ticket_id)
            await ctx.send(
                embed=error_embed(
                    "Notes Failed",
                    "Could not retrieve the notes. Please try again.",
                )
            )
            return
        if not notes:
            # B1: the empty-state ('ticket has no staff notes') is private
            # state — route it through the same privacy path as the notes
            # themselves so it never leaks to the channel.
            await self._send_notes_private(ctx, info_embed("No Notes", "No staff notes yet."))
            return

        lines = [f"`{n.id}` <@{n.author_id}> — {n.content}" for n in notes]
        embed = discord.Embed(
            title="📋 Staff Notes",
            description="\n".join(lines),
            color=COLOR_INFO,
            timestamp=datetime.now(UTC),
        )
        embed.set_footer(text="NebulosaBot • Tickets")

        # B1: route by invocation type to keep note content private.
        await self._send_notes_private(ctx, embed)

    @note.command(name="delete")
    @app_commands.describe(note_id="The UUID of the note to delete")
    @is_mod()
    async def note_delete(self, ctx: commands.Context, note_id: str) -> None:
        """Delete a staff note (author-only — enforced by the service)."""
        assert self.bot.db is not None
        assert self.bot.ticket_service is not None
        try:
            ticket_row = await self.bot.db.get_ticket_by_channel(str(ctx.channel.id))
        except Exception:
            logger.exception("Failed to look up ticket by channel %s", ctx.channel.id)
            await ctx.send(
                embed=error_embed(
                    "Lookup Failed",
                    "Could not look up the ticket. Please try again.",
                )
            )
            return
        if ticket_row is None:
            await ctx.send(
                embed=error_embed(
                    "Not a Ticket",
                    "This command must be used in a ticket channel.",
                )
            )
            return

        ticket_id = ticket_row["id"]
        try:
            await self.bot.ticket_service.delete_note(
                note_id=note_id,
                author_id=str(ctx.author.id),
                ticket_id=ticket_id,
            )
        except Exception:
            logger.exception("Failed to delete note %s", note_id)
            await ctx.send(embed=error_embed("Delete Failed", "Could not delete the note."))
            return

        await ctx.send(embed=success_embed("Note Deleted", f"Note `{note_id}` has been deleted."))


# ======================================================================
# Cog load / unload (discord.py v2.x requirement)
# ======================================================================


async def setup(bot: NebulosaBot) -> None:
    """Register TicketsCog with the bot."""
    await bot.add_cog(TicketsCog(bot))


async def teardown(bot: NebulosaBot) -> None:
    """Remove TicketsCog from the bot."""
    await bot.remove_cog("Tickets")
