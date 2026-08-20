"""Ticket admin flow — panel/category CRUD/fields (S3.4A).

Thin extraction behind :class:`TicketsCog` facade. Keeps guild-scoped DB
access and ``is_mod``-gated admin commands.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord

from bot.core.i18n import t
from bot.models.ticket_category import TicketCategory
from bot.services.ticket_field_service import validate_field_definitions
from bot.utils.brand import INFO
from bot.utils.embeds import cog_err as _err
from bot.utils.embeds import cog_info as _info
from bot.utils.embeds import cog_ok as _ok

if TYPE_CHECKING:
    from bot.bot import NebulosaBot
    from bot.core.context import NebulosaContext

logger = logging.getLogger("bot.cogs.tickets")


class TicketAdminFlow:
    """Administration/category flow — panel deployment, category CRUD, field config."""

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot

    async def ticket_panel(
        self,
        ctx: NebulosaContext,
        *,
        title: str | None = None,
        description_text: str | None = None,
    ) -> None:
        if ctx.guild is None:
            await ctx.send(embed=_err(None, "tickets.panel.server_only"), ephemeral=True)
            return
        gid = str(ctx.guild.id)
        try:
            # lazily import so patch("bot.cogs.tickets.deploy_ticket_panel") still works
            import bot.cogs.tickets as _tickets_mod
            from bot.views.tickets import deploy_ticket_panel as _real_deploy

            _deploy = getattr(_tickets_mod, "deploy_ticket_panel", _real_deploy)
            await _deploy(
                ctx.channel,
                gid,
                bot=self.bot,
                guild=ctx.guild,
                title=title,
                description_text=description_text,
            )
        except discord.Forbidden:
            await ctx.send(embed=_err(gid, "tickets.panel.permission_denied"), ephemeral=True)
            return
        except Exception:
            logger.exception("Failed to deploy ticket panel for guild %s", ctx.guild.id)
            await ctx.send(embed=_err(gid, "tickets.panel.deploy_error"), ephemeral=True)
            return
        await ctx.send(embed=_ok(gid, "tickets.panel.success"), ephemeral=True)

    async def create_category(
        self,
        ctx: NebulosaContext,
        name: str,
        emoji: str | None = None,
        description: str | None = None,
        position: int | None = None,
    ) -> None:
        if ctx.guild is None:
            return
        if self.bot.db is None:
            msg = "db not initialised"
            raise RuntimeError(msg)
        gid = str(ctx.guild.id)
        try:
            existing = await self.bot.db.get_ticket_categories(gid)
            if any(c.get("name", "").lower() == name.lower() for c in existing):
                await ctx.send(embed=_err(gid, "tickets.create.duplicate", name=name), ephemeral=True)
                return
            if position is None:
                position = max((c.get("position", 0) for c in existing), default=0) + 1
        except Exception:
            logger.exception("Failed to check for duplicate category name")
            await ctx.send(embed=_err(gid, "tickets.create.check_failed"), ephemeral=True)
            return
        try:
            row = await self.bot.db.insert_ticket_category(
                guild_id=gid, name=name, emoji=emoji, description=description, position=position
            )
            cat = TicketCategory.from_db_row(row)
        except Exception:
            logger.exception("Failed to create ticket category")
            await ctx.send(embed=_err(gid, "tickets.create.failed"), ephemeral=True)
            return
        await ctx.send(embed=_ok(gid, "tickets.create.success", name=cat.name, id=cat.id), ephemeral=True)

    async def list_categories(self, ctx: NebulosaContext) -> None:
        if ctx.guild is None:
            return
        if self.bot.db is None:
            msg = "db not initialised"
            raise RuntimeError(msg)
        gid = str(ctx.guild.id)
        try:
            rows = await self.bot.db.get_ticket_categories(gid)
            cats = [TicketCategory.from_db_row(r) for r in rows if r.get("active", True)]
        except Exception:
            logger.exception("Failed to fetch ticket categories")
            await ctx.send(embed=_err(gid, "tickets.list.failed"), ephemeral=True)
            return
        if not cats:
            await ctx.send(embed=_info(gid, "tickets.list.empty"), ephemeral=True)
            return
        lines: list[str] = []
        for c in cats:
            e = f"{c.emoji} " if c.emoji else ""
            d = f" \u2014 {c.description}" if c.description else ""
            lines.append(
                f"{e}**{c.name}**{d}\n\u3000\u2192 "
                f"{t(gid, 'tickets.list.id_label')}: `{c.id}`"
                f" \u00b7 {t(gid, 'tickets.list.position_label')}: {c.position}"
            )
        embed = discord.Embed(
            title=t(gid, "tickets.list.title"),
            description="\n".join(lines),
            color=INFO,
            timestamp=datetime.now(UTC),
        )
        embed.set_footer(text=t(gid, "tickets.open.footer"))
        await ctx.send(embed=embed, ephemeral=True)

    async def delete_category(self, ctx: NebulosaContext, category_id: str) -> None:
        if ctx.guild is None:
            return
        if self.bot.db is None:
            msg = "db not initialised"
            raise RuntimeError(msg)
        gid = str(ctx.guild.id)
        try:
            row = await self.bot.db.get_ticket_category(category_id, guild_id=gid)
        except Exception:
            logger.exception("Failed to fetch ticket category %s", category_id)
            await ctx.send(embed=_err(gid, "tickets.delete.failed"), ephemeral=True)
            return
        if row is None:
            await ctx.send(embed=_err(gid, "tickets.delete.not_found", id=category_id), ephemeral=True)
            return
        if row.get("guildId") != gid:
            await ctx.send(embed=_err(gid, "tickets.delete.wrong_guild"), ephemeral=True)
            return
        cat_name = row.get("name", category_id)
        try:
            open_count = await self.bot.db.count_open_tickets_by_category(gid, category_id)
        except Exception:
            logger.exception("Failed to count open tickets for category %s", category_id)
            await ctx.send(embed=_err(gid, "tickets.delete.failed"), ephemeral=True)
            return
        if open_count > 0:
            await ctx.send(embed=_err(gid, "tickets.delete.in_use", name=cat_name, count=open_count), ephemeral=True)
            return
        try:
            await self.bot.db.delete_ticket_category(category_id, guild_id=gid)
        except Exception:
            logger.exception("Failed to delete ticket category %s", category_id)
            await ctx.send(embed=_err(gid, "tickets.delete.failed"), ephemeral=True)
            return
        await ctx.send(embed=_ok(gid, "tickets.delete.success", name=cat_name), ephemeral=True)

    async def configure_fields(self, ctx: NebulosaContext) -> None:
        gid = str(ctx.guild.id) if ctx.guild else None
        await ctx.send(embed=_info(gid, "tickets.configure_fields.help"), ephemeral=True)

    async def configure_fields_set(
        self,
        ctx: NebulosaContext,
        category_id: str,
        fields_json: str,
    ) -> None:
        if ctx.guild is None:
            await ctx.send(embed=_err(None, "tickets.configure_fields.server_only"), ephemeral=True)
            return
        gid = str(ctx.guild.id)
        try:
            raw = json.loads(fields_json)
        except (json.JSONDecodeError, ValueError) as exc:
            await ctx.send(
                embed=_err(gid, "tickets.configure_fields.invalid_json", error=str(exc)),
                ephemeral=True,
            )
            return
        try:
            normalized = validate_field_definitions(raw)
        except ValueError as exc:
            await ctx.send(
                embed=_err(gid, "tickets.configure_fields.validation_error", error=str(exc)),
                ephemeral=True,
            )
            return
        if self.bot.db is None:
            msg = "db not initialised"
            raise RuntimeError(msg)
        try:
            row = await self.bot.db.get_ticket_category(category_id, guild_id=gid)
        except Exception:
            logger.exception("Failed to fetch ticket category %s", category_id)
            await ctx.send(embed=_err(gid, "tickets.configure_fields.failed"), ephemeral=True)
            return
        if row is None:
            await ctx.send(
                embed=_err(gid, "tickets.configure_fields.not_found", id=category_id),
                ephemeral=True,
            )
            return
        if row.get("guildId") != gid:
            await ctx.send(embed=_err(gid, "tickets.configure_fields.wrong_guild"), ephemeral=True)
            return
        try:
            await self.bot.db.update_ticket_category_field_definitions(
                category_id=category_id,
                guild_id=gid,
                field_definitions=normalized,
            )
        except Exception:
            logger.exception("Failed to update field_definitions for category %s", category_id)
            await ctx.send(embed=_err(gid, "tickets.configure_fields.failed"), ephemeral=True)
            return
        cat_name = row.get("name", category_id)
        if normalized:
            await ctx.send(
                embed=_ok(gid, "tickets.configure_fields.success", name=cat_name, count=len(normalized)),
                ephemeral=True,
            )
        else:
            await ctx.send(
                embed=_ok(gid, "tickets.configure_fields.success_cleared", name=cat_name),
                ephemeral=True,
            )
