"""LoggingService — centralized audit log embed routing.

Replaces the private ``SentinelCog._log_action()`` with a shared service
consumed by both ``SentinelCog`` and ``AuditListener``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord

from bot.utils.brand import INFO
from bot.utils.embeds import guild_footer_icon

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)

LOG_COLOR = INFO
MAX_FIELD_LENGTH = 1024


def _truncate(text: str, max_len: int = MAX_FIELD_LENGTH) -> str:
    """Truncate *text* to *max_len* characters, appending '…' if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


class LoggingService:
    """Centralized audit log service.

    Resolves ``log_channel_id`` and ``log_enabled`` via ``GuildService``.
    Builds formatted embeds for 9 event types and routes them to the
    configured log channel.  Skips silently when logging is disabled or
    the channel is unavailable.
    """

    __slots__ = ("_bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self._bot = bot

    # ------------------------------------------------------------------
    # Public log methods
    # ------------------------------------------------------------------

    async def log_moderation_action(
        self,
        guild_id: str,
        action: str,
        target: discord.Member | discord.User,
        moderator: discord.Member,
        reason: str,
    ) -> None:
        """Log a moderation action (warn, mute, kick, ban, …).

        Args:
            guild_id: Discord guild snowflake.
            action: Human-readable action name (e.g. ``"Warn"``).
            target: The user or member who received the action.
            moderator: The moderator who performed the action.
            reason: Free-text reason for the action.
        """
        if not await self._should_log(guild_id):
            return

        embed = discord.Embed(
            title=f"🛡️ Moderation: {action}",
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Target", value=f"{target.mention} ({target.name})", inline=True)
        embed.add_field(name="Moderator", value=f"{moderator.mention} ({moderator.name})", inline=True)
        if reason:
            embed.add_field(name="Reason", value=_truncate(reason), inline=False)

        await self._send_log(guild_id, embed)

    async def log_message_edit(
        self,
        guild_id: str,
        before: discord.Message,
        after: discord.Message,
    ) -> None:
        """Log a message edit event.

        Embeds both the original and the updated content.
        Skips if the source channel is invisible to @everyone.
        """
        if not await self._should_log(guild_id):
            return
        if not self.can_log_in_channel(before.channel):
            return

        channel_name = getattr(before.channel, "name", "unknown")
        embed = discord.Embed(
            title=f"📝 Message Edited in #{channel_name}",
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(
            name="Before",
            value=_truncate(before.content or "[No content]"),
            inline=False,
        )
        embed.add_field(
            name="After",
            value=_truncate(after.content or "[No content]"),
            inline=False,
        )
        embed.set_footer(text=f"Message ID: {before.id}")

        await self._send_log(guild_id, embed)

    async def log_message_delete(
        self,
        guild_id: str,
        message: discord.Message,
    ) -> None:
        """Log a message delete event.

        Embeds the deleted message content and its author.
        Skips if the source channel is invisible to @everyone.
        """
        if not await self._should_log(guild_id):
            return
        if not self.can_log_in_channel(message.channel):
            return

        channel_name = getattr(message.channel, "name", "unknown")
        content = message.content or "[No content]"
        embed = discord.Embed(
            title=f"🗑️ Message Deleted in #{channel_name}",
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Author", value=f"{message.author.mention} ({message.author.name})", inline=True)
        embed.add_field(name="Content", value=_truncate(content), inline=False)
        embed.set_footer(text=f"Message ID: {message.id}")

        await self._send_log(guild_id, embed)

    async def log_member_join(
        self,
        guild_id: str,
        member: discord.Member,
    ) -> None:
        """Log a member joining the guild.

        Embeds the member mention, account creation date, and member count.
        """
        if not await self._should_log(guild_id):
            return

        created = member.created_at.strftime("%Y-%m-%d") if member.created_at else "Unknown"
        member_count = getattr(member.guild, "member_count", 0)
        embed = discord.Embed(
            title=f"📥 {member.mention} joined",
            description=f"Account created: {created}",
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )
        if member_count:
            embed.set_footer(text=f"Member #{member_count}")

        await self._send_log(guild_id, embed)

    async def log_member_leave(
        self,
        guild_id: str,
        member: discord.Member,
    ) -> None:
        """Log a member leaving the guild.

        Embeds the member mention and their role names.
        """
        if not await self._should_log(guild_id):
            return

        role_names = [r.name for r in member.roles if r.name != "@everyone"]
        roles_text = ", ".join(f"@{r}" for r in role_names) if role_names else "None"

        embed = discord.Embed(
            title=f"📤 {member.mention} left",
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Roles", value=roles_text, inline=False)

        await self._send_log(guild_id, embed)

    async def log_member_update(
        self,
        guild_id: str,
        before: discord.Member,
        after: discord.Member,
    ) -> None:
        """Log a member update event (e.g. role changes).

        Only logs when roles actually change — no-ops otherwise.
        """
        if not await self._should_log(guild_id):
            return

        before_names = {r.name for r in before.roles if r.name != "@everyone"}
        after_names = {r.name for r in after.roles if r.name != "@everyone"}

        added = after_names - before_names
        removed = before_names - after_names

        if not added and not removed:
            return  # Nothing changed — skip

        embed = discord.Embed(
            title=f"🔄 {after.mention} roles changed",
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )
        if added:
            embed.add_field(name="Added", value=", ".join(f"@{r}" for r in sorted(added)), inline=True)
        if removed:
            embed.add_field(name="Removed", value=", ".join(f"@{r}" for r in sorted(removed)), inline=True)

        await self._send_log(guild_id, embed)

    async def log_channel_create(
        self,
        guild_id: str,
        channel: discord.abc.GuildChannel,
    ) -> None:
        """Log a channel creation event."""
        if not await self._should_log(guild_id):
            return

        embed = discord.Embed(
            title=f"📁 #{channel.name} created",
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )

        await self._send_log(guild_id, embed)

    async def log_channel_delete(
        self,
        guild_id: str,
        channel: discord.abc.GuildChannel,
    ) -> None:
        """Log a channel deletion event."""
        if not await self._should_log(guild_id):
            return

        embed = discord.Embed(
            title=f"📤 #{channel.name} deleted",
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )

        await self._send_log(guild_id, embed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _should_log(self, guild_id: str) -> bool:
        """Return ``True`` if logging is enabled and a log channel is configured."""
        assert self._bot.guild_service is not None, "GuildService initialised in setup_hook"
        config = await self._bot.guild_service.get_config(guild_id)
        if not config.log_enabled:
            return False
        if not config.log_channel_id:
            return False
        return True

    def can_log_in_channel(self, channel: discord.abc.GuildChannel) -> bool:
        """Return ``True`` if ``@everyone`` can read messages in *channel*.

        Only applies to ``discord.TextChannel`` — non-text channels always
        return ``False``.
        """
        if not isinstance(channel, discord.TextChannel):
            return False

        everyone_overwrites = channel.overwrites_for(channel.guild.default_role)
        if everyone_overwrites.read_messages is False:
            return False

        return True

    async def _send_log(self, guild_id: str, embed: discord.Embed) -> None:
        """Resolve the log channel and send *embed*."""
        assert self._bot.guild_service is not None, "GuildService initialised in setup_hook"
        config = await self._bot.guild_service.get_config(guild_id)
        if not config.log_channel_id:
            return

        # Apply guild icon as footer icon (falls back to bot avatar).
        guild = self._bot.get_guild(int(guild_id))
        embed.set_footer(
            text=embed.footer.text or "",
            icon_url=guild_footer_icon(guild, self._bot),
        )

        log_channel = self._bot.get_channel(int(config.log_channel_id))
        if log_channel is None:
            logger.warning(
                "Log channel %s not found for guild %s — skipping log",
                config.log_channel_id,
                guild_id,
            )
            return

        try:
            await log_channel.send(embed=embed)  # type: ignore[union-attr]  # log channels are text channels in practice
        except discord.HTTPException:
            logger.exception(
                "Failed to send log embed to channel %s (guild=%s)",
                config.log_channel_id,
                guild_id,
            )
