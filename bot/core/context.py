"""NebulosaContext — extended commands.Context with service accessors.

Provides every command handler with direct access to ``db``, ``cache``,
and the guild's ``guild_config`` without manual service lookups.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from bot.core.cache import TTLCache
    from bot.core.database import Database
    from bot.models.guild import GuildConfig


class NebulosaContext(commands.Context):
    """Custom context that exposes the bot's infrastructure services.

    ``guild_config`` is pre-populated by ``NebulosaBot.get_context()``
    for every guild-bound command invocation.  In DMs the property returns
    ``None``.

    Usage inside a cog command::

        async def my_command(self, ctx: NebulosaContext):
            config = ctx.guild_config            # GuildConfig | None
            cached = ctx.cache.get("foo")        # TTLCache shortcut
            await ctx.db.get_guild("123")        # Database shortcut
    """

    # ----------------------------------------------------------------
    # Service accessors (delegate to bot)
    # ----------------------------------------------------------------

    @property
    def db(self) -> Database:
        """The bot's :class:`Database` instance."""
        return self.bot.db  # type: ignore[return-value]

    @property
    def cache(self) -> TTLCache:
        """The bot's :class:`TTLCache` instance."""
        return self.bot.cache  # type: ignore[return-value]

    @property
    def guild_config(self) -> GuildConfig | None:
        """The cached :class:`GuildConfig` for this command's guild.

        ``None`` when the command was invoked in a DM channel.
        The value is pre-fetched by ``NebulosaBot.get_context()``.
        """
        return getattr(self, "_guild_config", None)
