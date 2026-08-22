"""TicketsCog — thin facade over 4 flow modules (S3.4A).

Each flow module owns one group; TicketsCog delegates via composition and
preserves hybrid command registration, ``async def setup(bot)``, listeners,
background tasks, and ``is_mod`` guards.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.cogs.ticket_admin_flow import TicketAdminFlow
from bot.cogs.ticket_integrity_flow import TicketIntegrityFlow
from bot.cogs.ticket_lifecycle_flow import TicketLifecycleFlow
from bot.cogs.ticket_notes_flow import TicketNotesFlow
from bot.core.context import NebulosaContext
from bot.core.i18n import t
from bot.models.ticket import Ticket
from bot.utils.brand import SUCCESS, WARNING
from bot.utils.checks import can_check, is_admin, is_mod_member
from bot.utils.embeds import build_ticket_embed, info_embed
from bot.views.confirmation import ConfirmCancelView
from bot.views.tickets import (
    TicketActionsView,
    TicketIntakeModal,
    TicketPanelView,
    _CategorySelect,
    _CategorySelectView,
    deploy_ticket_panel,  # noqa: F401 — re-export for patch("bot.cogs.tickets.deploy_ticket_panel")
)

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)
AUTO_CLOSE_HOURS = 48

# Backward-compat alias — tests import _build_ticket_embed from cog.
_build_ticket_embed = build_ticket_embed

__all__ = [
    "AUTO_CLOSE_HOURS",
    "TicketActionsView",
    "TicketAdminFlow",
    "TicketIntakeModal",
    "TicketIntegrityFlow",
    "TicketLifecycleFlow",
    "TicketNotesFlow",
    "TicketPanelView",
    "TicketsCog",
    "_CategorySelect",
    "_CategorySelectView",
    "_build_ticket_embed",
    "build_ticket_embed",
    "setup",
    "teardown",
]


class TicketsCog(commands.Cog, name="Tickets"):
    """Ticket system commands, views, and background tasks (facade)."""

    __slots__ = ("_admin_flow", "_integrity_flow", "_lifecycle_flow", "_notes_flow", "bot")

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot
        self._admin_flow = TicketAdminFlow(bot)
        self._lifecycle_flow = TicketLifecycleFlow(bot)
        self._notes_flow = TicketNotesFlow(bot)
        self._integrity_flow = TicketIntegrityFlow(bot)

    async def cog_load(self) -> None:
        logger.info("TicketsCog loading — syncing channel cache ...")
        await self._sync_channel_cache()
        if not self.auto_close_stale_tickets.is_running():
            self.auto_close_stale_tickets.start()
            logger.info("Auto-close task started (interval: %d h)", AUTO_CLOSE_HOURS)
        if not self.integrity_sweep_loop.is_running():
            self.integrity_sweep_loop.start()
            logger.info("Integrity sweep task started (periodic)")
        if not self.scheduled_close_loop.is_running():
            try:
                from bot.config import TICKET_TIMER_ENABLED

                timer_enabled = TICKET_TIMER_ENABLED
            except ImportError:
                timer_enabled = True
            if timer_enabled:
                self.scheduled_close_loop.start()
                logger.info("Scheduled-close loop started (interval: 60s)")

    @tasks.loop(seconds=60)
    async def scheduled_close_loop(self) -> None:
        logger.info("Scheduled-close loop: checking due tickets ...")
        if self.bot.ticket_service is None or self.bot.db is None:
            return
        for guild in self.bot.guilds:
            gid = str(guild.id)
            try:
                candidates = await self.bot.ticket_service.get_due_scheduled_tickets(gid, batch_size=50)
            except Exception:
                logger.exception("Failed to query scheduled-close candidates for guild %s", gid)
                continue
            for row in candidates:
                try:
                    await self._close_due_scheduled_ticket(gid, row)
                except Exception:
                    logger.exception("Failed to close scheduled ticket %s", row.get("id"))

    async def _close_due_scheduled_ticket(self, gid: str, row: dict) -> None:
        """Close one due scheduled-close candidate (thin: resolve channel, delegate).

        The service owns fetching the full ticket row, the status state-machine,
        and clearing stale scheduled fields; the cog only resolves the Discord
        channel (a Discord-API concern unavailable to the service layer).
        """
        db = self.bot.db
        ticket_service = self.bot.ticket_service
        if db is None or ticket_service is None:
            return
        ticket_id = row.get("id")
        channel_id = row.get("channelId")
        if not ticket_id or not channel_id:
            return
        channel = self.bot.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            logger.warning("Scheduled ticket %s channel %s not found — skipping", ticket_id, channel_id)
            return
        # Fetch full ticket row for close_ticket_full (service owns this too,
        # but close_ticket_full takes a Ticket — cog builds it from the row).
        full_row = await db.get_ticket(ticket_id, guild_id=gid)
        if full_row is None:
            return
        ticket = Ticket.from_db_row(full_row)
        if ticket.status not in ("open", "claimed"):
            # Already closed: clear stale scheduled fields (service owns this write).
            # Round 2: log failures instead of contextlib.suppress(Exception).
            try:
                await db.update_ticket(ticket_id, guild_id=gid, scheduledCloseAt=None, scheduledCloseBy=None)
            except Exception:
                logger.error("scheduled-close clear failed for ticket %s", ticket_id, exc_info=True)
            return
        await ticket_service.close_ticket_full(channel, ticket, "auto:scheduled", bot=self.bot, manual=False)

    @scheduled_close_loop.before_loop
    async def _before_scheduled_close(self) -> None:
        await self.bot.wait_until_ready()

    async def cog_unload(self) -> None:
        if self.auto_close_stale_tickets.is_running():
            self.auto_close_stale_tickets.cancel()
            logger.info("Auto-close task cancelled")
        if self.integrity_sweep_loop.is_running():
            self.integrity_sweep_loop.cancel()
            logger.info("Integrity sweep task cancelled")
        if self.scheduled_close_loop.is_running():
            self.scheduled_close_loop.cancel()
            logger.info("Scheduled-close loop cancelled")

    async def _sync_channel_cache(self) -> None:
        all_ids: set[int] = set()
        if self.bot.db is None:
            msg = "db not initialised"
            raise RuntimeError(msg)
        for guild in self.bot.guilds:
            try:
                for cid in await self.bot.db.get_open_ticket_channel_ids(str(guild.id)):
                    with contextlib.suppress(ValueError, TypeError):
                        all_ids.add(int(cid))
            except Exception:
                logger.exception("Failed to load ticket channel IDs for guild %s", guild.id)
        if self.bot.ticket_service is None:
            msg = "ticket_service not initialised"
            raise RuntimeError(msg)
        self.bot.ticket_service.sync_channel_cache(all_ids)
        logger.info("Ticket channel cache synced: %d active channels", len(all_ids))

    @tasks.loop(hours=1)
    async def auto_close_stale_tickets(self) -> None:
        logger.info("Auto-close task: checking for stale tickets ...")
        closed = 0
        if self.bot.guild_service is None:
            msg = "guild_service not initialised"
            raise RuntimeError(msg)
        if self.bot.ticket_service is None:
            msg = "ticket_service not initialised"
            raise RuntimeError(msg)
        for guild in self.bot.guilds:
            gid = str(guild.id)
            try:
                stale = await self.bot.ticket_service.get_stale_tickets(gid, hours=AUTO_CLOSE_HOURS)
            except Exception:
                logger.exception("Failed to query stale tickets for guild %s", gid)
                continue
            for ticket in stale:
                try:
                    channel = self.bot.get_channel(int(ticket.channel_id))
                    if not isinstance(channel, discord.TextChannel):
                        logger.warning("Ticket %s channel %s not found — skipping", ticket.id, ticket.channel_id)
                        continue
                    await self.bot.ticket_service.close_ticket_full(channel, ticket, "auto", bot=self.bot, manual=False)
                    closed += 1
                except Exception:
                    logger.exception("Failed to auto-close stale ticket %s", ticket.id)
        if closed:
            logger.info("Auto-close task: closed %d stale ticket(s)", closed)
        else:
            logger.debug("Auto-close task: no stale tickets found")

    @auto_close_stale_tickets.before_loop
    async def _before_auto_close(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def integrity_sweep_loop(self) -> None:
        logger.info("Integrity sweep task: checking active ticket channels ...")
        if self.bot.ticket_service is None:
            msg = "ticket_service not initialised"
            raise RuntimeError(msg)
        for guild in self.bot.guilds:
            gid = str(guild.id)
            try:
                await self.bot.ticket_service.sweep_integrity(gid, self.bot)
            except Exception:
                logger.exception("Integrity sweep failed for guild %s", gid)

    @integrity_sweep_loop.before_loop
    async def _before_integrity_sweep(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # Thin facade: validate (bot/DM/ticket channel) + update lastActivity +
        # mod gate, then delegate the timer state-machine to ticket_service.
        if message.author.bot or message.guild is None:
            return
        ts = getattr(self.bot, "ticket_service", None)
        if ts is None or not ts.is_ticket_channel(message.channel.id):
            return
        if self.bot.db is None:
            logger.error("db not initialised in TicketsCog.on_message — skipping message")
            return
        gid = str(message.guild.id)
        # Always update lastActivity first
        try:
            now = datetime.now(UTC).isoformat()
            await self.bot.db.update_ticket_last_activity(gid, str(message.channel.id), now)
        except Exception:
            logger.exception("Failed to update lastActivity for channel %s", message.channel.id)
        content = (message.content or "").strip()
        if not content.startswith(","):
            return
        # mod gate (member-based; no Interaction available in on_message)
        author = message.author
        if not isinstance(author, discord.Member) or not is_mod_member(author, self.bot, message.guild.id):
            return
        ticket_row = await self._fetch_active_ticket_row(message.channel.id, gid)
        if ticket_row is None:
            return
        ticket_id = ticket_row.get("id")
        if not ticket_id:
            return
        await self._dispatch_timer_message(ts, message, gid, ticket_id, ticket_row, content, author)

    async def _fetch_active_ticket_row(self, channel_id: int, gid: str) -> dict | None:
        """Fetch the active ticket row for *channel_id* (guild-scoped).

        Tries the guild-scoped path first, then the channel-only fallback.
        Returns the row dict or ``None`` when no active ticket is found.
        """
        db = self.bot.db
        if db is None:
            return None
        try:
            ticket_row = await db.get_ticket_by_channel(str(channel_id), guild_id=gid)
        except Exception:
            logger.exception("Failed to fetch ticket row for channel %s", channel_id)
            return None
        if ticket_row is None:
            try:
                ticket_row = await db.get_active_ticket_by_channel(gid, str(channel_id))
            except Exception:
                logger.warning(
                    "active-ticket fallback lookup failed for channel %s (guild %s)",
                    channel_id,
                    gid,
                    exc_info=True,
                )
                ticket_row = None
        if ticket_row is None:
            return None
        if ticket_row.get("status", "") not in ("open", "claimed"):
            return None
        return ticket_row

    async def _dispatch_timer_message(
        self,
        ts: Any,
        message: discord.Message,
        gid: str,
        ticket_id: str,
        ticket_row: dict,
        content: str,
        author: discord.Member,
    ) -> None:
        """Delegate the parsed timer message to the service and route the result."""
        try:
            result = await ts.handle_timer_message(gid, ticket_row, content, str(author.id))
        except Exception:
            logger.exception("Timer on_message handler failed for channel %s", message.channel.id)
            return
        if result is None:
            return  # ,hola etc: silent ignore, no error embed
        if result.action == "cancelled":
            await self._send_cancel_confirmation(message.channel, gid, ticket_id)
        elif result.action == "scheduled":
            if not result.schedule_failed:
                try:
                    await ts.upsert_timer_embed(message.channel, gid, ticket_id, result.due_ts, result.seconds)
                except Exception:
                    logger.exception("Failed to upsert timer embed for ticket %s", ticket_id)
        elif result.action == "needs_confirmation":
            await self._show_timer_confirm_view(
                message, gid, ticket_id, result.seconds, result.prompt_title, result.prompt_desc
            )

    async def _send_cancel_confirmation(self, channel: discord.abc.Messageable, gid: str, ticket_id: str) -> None:
        """Post the localized timer-cancelled confirmation embed."""
        try:
            title = t(gid, "tickets.timer.cancel_title")
            if title.startswith("tickets.timer"):
                title = "Timer Cancelled"
            desc = t(gid, "tickets.timer.cancel_description")
            if desc.startswith("tickets.timer"):
                desc = "Scheduled close cancelled."
            await channel.send(embed=info_embed(title, desc, guild_id=gid))
        except Exception:
            logger.exception("Failed to send cancel confirmation for ticket %s", ticket_id)

    async def _show_timer_confirm_view(
        self,
        message: discord.Message,
        gid: str,
        ticket_id: str,
        seconds: int,
        prompt_title: str,
        prompt_desc: str,
    ) -> None:
        """Show the :class:`ConfirmCancelView` for an out-of-threshold duration.

        The service owns parsing, thresholding, and (on confirm) scheduling +
        embed upsert. The cog only owns the ephemeral view + the success embed
        edit (Discord-API concerns unavailable to the service layer).
        """
        ts = self.bot.ticket_service
        if ts is None:
            return
        try:
            owner_id = message.author.id

            async def _on_confirm(interaction: discord.Interaction) -> None:
                try:
                    res = await ts.confirm_timer_schedule(gid, ticket_id, seconds, str(owner_id))
                except Exception:
                    logger.exception("Failed to schedule close on confirm for ticket %s", ticket_id)
                    return
                if not res.schedule_failed:
                    try:
                        await ts.upsert_timer_embed(message.channel, gid, ticket_id, res.due_ts, res.seconds)  # type: ignore[arg-type]
                    except Exception:
                        logger.exception("Failed to upsert timer embed on confirm for ticket %s", ticket_id)
                title = t(gid, "tickets.timer.confirm_success_title")
                if title.startswith("tickets.timer"):
                    title = "Timer Set"
                desc = t(gid, "tickets.timer.confirm_success_description")
                if desc.startswith("tickets.timer"):
                    desc = "Scheduled close set."
                with contextlib.suppress(Exception):
                    await interaction.response.edit_message(
                        embed=discord.Embed(title=title, description=desc, color=discord.Color(SUCCESS)),
                        view=None,
                    )

            view = ConfirmCancelView(guild_id=gid, owner_id=owner_id, on_confirm=_on_confirm, timeout=30)
            await message.channel.send(
                embed=discord.Embed(title=prompt_title, description=prompt_desc, color=discord.Color(WARNING)),
                view=view,
            )
        except Exception:
            logger.exception("Failed to show timer confirm view for ticket %s", ticket_id)

    # -- Admin (panel / category / fields) — delegates to TicketAdminFlow --

    @commands.hybrid_command(
        name="ticket_panel",
        description=app_commands.locale_str(
            "Desplegar el panel de tickets en el canal actual.",
            key="slash.descriptions.ticket_panel",
        ),
    )
    @app_commands.describe(
        title=app_commands.locale_str(
            "Título opcional para el embed del panel",
            key="slash.describes.ticket_panel.title",
        ),
        description_text=app_commands.locale_str(
            "Descripción opcional para el embed del panel",
            key="slash.describes.ticket_panel.description_text",
        ),
    )
    @app_commands.default_permissions(administrator=True)
    @can_check("tickets.manage")
    async def ticket_panel(
        self,
        ctx: NebulosaContext,
        *,
        title: str | None = None,
        description_text: str | None = None,
    ) -> None:
        await self._admin_flow.ticket_panel(ctx, title=title, description_text=description_text)

    @commands.hybrid_command(
        name="create_category",
        description=app_commands.locale_str(
            "Crear una nueva categoría de tickets.",
            key="slash.descriptions.create_category",
        ),
    )
    @app_commands.describe(
        name=app_commands.locale_str("Nombre de la categoría", key="slash.describes.create_category.name"),
        emoji=app_commands.locale_str("Emoji opcional", key="slash.describes.create_category.emoji"),
        description=app_commands.locale_str("Descripción opcional", key="slash.describes.create_category.description"),
        position=app_commands.locale_str("Orden de visualización", key="slash.describes.create_category.position"),
    )
    @app_commands.default_permissions(administrator=True)
    @can_check("tickets.manage")
    async def create_category(
        self,
        ctx: NebulosaContext,
        name: str,
        emoji: str | None = None,
        description: str | None = None,
        position: int | None = None,
    ) -> None:
        await self._admin_flow.create_category(ctx, name, emoji=emoji, description=description, position=position)

    @commands.hybrid_command(
        name="list_categories",
        description=app_commands.locale_str(
            "Listar todas las categorías de tickets activas.",
            key="slash.descriptions.list_categories",
        ),
    )
    @app_commands.default_permissions(administrator=True)
    @can_check("tickets.manage")
    async def list_categories(self, ctx: NebulosaContext) -> None:
        await self._admin_flow.list_categories(ctx)

    @commands.hybrid_command(
        name="delete_category",
        description=app_commands.locale_str(
            "Eliminar una categoría de tickets por ID.",
            key="slash.descriptions.delete_category",
        ),
    )
    @app_commands.describe(
        category_id=app_commands.locale_str(
            "El UUID de la categoría a eliminar",
            key="slash.describes.delete_category.category_id",
        )
    )
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def delete_category(self, ctx: NebulosaContext, category_id: str) -> None:
        await self._admin_flow.delete_category(ctx, category_id)

    @commands.hybrid_group(
        name="configure_fields",
        fallback="help",
        description=app_commands.locale_str(
            "Configurar campos de entrada personalizados para una categoría de tickets.",
            key="slash.descriptions.configure_fields._",
        ),
    )
    @app_commands.default_permissions(administrator=True)
    @can_check("tickets.manage")
    async def configure_fields(self, ctx: NebulosaContext) -> None:
        await self._admin_flow.configure_fields(ctx)

    @configure_fields.command(
        name="set",
        description=app_commands.locale_str(
            "Definir campos para una categoría de tickets.",
            key="slash.descriptions.configure_fields.set",
        ),
    )
    @app_commands.describe(
        category_id=app_commands.locale_str(
            "El UUID de la categoría de tickets",
            key="slash.describes.configure_fields.set.category_id",
        ),
        fields_json=app_commands.locale_str(
            'Array JSON de definiciones de campos, ej. \'[{"key":"player_nick","label":"Nickname del jugador"}]\'',
            key="slash.describes.configure_fields.set.fields_json",
        ),
    )
    @app_commands.default_permissions(administrator=True)
    @can_check("tickets.manage")
    async def configure_fields_set(
        self,
        ctx: NebulosaContext,
        category_id: str,
        fields_json: str,
    ) -> None:
        await self._admin_flow.configure_fields_set(ctx, category_id, fields_json)

    # -- Lifecycle (subticket / reopen / transfer / unclaim) --

    @commands.hybrid_group(
        name="subticket",
        fallback="help",
        description=app_commands.locale_str(
            "Gestionar sub-tickets vinculados a un ticket padre.",
            key="slash.descriptions.subticket._",
        ),
    )
    @can_check("tickets.manage")
    async def subticket(self, ctx: NebulosaContext) -> None:
        await self._lifecycle_flow.subticket(ctx)

    @subticket.command(
        name="create",
        description=app_commands.locale_str(
            "Crear un sub-ticket vinculado a un ticket padre.",
            key="slash.descriptions.subticket.create",
        ),
    )
    @app_commands.describe(
        parent_id=app_commands.locale_str(
            "El UUID del ticket padre (omitido: usa el canal actual)",
            key="slash.describes.subticket.create.parent_id",
        )
    )
    @can_check("tickets.manage")
    async def subticket_create(self, ctx: NebulosaContext, parent_id: str | None = None) -> None:
        # guild_id=gid — parent lookup is guild-scoped (568 + flow does guild_id=gid)
        await self._lifecycle_flow.subticket_create(ctx, parent_id=parent_id)

    @commands.hybrid_command(
        name="reopen",
        description=app_commands.locale_str(
            "Reabrir un ticket cerrado.",
            key="slash.descriptions.reopen",
        ),
    )
    @app_commands.describe(
        ticket_ref=app_commands.locale_str(
            "Referencia opcional del ticket: '#0003', '0003', un UUID, o 'ticket:#0003'",
            key="slash.describes.reopen.ticket_ref",
        )
    )
    @can_check("tickets.manage")
    async def reopen(self, ctx: NebulosaContext, *, ticket_ref: str | None = None) -> None:
        await self._lifecycle_flow.reopen(ctx, ticket_ref=ticket_ref)

    @commands.hybrid_command(
        name="transfer",
        description=app_commands.locale_str(
            "Transferir un ticket a otro miembro del staff.",
            key="slash.descriptions.transfer",
        ),
    )
    @app_commands.describe(
        member=app_commands.locale_str(
            "El miembro del staff al que transferir el ticket",
            key="slash.describes.transfer.member",
        )
    )
    @can_check("tickets.manage")
    async def transfer(self, ctx: NebulosaContext, member: discord.Member) -> None:
        # guild_id=gid — transfer lookup is guild-scoped (685 + flow does guild_id=gid)
        await self._lifecycle_flow.transfer(ctx, member)

    @commands.hybrid_command(
        name="unclaim",
        description=app_commands.locale_str(
            "Liberar un ticket reclamado de vuelta a estado abierto.",
            key="slash.descriptions.unclaim",
        ),
    )
    async def unclaim(self, ctx: NebulosaContext) -> None:
        # guild_id=gid — unclaim lookup is guild-scoped (722 path via get_ticket_by_channel guild_id=gid)
        await self._lifecycle_flow.unclaim(ctx)

    # -- Notes (add / list / delete) --

    @commands.hybrid_group(
        name="note",
        fallback="help",
        description=app_commands.locale_str(
            "Gestionar notas del staff en tickets.",
            key="slash.descriptions.note._",
        ),
    )
    @can_check("tickets.manage")
    async def note(self, ctx: NebulosaContext) -> None:
        await self._notes_flow.note(ctx)

    @note.command(
        name="add",
        description=app_commands.locale_str(
            "Agregar una nota del staff al ticket actual.",
            key="slash.descriptions.note.add",
        ),
    )
    @app_commands.describe(
        content=app_commands.locale_str(
            "El texto de la nota",
            key="slash.describes.note.add.content",
        )
    )
    @can_check("tickets.manage")
    async def note_add(self, ctx: NebulosaContext, content: str) -> None:
        await self._notes_flow.note_add(ctx, content=content)

    @note.command(
        name="list",
        description=app_commands.locale_str(
            "Listar todas las notas del staff en el ticket actual.",
            key="slash.descriptions.note.list",
        ),
    )
    @can_check("tickets.manage")
    async def note_list(self, ctx: NebulosaContext) -> None:
        await self._notes_flow.note_list(ctx)

    @note.command(
        name="delete",
        description=app_commands.locale_str(
            "Eliminar una nota del staff del ticket actual.",
            key="slash.descriptions.note.delete",
        ),
    )
    @app_commands.describe(
        note_id=app_commands.locale_str(
            "El UUID de la nota a eliminar",
            key="slash.describes.note.delete.note_id",
        )
    )
    @can_check("tickets.manage")
    async def note_delete(self, ctx: NebulosaContext, note_id: str) -> None:
        await self._notes_flow.note_delete(ctx, note_id=note_id)

    # -- Integrity (sweep / repair) --

    @commands.hybrid_command(
        name="sweep_integrity",
        description=app_commands.locale_str(
            "Verificar canales de tickets activos y cerrar los que ya no existen.",
            key="slash.descriptions.sweep_integrity",
        ),
    )
    @can_check("tickets.manage")
    async def sweep_integrity(self, ctx: NebulosaContext) -> None:
        await self._integrity_flow.sweep_integrity(ctx)

    @commands.hybrid_command(
        name="repair_ticket",
        description=app_commands.locale_str(
            "Reparar un ticket cuyo canal fue eliminado (requiere corroboración).",
            key="slash.descriptions.repair_ticket",
        ),
    )
    @app_commands.describe(
        ticket_ref=app_commands.locale_str(
            "Referencia del ticket: '#0003', '0003', un UUID, o 'ticket:#0003'",
            key="slash.describes.repair_ticket.ticket_ref",
        ),
    )
    @can_check("tickets.manage")
    async def repair_ticket(self, ctx: NebulosaContext, *, ticket_ref: str) -> None:
        await self._integrity_flow.repair_ticket(ctx, ticket_ref=ticket_ref)


async def setup(bot: NebulosaBot) -> None:
    await bot.add_cog(TicketsCog(bot))


async def teardown(bot: NebulosaBot) -> None:
    await bot.remove_cog("Tickets")
