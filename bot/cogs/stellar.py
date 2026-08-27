"""StellarCog — economy commands: daily, coins, leaderboard, rank.

Provides pure app commands for the guild economy system:
  - /daily — claim daily coins with streak tracking
  - /coins [member] — check coin balance (self or target)
  - /leaderboard <xp|coins> — top-10 leaderboard embed
  - /rank [member] — generate and send a rank card image

NOTE: Slash command descriptions use locale_str with Spanish default
messages (Discord UI metadata); the LocaleTranslator resolves them to the
user's client language via the locale JSON files. Runtime responses are
localized through t().
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import RANK_COOLDOWN_SECONDS
from bot.core.context import NebulosaContext  # noqa: F401 -- DRY guard expects presence
from bot.core.i18n import t
from bot.utils.brand import INFO
from bot.utils.embeds import (
    error_embed,
    info_embed,
    success_embed,
    warning_embed,
)

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)


class StellarCog(commands.Cog, name="Stellar"):
    """Economy and level system commands.

    All commands are pure app (slash) — see bot-core slash-only spec.  Business logic is delegated
    to :class:`~bot.services.economy_service.EconomyService`.
    """

    __slots__ = ("bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot = bot

    def _to_ctx(self, src: object):  # type: ignore[no-untyped-def]
        from bot.cogs._slash_compat import is_context_like as _is_ctx  # noqa: PLC0415 -- cycle-breaking: compat shim avoids circular import  # isort: skip

        if _is_ctx(src):
            return src
        from bot.cogs._slash_compat import InteractionContext as _InteractionContext  # noqa: PLC0415 -- cycle-breaking: compat shim avoids circular import  # isort: skip

        return _InteractionContext(src, self.bot)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # /daily
    # ------------------------------------------------------------------

    @app_commands.command(
        name="daily",
        description=app_commands.locale_str(
            "Reclamar tu recompensa diaria de monedas.",
            key="slash.descriptions.daily",
        ),
    )
    async def daily(self, interaction: discord.Interaction) -> None:
        """Claim the daily coin reward with streak tracking."""
        ctx = self._to_ctx(interaction)
        guild_id = str(ctx.guild.id) if ctx.guild else ""  # type: ignore[union-attr]
        user_id = str(ctx.author.id)  # type: ignore[union-attr]

        if self.bot.economy_service is None:
            msg = "EconomyService initialised in setup_hook"
            raise RuntimeError(msg)
        try:
            success, coins_awarded, streak, remaining_seconds = await self.bot.economy_service.claim_daily(
                guild_id, user_id
            )
        except Exception:
            logger.exception("Daily claim failed for user %s", user_id)
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "stellar.daily.failed_title"),
                    t(guild_id, "stellar.daily.failed_description"),
                ),
            )
            return

        if success:
            plural = "s" if streak != 1 else ""
            embed = success_embed(
                t(guild_id, "stellar.daily.success_title"),
                t(guild_id, "stellar.daily.success_description", coins=coins_awarded, streak=streak, plural=plural),
            )
        else:
            hours, minutes = divmod(remaining_seconds // 60, 60)
            remaining = f"{hours}h {minutes}m"
            embed = warning_embed(
                t(guild_id, "stellar.daily.cooldown_title"),
                t(guild_id, "stellar.daily.cooldown_description", streak=streak, remaining=remaining),
            )

        await ctx.send(embed=embed)

    # ------------------------------------------------------------------
    # /coins
    # ------------------------------------------------------------------

    @app_commands.command(
        name="coins",
        description=app_commands.locale_str(
            "Consultar tu balance de monedas o el de otro.",
            key="slash.descriptions.coins",
        ),
    )
    @app_commands.describe(
        member=app_commands.locale_str(
            "El miembro a consultar (por defecto: tú)",
            key="slash.describes.coins.member",
        )
    )
    async def coins(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        """Show the coin balance for yourself or a target member."""
        ctx = self._to_ctx(interaction)
        guild_id = str(ctx.guild.id) if ctx.guild else ""  # type: ignore[union-attr]
        target = member or ctx.author  # type: ignore[union-attr]
        user_id = str(target.id)

        if self.bot.economy_service is None:
            msg = "EconomyService initialised in setup_hook"
            raise RuntimeError(msg)
        try:
            balance = await self.bot.economy_service.get_balance(guild_id, user_id)
        except Exception:
            logger.exception("Balance query failed for user %s", user_id)
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "stellar.coins.failed_title"),
                    t(guild_id, "stellar.coins.failed_description"),
                ),
            )
            return

        if target == ctx.author:
            description = t(guild_id, "stellar.coins.self_description", balance=balance)
        else:
            description = t(guild_id, "stellar.coins.target_description", name=target.display_name, balance=balance)

        embed = info_embed(t(guild_id, "stellar.coins.balance_title"), description)
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------
    # /leaderboard
    # ------------------------------------------------------------------

    @app_commands.command(
        name="leaderboard",
        description=app_commands.locale_str(
            "Ver la tabla de líderes del servidor por XP o monedas.",
            key="slash.descriptions.leaderboard",
        ),
    )
    @app_commands.describe(
        lb_type=app_commands.locale_str(
            "Tipo de tabla de líderes: 'xp' o 'coins' (por defecto: xp)",
            key="slash.describes.leaderboard.lb_type",
        )
    )
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        lb_type: str = "xp",
    ) -> None:
        """Display the top-10 leaderboard for XP or coins."""
        ctx = self._to_ctx(interaction)
        guild_id = str(ctx.guild.id) if ctx.guild else ""  # type: ignore[union-attr]

        sort_by = lb_type.lower()
        if sort_by not in ("xp", "coins"):
            sort_by = "xp"

        if self.bot.economy_service is None:
            msg = "EconomyService initialised in setup_hook"
            raise RuntimeError(msg)
        try:
            rows = await self.bot.economy_service.get_leaderboard(guild_id, sort_by=sort_by, limit=10, offset=0)
        except Exception:
            logger.exception("Leaderboard query failed for guild %s", guild_id)
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "stellar.leaderboard.error_title"),
                    t(guild_id, "stellar.leaderboard.error_description"),
                ),
            )
            return

        if not rows:
            type_label = "XP" if sort_by == "xp" else "coins"
            embed = error_embed(
                t(guild_id, "stellar.leaderboard.empty_title"),
                t(guild_id, "stellar.leaderboard.empty_description", type=type_label),
            )
            await ctx.send(embed=embed)
            return

        # Build description lines: "#1 <@id> — {value} XP/coins"
        lines: list[str] = []
        emoji_type = "✨" if sort_by == "xp" else "💰"
        for idx, row in enumerate(rows, start=1):
            user_id = row.get("userId", "unknown")
            value = row.get(sort_by, 0)
            trophy = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"#{idx}"
            lines.append(f"{trophy} <@{user_id}> — **{value:,}** {emoji_type}")

        title_key = "stellar.leaderboard.xp_title" if sort_by == "xp" else "stellar.leaderboard.coins_title"
        embed = discord.Embed(
            title=t(guild_id, title_key),
            description="\n".join(lines),
            color=INFO,
        )
        embed.set_footer(text=t(guild_id, "stellar.leaderboard.footer", count=len(rows)))

        await ctx.send(embed=embed)

    # ------------------------------------------------------------------
    # /rank
    # ------------------------------------------------------------------

    @app_commands.command(
        name="rank",
        description=app_commands.locale_str("Ver tu tarjeta de rango o la de otro.", key="slash.descriptions.rank"),
    )
    @app_commands.checks.cooldown(1, RANK_COOLDOWN_SECONDS)
    @app_commands.describe(
        member=app_commands.locale_str(
            "El miembro a consultar (por defecto: tú)",
            key="slash.describes.rank.member",
        )
    )
    async def rank(  # noqa: C901
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        """Generate and send a rank card for yourself or a target member."""
        ctx = self._to_ctx(interaction)
        guild_id = str(ctx.guild.id) if ctx.guild else ""  # type: ignore[union-attr]
        target: discord.Member = member or ctx.author  # type: ignore[assignment,union-attr]
        user_id = str(target.id)

        # Defer — image generation and avatar fetch are I/O-bound.
        await ctx.defer(ephemeral=True)

        if self.bot.economy_service is None:
            msg = "EconomyService initialised in setup_hook"
            raise RuntimeError(msg)
        try:
            rank_info = await self.bot.economy_service.get_rank_info(guild_id, user_id)
        except Exception:
            logger.exception("Rank info query failed for user %s", user_id)
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "stellar.rank.failed_title"),
                    t(guild_id, "stellar.rank.failed_description"),
                ),
                ephemeral=True,
            )
            return

        if rank_info is None:
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "stellar.rank.no_data_title"),
                    t(guild_id, "stellar.rank.no_data_description", name=target.display_name),
                ),
                ephemeral=True,
            )
            return

        # Fetch avatar URL for the rank card.
        # The renderer downloads the avatar itself in-thread, so we only
        # pass the URL — no need to read() bytes here.
        try:
            avatar_url: str | None = str(target.display_avatar.url)
        except Exception:
            avatar_url = None
            logger.debug(
                "Could not resolve avatar URL for user %s — using placeholder",
                user_id,
                exc_info=True,
            )

        # Generate the rank card in a thread to avoid blocking. The bot-wide
        # semaphore (S0.11) caps concurrent renders so bursts queue instead of
        # saturating the thread pool; the renderer is owned by the bot (stored
        # in setup_hook) so the cog uses the shared instance directly.
        if self.bot.rank_renderer is None:
            msg = "RankRenderer initialised in setup_hook"
            raise RuntimeError(msg)
        async with self.bot.rank_render_sem:
            buffer = await asyncio.to_thread(
                self.bot.rank_renderer.generate_rank_card,
                username=target.display_name,
                avatar_url=avatar_url,
                xp=rank_info["xp"],
                level=rank_info["level"],
                rank=rank_info["rank"],
                xp_for_current=rank_info["xp_current"],
                xp_for_next=rank_info["xp_needed"],
                guild_id=guild_id,
            )

        file = discord.File(buffer, filename="rank.png")
        await ctx.send(file=file, ephemeral=True)


async def setup(bot: NebulosaBot) -> None:
    """Load the StellarCog into the bot."""
    await bot.add_cog(StellarCog(bot))


async def teardown(bot: NebulosaBot) -> None:
    """Remove StellarCog from the bot."""
    await bot.remove_cog("Stellar")
