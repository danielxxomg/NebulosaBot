"""Goodbye setup module — parity with legacy /goodbye group + preview."""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import typing

import discord

from bot.core.i18n import t
from bot.services.greeting_renderer import TEMPLATE_REGISTRY
from bot.services.greeting_service import _resolve_avatar_url  # noqa: PLC0415  # DRY: single definition
from bot.utils.brand import INFO
from bot.utils.checks import can_member
from bot.utils.embeds import error_embed, success_embed

logger = logging.getLogger(__name__)

_GOODBYE_SELECT_CUSTOM_ID = "setup:goodbye:select_template"


def _resolve_guild_icon_url(guild: discord.Guild | None) -> str | None:
    if guild is None:
        return None
    try:
        icon = guild.icon
        return str(icon.url) if icon is not None else None
    except Exception:  # noqa: BLE001
        return None


def _format_template(template: str, user: typing.Any, guild: discord.Guild | None = None) -> str:
    try:
        guild_name = guild.name if guild is not None else ""
        mention = getattr(user, "mention", "")
        return template.format(mention=mention, user=mention, server=guild_name)
    except Exception:  # noqa: BLE001
        return template


def _build_template_select(guild_id: str) -> discord.ui.Select:
    """Persistent StringSelect offering the four registry templates via t()."""
    select = discord.ui.Select(
        custom_id=_GOODBYE_SELECT_CUSTOM_ID,
        placeholder=t(guild_id, "setup.module.goodbye.template_placeholder"),
        min_values=1,
        max_values=1,
    )
    for template_id in TEMPLATE_REGISTRY:
        select.add_option(
            label=t(guild_id, f"templates.greeting.{template_id}.label"),
            description=t(guild_id, f"templates.greeting.{template_id}.description"),
            value=template_id,
        )
    return select


class _TemplateRefreshView(discord.ui.View):
    """Ephemeral one-item view that re-renders the picker after a selection.

    Carries the rebound template select so the panel message keeps its
    controls after ``edit_message`` (never ``view=None``). Not persistent —
    restart routing uses the panel's static custom_ids instead.
    """

    def __init__(self, select: discord.ui.Select) -> None:
        super().__init__(timeout=180)
        self.add_item(select)


class GoodbyeSetupModule:
    """Setup module for goodbye — gated by greeting.manage."""

    key = "goodbye"
    permission_key = "greeting.manage"

    def __init__(self, bot: typing.Any | None = None) -> None:
        self._bot = bot

    def _resolve_bot(self, interaction: discord.Interaction | None = None) -> typing.Any | None:
        if self._bot is not None:
            return self._bot
        if interaction is not None:
            return getattr(interaction, "client", None)
        try:
            from bot.views.setup_panel import _get_setup_bot  # noqa: PLC0415 -- cycle-breaking circular import

            return _get_setup_bot()
        except Exception:  # noqa: BLE001
            return None

    async def set_goodbye_channel(self, guild_id: str, channel_id: str) -> None:
        bot = self._resolve_bot()
        if bot is None:
            try:
                from bot.views.setup_panel import _get_setup_bot  # noqa: PLC0415 -- cycle-breaking circular import

                bot = _get_setup_bot()
            except Exception:  # noqa: BLE001
                bot = None
        if bot is None or getattr(bot, "greeting_service", None) is None:
            msg = "GreetingService unavailable"
            raise RuntimeError(msg)
        cfg = await bot.greeting_service.get_config(guild_id)
        cfg.goodbye_channel_id = channel_id
        await bot.greeting_service.save_config(cfg)

    async def set_goodbye_template_id(
        self,
        guild_id: str,
        template_id: str | None,
        bot: typing.Any | None = None,
    ) -> None:
        """Persist the per-kind goodbye template id (migration 030 column).

        ``bot`` may be passed by callers that already resolved it from the
        interaction (panel-routed selects run on the MODULES singleton,
        which holds no bot reference).
        """
        bot = bot or self._resolve_bot()
        if bot is None:
            try:
                from bot.views.setup_panel import _get_setup_bot  # noqa: PLC0415 -- cycle-breaking circular import

                bot = _get_setup_bot()
            except Exception:  # noqa: BLE001
                bot = None
        if bot is None or getattr(bot, "greeting_service", None) is None:
            msg = "GreetingService unavailable"
            raise RuntimeError(msg)
        cfg = await bot.greeting_service.get_config(guild_id)
        cfg.goodbye_template_id = template_id  # orphan: goodbyeTemplateId
        await bot.greeting_service.save_config(cfg)

    def render(self, guild_id: str, bot: typing.Any | None = None) -> discord.Embed:  # noqa: ARG002
        title = t(guild_id, "setup.module.goodbye.title")
        desc = t(guild_id, "setup.module.goodbye.description")
        return discord.Embed(title=title, description=desc, color=INFO)

    async def render_async(self, guild_id: str, bot: typing.Any | None = None) -> discord.Embed:
        b = bot or self._resolve_bot()
        title = t(guild_id, "setup.module.goodbye.title")
        desc = t(guild_id, "setup.module.goodbye.description")
        if b is not None and getattr(b, "greeting_service", None) is not None:
            try:
                cfg = await b.greeting_service.get_config(guild_id)
                not_cfg = t(guild_id, "setup.module.goodbye.not_configured")
                channel_display = f"<#{cfg.goodbye_channel_id}>" if cfg.goodbye_channel_id else not_cfg
                enabled_display = "✅" if cfg.goodbye_enabled else "❌"
                card_display = "✅" if getattr(cfg, "goodbye_card_enabled", False) else "❌"
                resolved = cfg.goodbye_template_id or cfg.theme_id or "default"
                template_display = t(guild_id, f"templates.greeting.{resolved}.label")
                if template_display == f"templates.greeting.{resolved}.label":
                    template_display = resolved
                desc = (
                    f"{desc}\n\n"
                    f"**{t(guild_id, 'setup.module.goodbye.channel_label')}:** {channel_display}\n"
                    f"**{t(guild_id, 'setup.module.goodbye.enabled_label')}:** {enabled_display}\n"
                    f"**{t(guild_id, 'setup.module.goodbye.card_enabled_label')}:** {card_display}\n"
                    f"**{t(guild_id, 'setup.module.goodbye.template_label')}:** {template_display}"
                )
            except Exception:  # noqa: BLE001
                logger.debug("Goodbye render_async failed", exc_info=True)
        return discord.Embed(title=title, description=desc, color=INFO)

    def components(self, guild_id: str, bot: typing.Any | None = None) -> list[discord.ui.Item]:  # noqa: ARG002
        select = _build_template_select(guild_id)
        select.callback = self._on_template_select  # type: ignore[method-assign]
        return [
            discord.ui.Button(
                label=t(guild_id, "setup.module.goodbye.channel_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:goodbye:set_channel",
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.goodbye.toggle_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:goodbye:toggle",
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.goodbye.message_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:goodbye:set_message",
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.goodbye.card_toggle_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:goodbye:card_toggle",
            ),
            select,
            discord.ui.Button(
                label=t(guild_id, "setup.module.goodbye.test_button"),
                style=discord.ButtonStyle.primary,
                custom_id="setup:goodbye:test",
            ),
        ]

    async def handle(self, interaction: discord.Interaction, action: str) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    t(None, "setup.module.goodbye.error_guild_only_title"),
                    t(None, "setup.module.goodbye.error_guild_only_description"),
                ),
                ephemeral=True,
            )
            return
        guild_id = str(guild.id)
        bot = self._resolve_bot(interaction)
        if bot is None or getattr(bot, "greeting_service", None) is None:
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "setup.module.goodbye.error_title"),
                    t(guild_id, "setup.module.goodbye.error_bot_unavailable"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        if action == "test":
            await self._handle_test(interaction)
            return
        if action == "select_template":
            await self._handle_template_select(interaction)
            return
        if action in ("set_channel", "toggle", "set_message", "card_toggle"):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title=t(guild_id, "setup.module.goodbye.editor_title"),
                    description=t(guild_id, "setup.module.goodbye.editor_description"),
                    color=INFO,
                ),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=error_embed(
                t(guild_id, "setup.module.goodbye.error_title"),
                t(guild_id, "setup.module.goodbye.unknown_action", action=action),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )

    async def _on_template_select(self, interaction: discord.Interaction) -> None:
        """Select callback — dispatches to the module handler (persistent reroute path)."""
        await self.handle(interaction, "select_template")

    async def _handle_template_select(self, interaction: discord.Interaction) -> None:
        """Persist the picked template (greeting.manage gated) and refresh the panel."""
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    t(None, "setup.module.goodbye.error_guild_only_title"),
                    t(None, "setup.module.goodbye.error_guild_only_description"),
                ),
                ephemeral=True,
            )
            return
        guild_id = str(guild.id)
        bot = self._resolve_bot(interaction)
        if bot is None or getattr(bot, "greeting_service", None) is None:
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "setup.module.goodbye.error_title"),
                    t(guild_id, "setup.module.goodbye.error_bot_unavailable"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        # Permission gate: greeting.manage only (no new matrix key).
        user = interaction.user
        if not getattr(getattr(user, "guild_permissions", None), "administrator", False):
            try:
                allowed = await can_member("greeting.manage", user, guild_id)
            except Exception:  # noqa: BLE001
                allowed = False
            if not allowed:
                await interaction.response.send_message(
                    embed=error_embed(
                        t(guild_id, "setup.panel.error_denied_title"),
                        t(guild_id, "setup.panel.error_denied_description"),
                        guild_id=guild_id,
                    ),
                    ephemeral=True,
                )
                return
        # Read the picked value (interaction payload first, then select state).
        template_id: str | None = None
        try:
            data = getattr(interaction, "data", None)
            if isinstance(data, dict):
                vals = data.get("values") or []
                if vals:
                    template_id = str(vals[0])
        except Exception:  # noqa: BLE001
            template_id = None
        if template_id is None:
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "setup.module.goodbye.error_title"),
                    t(guild_id, "setup.module.goodbye.unknown_action", action="select_template"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        await self.set_goodbye_template_id(guild_id, template_id, bot=bot)
        embed = await self.render_async(guild_id, bot=bot)
        # Re-render the picker with the current label; never pass view=None —
        # discord.py serializes it as components: [] and strips every control
        # from the panel message (verify-report CRITICAL #1 probe 2).
        select = _build_template_select(guild_id)
        select.callback = self._on_template_select  # type: ignore[method-assign]
        await interaction.response.edit_message(embed=embed, view=_TemplateRefreshView(select))
        await interaction.followup.send(
            embed=success_embed(
                t(guild_id, "setup.module.goodbye.template_select_title"),
                t(guild_id, "setup.module.goodbye.template_select_description"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )

    async def _handle_test(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(
                embed=error_embed(
                    t(None, "setup.module.goodbye.preview_error_title"),
                    t(None, "setup.module.goodbye.preview_error_description"),
                ),
                ephemeral=True,
            )
            return
        guild_id = str(guild.id)
        bot = self._resolve_bot(interaction)
        if bot is None:
            await interaction.followup.send(
                embed=error_embed(
                    t(None, "setup.module.goodbye.preview_error_title"),
                    t(None, "setup.module.goodbye.preview_error_description"),
                ),
                ephemeral=True,
            )
            return

        with contextlib.suppress(Exception):  # noqa: BLE001
            await interaction.response.defer(ephemeral=True)
        try:
            cfg = await bot.greeting_service.get_config(guild_id)
        except Exception:  # noqa: BLE001
            logger.exception("Goodbye preview get_config failed")
            await interaction.followup.send(
                embed=error_embed(
                    t(guild_id, "setup.module.goodbye.preview_error_title"),
                    t(guild_id, "setup.module.goodbye.preview_error_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        channel_id = getattr(cfg, "goodbye_channel_id", None)
        if not channel_id:
            await interaction.followup.send(
                embed=error_embed(
                    t(guild_id, "setup.module.goodbye.preview_no_channel_title"),
                    t(guild_id, "setup.module.goodbye.preview_no_channel_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        try:
            channel = guild.get_channel(int(channel_id))
        except Exception:  # noqa: BLE001
            channel = None
        if channel is None:
            await interaction.followup.send(
                embed=error_embed(
                    t(guild_id, "setup.module.goodbye.preview_no_channel_title"),
                    t(guild_id, "setup.module.goodbye.preview_no_channel_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        try:
            render_fn = bot.greeting_service.resolve_renderer()
        except Exception:  # noqa: BLE001
            logger.exception("Goodbye preview resolve_renderer failed")
            await interaction.followup.send(
                embed=error_embed(
                    t(guild_id, "setup.module.goodbye.preview_error_title"),
                    t(guild_id, "setup.module.goodbye.preview_error_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        user = interaction.user
        member_count = getattr(guild, "member_count", 0) or 0
        greeting_title = t(guild_id, "greetings.card.goodbye_title")
        member_count_text = t(guild_id, "greetings.card.member_count", count=member_count)
        avatar_url = _resolve_avatar_url(user)
        guild_icon_url = _resolve_guild_icon_url(guild)
        # S3 preview: forward the resolved per-kind template (fallback chain) to the renderer.
        try:
            from bot.services.greeting_service import select_template  # noqa: PLC0415 -- cycle-break

            resolved = select_template(cfg, "goodbye")
        except Exception:  # noqa: BLE001
            resolved = getattr(cfg, "goodbye_template_id", None) or getattr(cfg, "theme_id", None) or "default"
        try:
            buffer: io.BytesIO = await asyncio.to_thread(
                render_fn,
                username=getattr(user, "display_name", str(user)),
                avatar_url=avatar_url,
                guild_name=getattr(guild, "name", ""),
                member_count=member_count,
                guild_icon_url=guild_icon_url,
                greeting_title=greeting_title,
                member_count_text=member_count_text,
                card_type="goodbye",
                template_id=resolved,
                # theme_id receives the SAME resolved id (legacy alias per
                # setup-panel spec: preview forwards template_id=resolved,
                # theme_id=resolved — never the raw config value).
                theme_id=resolved,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Goodbye preview render failed")
            await interaction.followup.send(
                embed=error_embed(
                    t(guild_id, "setup.module.goodbye.preview_error_title"),
                    t(guild_id, "setup.module.goodbye.preview_error_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        content: str | None = None
        try:
            tmpl = getattr(cfg, "goodbye_message", None)
            if tmpl:
                content = _format_template(tmpl, user, guild)
        except Exception:  # noqa: BLE001
            content = None
        try:
            # Goodbye also respects card_enabled toggle per spec
            if getattr(cfg, "goodbye_card_enabled", False):
                file = discord.File(buffer, filename="goodbye.png")
                await channel.send(content=content or None, file=file)  # type: ignore[union-attr]
            else:
                if content and content.strip():
                    await channel.send(content=content)  # type: ignore[union-attr]
                else:
                    await channel.send(content=content or None)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            logger.exception("Goodbye preview channel send failed")
            await interaction.followup.send(
                embed=error_embed(
                    t(guild_id, "setup.module.goodbye.preview_error_title"),
                    t(guild_id, "setup.module.goodbye.preview_error_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            embed=success_embed(
                t(guild_id, "setup.module.goodbye.preview_success_title"),
                t(guild_id, "setup.module.goodbye.preview_success_description", channel=f"<#{channel_id}>"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )
