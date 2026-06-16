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
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.models.ticket_category import TicketCategory
from bot.utils.checks import is_mod
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
    async def open_ticket_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Show category selection then create the ticket channel."""
        bot: NebulosaBot = interaction.client  # type: ignore[assignment]
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Server Only", "Tickets can only be opened in a server."
                ),
                ephemeral=True,
            )
            return

        # Fetch active ticket categories for this guild.
        rows = await bot.db.get_ticket_categories(str(guild.id))
        categories = [
            TicketCategory.from_db_row(r) for r in rows if r.get("active", True)
        ]

        if not categories:
            await interaction.response.send_message(
                embed=error_embed(
                    "No Categories",
                    "No ticket categories are configured. "
                    "Ask an admin to set them up with `/create_category`.",
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
        await interaction.response.send_message(
            "Select a ticket category:", view=view, ephemeral=True
        )


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
    async def _get_ticket(
        bot: NebulosaBot, channel_id: int
    ) -> tuple[dict | None, str | None]:
        """Fetch the ticket row (raw dict) and build a user-facing error.

        Returns ``(row, error_message)`` — exactly one is non-None.
        """
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
    async def claim_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Claim the ticket, assigning it to the clicking staff member."""
        bot: NebulosaBot = interaction.client  # type: ignore[assignment]
        channel_id = interaction.channel_id
        if channel_id is None:
            return

        ticket_row, error = await self._get_ticket(bot, channel_id)
        if error is not None:
            await interaction.response.send_message(
                embed=error_embed("Claim Failed", error), ephemeral=True
            )
            return

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

        try:
            ticket = await bot.ticket_service.claim_ticket(ticket_id, staff_id)
        except Exception:
            logger.exception("Failed to claim ticket %s", ticket_id)
            await interaction.response.send_message(
                embed=error_embed(
                    "Claim Failed", "Could not claim the ticket. Please try again."
                ),
                ephemeral=True,
            )
            return

        # Update the embed to show the claimed status.
        embed = _build_ticket_embed(ticket, claimed_by=interaction.user)
        await interaction.response.edit_message(embed=embed, view=self)
        logger.info(
            "Ticket %s claimed by %s in channel %s",
            ticket_id, staff_id, channel_id,
        )

    @discord.ui.button(
        label="Close",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:close",
        emoji="🔒",
    )
    async def close_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Close the ticket: generate transcript, upload, delete channel."""
        bot: NebulosaBot = interaction.client  # type: ignore[assignment]
        channel_id = interaction.channel_id
        guild = interaction.guild
        if channel_id is None or guild is None:
            return

        ticket_row, error = await self._get_ticket(bot, channel_id)
        if error is not None:
            await interaction.response.send_message(
                embed=error_embed("Close Failed", error), ephemeral=True
            )
            return

        ticket_id = ticket_row["id"]
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return

        await interaction.response.defer(ephemeral=True)

        # 1. Generate transcript.
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
                transcript_url = await bot.transcript_service.upload(
                    transcript_file, log_channel
                )
            else:
                logger.warning(
                    "No log channel configured for guild %s — skipping transcript upload",
                    guild.id,
                )
        except Exception:
            logger.exception(
                "Transcript generation/upload failed for ticket %s", ticket_id
            )

        # 2. Close ticket in DB.
        closer_id = str(interaction.user.id)
        try:
            await bot.ticket_service.close_ticket(
                ticket_id, closed_by=closer_id, transcript_url=transcript_url
            )
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
        await channel.send(
            embed=info_embed("Ticket Closed", close_msg)
        )

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

    def __init__(
        self, options: list[discord.SelectOption], guild: discord.Guild
    ) -> None:
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
                embed=error_embed(
                    "Config Error", "Could not load guild configuration."
                ),
                ephemeral=True,
            )
            return

        if not config.ticket_category_id:
            await interaction.followup.send(
                embed=error_embed(
                    "Not Configured",
                    "The ticket category channel has not been configured. "
                    "Ask an admin to set it up.",
                ),
                ephemeral=True,
            )
            return

        ticket_category_channel = guild.get_channel(
            int(config.ticket_category_id)
        )
        if ticket_category_channel is None or not isinstance(
            ticket_category_channel, discord.CategoryChannel
        ):
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
            try:
                mod_role = guild.get_role(int(config.mod_role_id))
            except (ValueError, TypeError):
                pass

        author = interaction.user

        # --- Get tentative ticket number for channel naming. ---
        tentative_max = await bot.db.get_max_ticket_number(str(guild.id))
        tentative_number = tentative_max + 1
        channel_name = f"ticket-{tentative_number:04d}"

        # --- Build permission overwrites. ---
        overwrites: dict[
            discord.Role | discord.Member, discord.PermissionOverwrite
        ] = {
            guild.default_role: discord.PermissionOverwrite(
                read_messages=False
            ),
            author: discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            ),
            guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            ),
        }
        if mod_role is not None:
            overwrites[mod_role] = discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            )

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
            try:
                await channel.delete(reason="Ticket creation failed — cleanup")
            except discord.HTTPException:
                pass
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
                    channel.id, actual_name,
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
            ticket.ticket_number, guild.id, channel.id, author.id,
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
        description = (
            "A staff member has claimed this ticket and will assist you shortly."
        )
        if claimed_by is not None:
            description += f"\n**Claimed by:** {claimed_by.mention}"
    else:
        color = COLOR_SUCCESS
        title = f"🎫 Ticket #{number}"
        description = (
            "Welcome! A staff member will assist you soon.\n"
            "Describe your issue and a moderator will respond."
        )

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc),
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
        for guild in self.bot.guilds:
            try:
                ids = await self.bot.db.get_open_ticket_channel_ids(
                    str(guild.id)
                )
                for cid in ids:
                    try:
                        all_channel_ids.add(int(cid))
                    except (ValueError, TypeError):
                        pass
            except Exception:
                logger.exception(
                    "Failed to load open ticket channel IDs for guild %s",
                    guild.id,
                )
        self.bot.ticket_service.sync_channel_cache(all_channel_ids)
        logger.info(
            "Ticket channel cache synced: %d active channels", len(all_channel_ids)
        )

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
                stale = await self.bot.ticket_service.get_stale_tickets(
                    guild_id, hours=AUTO_CLOSE_HOURS
                )
            except Exception:
                logger.exception(
                    "Failed to query stale tickets for guild %s", guild_id
                )
                continue

            for ticket in stale:
                try:
                    await self._close_one_ticket(
                        ticket, guild, log_channel,
                        reason="Auto-closed due to inactivity (48 h)",
                    )
                    closed_count += 1
                except Exception:
                    logger.exception(
                        "Failed to auto-close stale ticket %s", ticket.id
                    )

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
        channel = self.bot.get_channel(int(ticket.channel_id))
        if channel is None or not isinstance(channel, discord.TextChannel):
            # Channel was deleted externally — just close the DB record.
            await self.bot.ticket_service.close_ticket(ticket.id)
            logger.info(
                "Ticket %s closed (channel %s already deleted)",
                ticket.id, ticket.channel_id,
            )
            return

        # 1. Transcript.
        transcript_url: str | None = None
        try:
            transcript_file = await self.bot.transcript_service.generate(channel)
            if log_channel is not None:
                transcript_url = await self.bot.transcript_service.upload(
                    transcript_file, log_channel
                )
        except Exception:
            logger.exception(
                "Transcript generation failed for stale ticket %s", ticket.id
            )

        # 2. Close in DB.
        await self.bot.ticket_service.close_ticket(
            ticket.id, transcript_url=transcript_url
        )

        # 3. Delete channel silently after delay.
        await asyncio.sleep(CHANNEL_DELETE_DELAY)
        try:
            await channel.delete(reason=reason)
        except discord.HTTPException:
            logger.exception(
                "Failed to delete stale ticket channel %s", channel.id
            )

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

        try:
            await self.bot.db.update_ticket_last_activity(
                str(message.channel.id)
            )
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
            "Click the button below to open a support ticket. "
            "A staff member will assist you shortly."
        ),
    ) -> None:
        """Deploy (or redeploy) the ticket panel in the current channel.

        Stores the message and channel IDs in the guild configuration
        so the panel survives bot restarts.
        """
        if ctx.guild is None:
            await ctx.send(
                embed=error_embed(
                    "Server Only", "The ticket panel can only be deployed in a server."
                )
            )
            return

        # Build the panel embed.
        embed = discord.Embed(
            title=title,
            description=description_text,
            color=COLOR_INFO,
            timestamp=datetime.now(timezone.utc),
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
                ctx.guild.id, message.id, message.channel.id,
            )
        except Exception:
            logger.exception("Failed to persist ticket panel for guild %s", ctx.guild.id)
            await ctx.send(
                embed=error_embed(
                    "Persistence Error",
                    "The panel was sent but the IDs could not be saved. "
                    "It will not survive a bot restart.",
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
                max_pos = max(
                    (cat.get("position", 0) for cat in existing), default=0
                )
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
                f"Ticket category **{category.name}** has been created.\n"
                f"ID: `{category.id}`",
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

        guild_id = str(ctx.guild.id)

        try:
            rows = await self.bot.db.get_ticket_categories(guild_id)
            categories = [
                TicketCategory.from_db_row(r)
                for r in rows
                if r.get("active", True)
            ]
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
                    "No ticket categories have been created yet. "
                    "Use `/create_category` to add one.",
                )
            )
            return

        # Build a clean listing embed.
        lines: list[str] = []
        for cat in categories:
            emoji_str = f"{cat.emoji} " if cat.emoji else ""
            desc_str = f" — {cat.description}" if cat.description else ""
            lines.append(
                f"{emoji_str}**{cat.name}**{desc_str}\n"
                f"　↳ ID: `{cat.id}` · Position: {cat.position}"
            )

        embed = discord.Embed(
            title="📋 Ticket Categories",
            description="\n".join(lines),
            color=COLOR_INFO,
            timestamp=datetime.now(timezone.utc),
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
    async def delete_category(
        self, ctx: commands.Context, category_id: str
    ) -> None:
        """Delete a ticket category by its UUID.

        This is a hard delete — the category is removed from the database.
        """
        if ctx.guild is None:
            return

        # Verify the category exists and belongs to this guild.
        try:
            row = await self.bot.db.get_ticket_category(category_id)
        except Exception:
            logger.exception("Failed to fetch ticket category %s", category_id)
            await ctx.send(
                embed=error_embed(
                    "Query Failed", "Could not verify the category. Please try again."
                )
            )
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
            logger.exception(
                "Failed to count open tickets for category %s", category_id
            )
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
                    f"Cannot delete category **{cat_name}** because it has "
                    f"**{open_count}** open ticket(s).",
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


# ======================================================================
# Cog load / unload (discord.py v2.x requirement)
# ======================================================================


async def setup(bot: NebulosaBot) -> None:
    """Register TicketsCog with the bot."""
    await bot.add_cog(TicketsCog(bot))


async def teardown(bot: NebulosaBot) -> None:
    """Remove TicketsCog from the bot."""
    await bot.remove_cog("Tickets")
