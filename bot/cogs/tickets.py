"""TicketsCog — ticket system commands and auto-close task.

Views moved to ``bot.views.tickets``, embed builder to ``bot.utils.embeds``,
ticket helpers to ``bot.utils.ticket_helpers``. This module keeps only the
cog class, thin command definitions, and the auto-close background task.
"""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.core.i18n import t
from bot.models.ticket_category import TicketCategory
from bot.services.ticket_field_service import validate_field_definitions
from bot.services.ticket_service import TicketCategoryNotConfiguredError
from bot.utils.brand import INFO
from bot.utils.checks import is_mod, is_mod_check
from bot.utils.embeds import build_ticket_embed, error_embed, info_embed, success_embed
from bot.utils.ticket_helpers import resolve_ticket_for_channel, resolve_ticket_for_reopen
from bot.views.tickets import (
    TicketActionsView,
    TicketIntakeModal,
    TicketPanelView,
    _CategorySelect,
    _CategorySelectView,
    deploy_ticket_panel,
)

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)
AUTO_CLOSE_HOURS = 48

# Backward-compat aliases.
_build_ticket_embed = build_ticket_embed
__all__ = [
    "TicketActionsView",
    "TicketIntakeModal",
    "TicketPanelView",
    "TicketsCog",
    "_CategorySelect",
    "_CategorySelectView",
    "_build_ticket_embed",
    "setup",
    "teardown",
]


def _err(gid: str | None, key: str, **kw: object) -> discord.Embed:
    return error_embed(t(gid, f"{key}_title"), t(gid, f"{key}_description", **kw), guild_id=gid)


def _ok(gid: str | None, key: str, **kw: object) -> discord.Embed:
    return success_embed(t(gid, f"{key}_title"), t(gid, f"{key}_description", **kw), guild_id=gid)


def _info(gid: str | None, key: str, **kw: object) -> discord.Embed:
    return info_embed(t(gid, f"{key}_title"), t(gid, f"{key}_description", **kw), guild_id=gid)


class TicketsCog(commands.Cog, name="Tickets"):
    """Ticket system commands, views, and background tasks."""

    __slots__ = ("bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot

    async def cog_load(self) -> None:
        logger.info("TicketsCog loading — syncing channel cache ...")
        await self._sync_channel_cache()
        if not self.auto_close_stale_tickets.is_running():
            self.auto_close_stale_tickets.start()
            logger.info("Auto-close task started (interval: %d h)", AUTO_CLOSE_HOURS)

    async def cog_unload(self) -> None:
        if self.auto_close_stale_tickets.is_running():
            self.auto_close_stale_tickets.cancel()
            logger.info("Auto-close task cancelled")

    async def _sync_channel_cache(self) -> None:
        all_ids: set[int] = set()
        assert self.bot.db is not None
        for guild in self.bot.guilds:
            try:
                for cid in await self.bot.db.get_open_ticket_channel_ids(str(guild.id)):
                    with contextlib.suppress(ValueError, TypeError):
                        all_ids.add(int(cid))
            except Exception:
                logger.exception("Failed to load ticket channel IDs for guild %s", guild.id)
        assert self.bot.ticket_service is not None
        self.bot.ticket_service.sync_channel_cache(all_ids)
        logger.info("Ticket channel cache synced: %d active channels", len(all_ids))

    @tasks.loop(hours=1)
    async def auto_close_stale_tickets(self) -> None:
        logger.info("Auto-close task: checking for stale tickets ...")
        closed = 0
        assert self.bot.guild_service is not None and self.bot.ticket_service is not None
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
                    await self.bot.ticket_service.close_ticket_full(
                        channel, ticket, "auto", bot=self.bot, manual=False
                    )
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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        ts = getattr(self.bot, "ticket_service", None)
        if ts is None or not ts.is_ticket_channel(message.channel.id):
            return
        assert self.bot.db is not None
        try:
            now = datetime.now(UTC).isoformat()
            await self.bot.db.update_ticket_last_activity(
                str(message.guild.id), str(message.channel.id), now
            )
        except Exception:
            logger.exception("Failed to update lastActivity for channel %s", message.channel.id)

    @commands.hybrid_command(name="ticket_panel", description="Deploy the ticket panel to the current channel.")
    @app_commands.describe(
        title="Optional title for the panel embed", description_text="Optional description for the panel embed"
    )
    @app_commands.default_permissions(administrator=True)
    @is_mod()
    async def ticket_panel(
        self,
        ctx: commands.Context,
        *,
        title: str = "Support Tickets",
        description_text: str = (
            "Click the button below to open a support ticket."
            " A staff member will assist you shortly."
        ),
    ) -> None:
        if ctx.guild is None:
            await ctx.send(embed=_err(None, "tickets.panel.server_only"), ephemeral=True)
            return
        gid = str(ctx.guild.id)
        try:
            await deploy_ticket_panel(
                ctx.channel, gid, bot=self.bot, guild=ctx.guild,
                title=title, description_text=description_text,
            )
        except discord.Forbidden:
            await ctx.send(embed=_err(gid, "tickets.panel.permission_denied"), ephemeral=True)
            return
        except Exception:
            logger.exception("Failed to deploy ticket panel for guild %s", ctx.guild.id)
            await ctx.send(embed=_err(gid, "tickets.panel.deploy_error"), ephemeral=True)
            return
        await ctx.send(embed=_ok(gid, "tickets.panel.success"), ephemeral=True)

    @commands.hybrid_command(name="create_category", description="Create a new ticket category.")
    @app_commands.describe(
        name="Category name", emoji="Optional emoji", description="Optional description", position="Display order"
    )
    @app_commands.default_permissions(administrator=True)
    @is_mod()
    async def create_category(
        self,
        ctx: commands.Context,
        name: str,
        emoji: str | None = None,
        description: str | None = None,
        position: int | None = None,
    ) -> None:
        if ctx.guild is None:
            return
        assert self.bot.db is not None
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

    @commands.hybrid_command(name="list_categories", description="List all active ticket categories.")
    @app_commands.default_permissions(administrator=True)
    @is_mod()
    async def list_categories(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            return
        assert self.bot.db is not None
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
        lines = []
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

    @commands.hybrid_command(name="delete_category", description="Delete a ticket category by ID.")
    @app_commands.describe(category_id="The UUID of the category to delete")
    @app_commands.default_permissions(administrator=True)
    @is_mod()
    async def delete_category(self, ctx: commands.Context, category_id: str) -> None:
        if ctx.guild is None:
            return
        assert self.bot.db is not None
        gid = str(ctx.guild.id)
        try:
            row = await self.bot.db.get_ticket_category(category_id)
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
            await self.bot.db.delete_ticket_category(category_id)
        except Exception:
            logger.exception("Failed to delete ticket category %s", category_id)
            await ctx.send(embed=_err(gid, "tickets.delete.failed"), ephemeral=True)
            return
        await ctx.send(embed=_ok(gid, "tickets.delete.success", name=cat_name), ephemeral=True)

    @commands.hybrid_group(
        name="configure_fields",
        fallback="help",
        description="Configure custom intake fields for a ticket category.",
    )
    @app_commands.default_permissions(administrator=True)
    @is_mod()
    async def configure_fields(self, ctx: commands.Context) -> None:
        """Configure custom intake fields for a ticket category."""
        gid = str(ctx.guild.id) if ctx.guild else None
        await ctx.send(embed=_info(gid, "tickets.configure_fields.help"), ephemeral=True)

    @configure_fields.command(name="set", description="Set field definitions for a ticket category.")
    @app_commands.describe(
        category_id="The UUID of the ticket category",
        fields_json='JSON array of field definitions, e.g. \'[{"key":"player_nick","label":"Player Nickname"}]\'',
    )
    @app_commands.default_permissions(administrator=True)
    @is_mod()
    async def configure_fields_set(
        self,
        ctx: commands.Context,
        category_id: str,
        fields_json: str,
    ) -> None:
        """Set field_definitions on a ticket category."""
        if ctx.guild is None:
            await ctx.send(embed=_err(None, "tickets.configure_fields.server_only"), ephemeral=True)
            return

        gid = str(ctx.guild.id)

        # Parse JSON.
        try:
            raw = json.loads(fields_json)
        except (json.JSONDecodeError, ValueError) as exc:
            await ctx.send(
                embed=_err(gid, "tickets.configure_fields.invalid_json", error=str(exc)),
                ephemeral=True,
            )
            return

        # Validate field definitions via pure service.
        try:
            normalized = validate_field_definitions(raw)
        except ValueError as exc:
            await ctx.send(
                embed=_err(gid, "tickets.configure_fields.validation_error", error=str(exc)),
                ephemeral=True,
            )
            return

        # Fetch category and verify guild ownership.
        assert self.bot.db is not None
        try:
            row = await self.bot.db.get_ticket_category(category_id)
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

        # Persist via DB facade.
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

    @commands.hybrid_group(
        name="subticket",
        fallback="help",
        description="Manage sub-tickets linked to a parent ticket.",
    )
    @is_mod()
    async def subticket(self, ctx: commands.Context) -> None:
        gid = str(ctx.guild.id) if ctx.guild else None
        await ctx.send(embed=_info(gid, "tickets.subticket.help"))

    @staticmethod
    async def _resolve_parent_owner(
        guild: discord.Guild, parent_author_id: str, ctx: commands.Context
    ) -> discord.Member | None:
        gid = str(guild.id)
        if not parent_author_id:
            await ctx.send(embed=_err(gid, "tickets.subticket.owner_not_found"))
            return None
        try:
            member = guild.get_member(int(parent_author_id))
            if member is not None:
                return member
            return await guild.fetch_member(int(parent_author_id))
        except (discord.NotFound, discord.HTTPException, ValueError, TypeError):
            logger.exception("Failed to resolve parent ticket owner %s", parent_author_id)
            await ctx.send(embed=_err(gid, "tickets.subticket.owner_not_found_resolve"))
            return None

    @subticket.command(name="create", description="Create a sub-ticket linked to a parent ticket.")
    @app_commands.describe(parent_id="The UUID of the parent ticket (omitted: uses current channel)")
    @is_mod()
    async def subticket_create(self, ctx: commands.Context, parent_id: str | None = None) -> None:
        if ctx.guild is None:
            await ctx.send(embed=_err(None, "tickets.subticket.server_only"))
            return
        guild, author = ctx.guild, ctx.author
        gid = str(guild.id)
        assert (
            isinstance(author, discord.Member)
            and self.bot.db is not None
            and self.bot.guild_service is not None
            and self.bot.ticket_service is not None
        )
        try:
            config = await self.bot.guild_service.get_config(gid)
        except Exception:
            logger.exception("Failed to fetch guild config for sub-ticket (guild=%s)", guild.id)
            await ctx.send(embed=_err(gid, "tickets.open.config_error"))
            return
        if not config.ticket_category_id:
            await ctx.send(
                embed=error_embed(
                    t(gid, "tickets.config_missing.title"), t(gid, "tickets.config_missing.description"), guild_id=gid
                )
            )
            return
        try:
            cat_ch = guild.get_channel(int(config.ticket_category_id))
        except (ValueError, TypeError):
            cat_ch = None
        if not isinstance(cat_ch, discord.CategoryChannel):
            await ctx.send(embed=_err(gid, "tickets.subticket.invalid_category"))
            return
        try:
            parent_row = await (
                self.bot.db.get_ticket_by_channel(str(ctx.channel.id))
                if parent_id is None
                else self.bot.db.get_ticket(parent_id)
            )
        except Exception:
            logger.exception("Failed to look up parent ticket")
            await ctx.send(embed=_err(gid, "tickets.subticket.lookup_failed"))
            return
        if parent_row is None or parent_row.get("status") == "closed":
            await ctx.send(embed=_err(gid, "tickets.subticket.not_ticket"))
            return
        pid = parent_row["id"]
        parent_author_id = parent_row.get("authorId", str(author.id))
        parent_owner: discord.Member | None = (
            author
            if str(author.id) == parent_author_id
            else await self._resolve_parent_owner(guild, parent_author_id, ctx)
        )  # type: ignore[assignment]
        if parent_owner is None:
            return
        mod_role: discord.Role | None = None
        if config.mod_role_id:
            with contextlib.suppress(ValueError, TypeError):
                mod_role = guild.get_role(int(config.mod_role_id))
        # Resolve parent's category name for channel naming.
        sub_cat_name = "ticket"
        parent_cat_id = parent_row.get("categoryId")
        if parent_cat_id:
            try:
                cat_row = await self.bot.db.get_ticket_category(parent_cat_id)
                if cat_row is not None:
                    sub_cat_name = cat_row.get("name", "ticket")
            except Exception:
                logger.warning("Failed to resolve parent category %s for subticket naming", parent_cat_id)
        try:
            channel, subticket = await self.bot.ticket_service.create_ticket_channel(
                guild,
                cat_ch,
                parent_owner,
                guild_id=gid,
                category_name=sub_cat_name,
                parent_id=pid,
                mod_role=mod_role,
            )
        except discord.HTTPException:
            logger.exception("Failed to create sub-ticket channel")
            await ctx.send(embed=_err(gid, "tickets.subticket.channel_failed"))
            return
        except Exception:
            logger.exception("Failed to create sub-ticket in DB (parent=%s)", pid)
            await ctx.send(embed=_err(gid, "tickets.subticket.creation_failed"))
            return
        await channel.send(content=parent_owner.mention, embed=build_ticket_embed(subticket, guild_id=gid))
        await ctx.send(embed=_ok(gid, "tickets.subticket.success", channel=channel.mention))
        logger.info(
            "Sub-ticket #%d created (parent=%s, guild=%s, author=%s)", subticket.ticket_number, pid, guild.id, author.id
        )

    @commands.hybrid_command(name="reopen", description="Reopen a closed ticket.")
    @app_commands.describe(ticket_ref="Optional ticket reference: '#0003', '0003', a UUID, or 'ticket:#0003'")
    @is_mod()
    async def reopen(self, ctx: commands.Context, *, ticket_ref: str | None = None) -> None:
        if ctx.guild is None:
            await ctx.send(embed=_err(None, "tickets.reopen.server_only"))
            return
        assert self.bot.ticket_service is not None
        gid = str(ctx.guild.id)
        row = await resolve_ticket_for_reopen(self.bot, ctx, ticket_ref, gid)
        if row is None:
            return
        tid = row["id"]
        try:
            await self.bot.ticket_service.reopen_ticket(tid, guild=ctx.guild)
        except TicketCategoryNotConfiguredError:
            await ctx.send(
                embed=error_embed(
                    t(gid, "tickets.config_missing.title"), t(gid, "tickets.config_missing.description"), guild_id=gid
                )
            )
            return
        except ValueError:
            await ctx.send(
                embed=error_embed(
                    t(gid, "tickets.reopen.failed_title"),
                    t(gid, "tickets.reopen.not_closed_description", status=row.get("status", "unknown")),
                    guild_id=gid,
                )
            )
            return
        except Exception:
            logger.exception("Failed to reopen ticket %s", tid)
            await ctx.send(embed=_err(gid, "tickets.reopen.failed"))
            return
        await ctx.send(embed=_ok(gid, "tickets.reopen.success"))

    @commands.hybrid_command(name="transfer", description="Transfer a ticket to another staff member.")
    @app_commands.describe(member="The staff member to transfer the ticket to")
    @is_mod()
    async def transfer(self, ctx: commands.Context, member: discord.Member) -> None:
        if ctx.guild is None:
            await ctx.send(embed=_err(None, "tickets.transfer.server_only"))
            return
        gid = str(ctx.guild.id)
        assert self.bot.ticket_service is not None
        assert self.bot.db is not None
        try:
            row = await self.bot.db.get_ticket_by_channel(str(ctx.channel.id))
        except Exception:
            logger.exception("Failed to look up ticket by channel %s", ctx.channel.id)
            await ctx.send(embed=_err(gid, "tickets.transfer.lookup_failed"))
            return
        if row is None:
            await ctx.send(embed=_err(gid, "tickets.transfer.not_ticket"))
            return
        try:
            await self.bot.ticket_service.transfer_ticket(
                row["id"],
                new_claimed_by=str(member.id),
                actor_id=str(ctx.author.id),
                guild=ctx.guild,
                logging_service=self.bot.logging_service,
            )
        except Exception:
            logger.exception("Failed to transfer ticket %s", row["id"])
            await ctx.send(embed=_err(gid, "tickets.transfer.failed"))
            return
        await ctx.send(embed=_ok(gid, "tickets.transfer.success", member=member.mention))

    @commands.hybrid_command(name="unclaim", description="Release a claimed ticket back to open status.")
    async def unclaim(self, ctx: commands.Context) -> None:
        """Unclaim a ticket — available to the claimer or moderators."""
        if ctx.guild is None:
            await ctx.send(embed=_err(None, "tickets.actions.unclaim_not_ticket_title"))
            return
        gid = str(ctx.guild.id)
        assert self.bot.db is not None and self.bot.ticket_service is not None
        try:
            row = await self.bot.db.get_ticket_by_channel(str(ctx.channel.id))
        except Exception:
            logger.exception("Failed to look up ticket by channel %s", ctx.channel.id)
            await ctx.send(
                embed=error_embed(
                    t(gid, "tickets.actions.unclaim_failed_title"),
                    t(gid, "tickets.actions.unclaim_failed_description"),
                    guild_id=gid,
                ),
                ephemeral=True,
            )
            return
        if row is None:
            await ctx.send(
                embed=error_embed(
                    t(gid, "tickets.actions.unclaim_not_ticket_title"),
                    t(gid, "tickets.actions.unclaim_not_ticket_description"),
                    guild_id=gid,
                ),
                ephemeral=True,
            )
            return

        actor_id = str(ctx.author.id)
        # Pre-check: ticket must be claimed to unclaim.
        if not row.get("claimedBy"):
            await ctx.send(
                embed=error_embed(
                    t(gid, "tickets.actions.unclaim_not_claimed_title"),
                    t(gid, "tickets.actions.unclaim_not_claimed_description"),
                    guild_id=gid,
                ),
                ephemeral=True,
            )
            return

        # Resolve actor_is_mod: use shared predicate (single source of truth).
        actor_is_mod = False
        if isinstance(ctx.author, discord.Member):
            # Build a lightweight interaction-like object for is_mod_check,
            # which expects (user, guild, guild_id, client) attributes.
            _interaction = type("_Interaction", (), {
                "user": ctx.author,
                "guild": ctx.guild,
                "guild_id": int(gid),
                "client": self.bot,
            })()
            actor_is_mod = await is_mod_check(_interaction)

        try:
            ticket = await self.bot.ticket_service.unclaim_ticket(row["id"], actor_id, is_mod=actor_is_mod)
        except ValueError as exc:
            reason = str(exc)
            if "not currently claimed" in reason:
                await ctx.send(
                    embed=error_embed(
                        t(gid, "tickets.actions.unclaim_not_claimed_title"),
                        t(gid, "tickets.actions.unclaim_not_claimed_description"),
                        guild_id=gid,
                    ),
                    ephemeral=True,
                )
            else:
                await ctx.send(
                    embed=error_embed(
                        t(gid, "tickets.actions.unclaim_permission_denied_title"),
                        t(gid, "tickets.actions.unclaim_permission_denied_description"),
                        guild_id=gid,
                    ),
                    ephemeral=True,
                )
            return
        except Exception:
            logger.exception("Failed to unclaim ticket %s", row["id"])
            await ctx.send(
                embed=error_embed(
                    t(gid, "tickets.actions.unclaim_failed_title"),
                    t(gid, "tickets.actions.unclaim_failed_description"),
                    guild_id=gid,
                ),
                ephemeral=True,
            )
            return

        # Refresh the embed to show unclaimed status.
        from bot.utils.embeds import build_ticket_embed

        embed = build_ticket_embed(ticket, guild_id=gid, bot=self.bot, guild=ctx.guild)
        # Try to edit the original actions view message to refresh the embed.
        try:
            # Find the pinned welcome message to edit it.
            async for message in ctx.channel.history(limit=10):
                if message.pinned and message.author == ctx.guild.me:
                    await message.edit(embed=embed)
                    break
        except (discord.HTTPException, discord.Forbidden):
            logger.warning("Failed to refresh ticket embed after unclaim in channel %s", ctx.channel.id)

        await ctx.send(embed=_ok(gid, "tickets.actions.unclaim_success"))

    @commands.hybrid_group(name="note", fallback="help", description="Manage staff notes on tickets.")
    @is_mod()
    async def note(self, ctx: commands.Context) -> None:
        gid = str(ctx.guild.id) if ctx.guild else None
        await ctx.send(embed=_info(gid, "tickets.note.help"))

    @note.command(name="add", description="Add a staff note to the current ticket.")
    @app_commands.describe(content="The note text")
    @is_mod()
    async def note_add(self, ctx: commands.Context, content: str) -> None:
        gid = str(ctx.guild.id) if ctx.guild else None
        assert self.bot.ticket_service is not None
        row = await resolve_ticket_for_channel(self.bot, ctx.channel.id, gid, action="note_add")
        if row is None:
            await ctx.send(embed=_err(gid, "tickets.note.add_not_ticket"))
            return
        try:
            note = await self.bot.ticket_service.create_note(row["id"], str(ctx.author.id), content)
        except Exception:
            logger.exception("Failed to add note to ticket %s", row["id"])
            await ctx.send(embed=_err(gid, "tickets.note.add_failed"))
            return
        await ctx.send(embed=_ok(gid, "tickets.note.add_success", id=note.id))

    async def _send_notes_private(self, ctx: commands.Context, embed: discord.Embed) -> None:
        gid = str(ctx.guild.id) if ctx.guild else None
        if ctx.interaction is not None:
            await ctx.send(embed=embed, ephemeral=True)
            return
        try:
            await ctx.author.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("Failed to DM staff notes to %s", ctx.author.id)
            await ctx.send(embed=_err(gid, "tickets.note.list_dm_failed"))
            return
        await ctx.send(embed=_ok(gid, "tickets.note.list_sent"))

    @note.command(name="list", description="List all staff notes on the current ticket.")
    @is_mod()
    async def note_list(self, ctx: commands.Context) -> None:
        gid = str(ctx.guild.id) if ctx.guild else None
        assert self.bot.ticket_service is not None
        row = await resolve_ticket_for_channel(self.bot, ctx.channel.id, gid, action="note_list")
        if row is None:
            await ctx.send(embed=_err(gid, "tickets.note.add_not_ticket"))
            return
        try:
            notes = await self.bot.ticket_service.get_notes(row["id"])
        except Exception:
            logger.exception("Failed to fetch notes for ticket %s", row["id"])
            await ctx.send(embed=_err(gid, "tickets.note.add_failed"))
            return
        if not notes:
            await self._send_notes_private(ctx, _info(gid, "tickets.note.list_no_notes"))
            return
        lines = [f"`{n.id}` <@{n.author_id}> \u2014 {n.content}" for n in notes]
        embed = discord.Embed(
            title=t(gid, "tickets.note.list_title"),
            description="\n".join(lines),
            color=INFO,
            timestamp=datetime.now(UTC),
        )
        embed.set_footer(text=t(gid, "tickets.open.footer"))
        await self._send_notes_private(ctx, embed)

    @note.command(name="delete", description="Delete a staff note from the current ticket.")
    @app_commands.describe(note_id="The UUID of the note to delete")
    @is_mod()
    async def note_delete(self, ctx: commands.Context, note_id: str) -> None:
        gid = str(ctx.guild.id) if ctx.guild else None
        assert self.bot.ticket_service is not None
        row = await resolve_ticket_for_channel(self.bot, ctx.channel.id, gid, action="note_delete")
        if row is None:
            await ctx.send(embed=_err(gid, "tickets.note.delete_not_ticket"))
            return
        try:
            await self.bot.ticket_service.delete_note(
                note_id=note_id, author_id=str(ctx.author.id), ticket_id=row["id"]
            )
        except Exception:
            logger.exception("Failed to delete note %s", note_id)
            await ctx.send(embed=_err(gid, "tickets.note.delete_failed"))
            return
        await ctx.send(embed=_ok(gid, "tickets.note.delete_success", id=note_id))


async def setup(bot: NebulosaBot) -> None:
    await bot.add_cog(TicketsCog(bot))


async def teardown(bot: NebulosaBot) -> None:
    await bot.remove_cog("Tickets")
