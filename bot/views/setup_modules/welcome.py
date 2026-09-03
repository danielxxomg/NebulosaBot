"""Welcome setup module — parity with legacy /welcome group + preview.

Kind-specific glue over the shared factory in
``bot.views.setup_modules._template_picker`` (jscpd budget extraction).
"""

from __future__ import annotations

import logging
import typing

import discord

from bot.core.i18n import t
from bot.utils.brand import INFO
from bot.utils.checks import can_member  # noqa: F401  # re-export: test patch target
from bot.utils.embeds import error_embed
from bot.views.setup_modules._template_picker import (  # noqa: PLC0415  # facade indirection
    build_template_select,
    handle_preview_flow,
    handle_template_select_flow,
)

_WELCOME_SELECT_CUSTOM_ID = "setup:welcome:select_template"

# Preview forwards the resolved per-kind template via the shared factory:
# greetings.card greeting_title/member_count_text are t()-sourced there.
_PREVIEW_CARD_KEYS = ("greetings.card.welcome_title", "greetings.card.member_count")

logger = logging.getLogger(__name__)


class WelcomeSetupModule:
    """Setup module for welcome — gated by greeting.manage."""

    key = "welcome"
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

    # --- parity helpers (used by tests + editors) -------------------

    async def set_welcome_channel(self, guild_id: str, channel_id: str) -> None:
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
        cfg.welcome_channel_id = channel_id
        await bot.greeting_service.save_config(cfg)

    async def set_welcome_card_enabled(self, guild_id: str, enabled: bool) -> None:
        """Expose orphan column cardEnabled (welcome_card_enabled) for editor."""
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
        cfg.welcome_card_enabled = enabled  # orphan: cardEnabled
        await bot.greeting_service.save_config(cfg)

    async def set_theme_id(self, guild_id: str, theme_id: str | None) -> None:
        """Expose orphan column themeId."""
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
        cfg.theme_id = theme_id  # orphan: themeId
        await bot.greeting_service.save_config(cfg)

    async def set_onboarding_channel_id(self, guild_id: str, channel_id: str | None) -> None:
        """Expose orphan column onboardingChannelId."""
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
        cfg.onboarding_channel_id = channel_id  # orphan: onboardingChannelId
        await bot.greeting_service.save_config(cfg)

    async def set_welcome_template_id(
        self,
        guild_id: str,
        template_id: str | None,
        bot: typing.Any | None = None,
    ) -> None:
        """Persist the per-kind welcome template id (migration 030 column).

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
        cfg.welcome_template_id = template_id  # orphan: welcomeTemplateId
        await bot.greeting_service.save_config(cfg)

    # --- render / components / handle -------------------------------

    def render(self, guild_id: str, bot: typing.Any | None = None) -> discord.Embed:  # noqa: ARG002
        title = t(guild_id, "setup.module.welcome.title")
        desc = t(guild_id, "setup.module.welcome.description")
        return discord.Embed(title=title, description=desc, color=INFO)

    async def render_async(self, guild_id: str, bot: typing.Any | None = None) -> discord.Embed:
        b = bot or self._resolve_bot()
        title = t(guild_id, "setup.module.welcome.title")
        desc = t(guild_id, "setup.module.welcome.description")
        if b is not None and getattr(b, "greeting_service", None) is not None:
            try:
                cfg = await b.greeting_service.get_config(guild_id)
                # Append live state for refresh test
                not_cfg = t(guild_id, "setup.module.welcome.not_configured")
                channel_display = f"<#{cfg.welcome_channel_id}>" if cfg.welcome_channel_id else not_cfg
                enabled_display = "✅" if cfg.welcome_enabled else "❌"
                # orphan columns visible in refresh
                card_display = "✅" if getattr(cfg, "welcome_card_enabled", False) else "❌"
                theme_display = getattr(cfg, "theme_id", None) or t(guild_id, "setup.module.welcome.theme_not_set")
                onboarding_display = (
                    f"<#{cfg.onboarding_channel_id}>"
                    if getattr(cfg, "onboarding_channel_id", None)
                    else t(guild_id, "setup.module.welcome.not_configured")
                )
                resolved = cfg.welcome_template_id or cfg.theme_id or "default"
                template_display = t(guild_id, f"templates.greeting.{resolved}.label")
                if template_display == f"templates.greeting.{resolved}.label":
                    template_display = resolved
                desc = (
                    f"{desc}\n\n"
                    f"**{t(guild_id, 'setup.module.welcome.channel_label')}:** {channel_display}\n"
                    f"**{t(guild_id, 'setup.module.welcome.enabled_label')}:** {enabled_display}\n"
                    f"**{t(guild_id, 'setup.module.welcome.card_enabled_label')}:** {card_display}\n"
                    f"**{t(guild_id, 'setup.module.welcome.theme_label')}:** {theme_display}\n"
                    f"**{t(guild_id, 'setup.module.welcome.template_label')}:** {template_display}\n"
                    f"**{t(guild_id, 'setup.module.welcome.onboarding_label')}:** {onboarding_display}"
                )
            except Exception:  # noqa: BLE001
                logger.debug("Welcome render_async failed", exc_info=True)
        return discord.Embed(title=title, description=desc, color=INFO)

    def components(self, guild_id: str, bot: typing.Any | None = None) -> list[discord.ui.Item]:  # noqa: ARG002
        select = build_template_select(guild_id, "welcome")
        select.callback = self._on_template_select  # type: ignore[method-assign]
        return [
            discord.ui.Button(
                label=t(guild_id, "setup.module.welcome.channel_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:welcome:set_channel",
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.welcome.toggle_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:welcome:toggle",
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.welcome.message_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:welcome:set_message",
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.welcome.card_toggle_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:welcome:card_toggle",
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.welcome.theme_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:welcome:set_theme",
            ),
            select,
            discord.ui.Button(
                label=t(guild_id, "setup.module.welcome.onboarding_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:welcome:set_onboarding",
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.welcome.test_button"),
                style=discord.ButtonStyle.primary,
                custom_id="setup:welcome:test",
            ),
        ]

    async def handle(self, interaction: discord.Interaction, action: str) -> None:
        guild = interaction.guild
        if guild is None:
            error_embed(
                t(None, "setup.module.welcome.error_guild_only_title"),
                t(None, "setup.module.welcome.error_guild_only_description"),
            )
            return
        guild_id = str(guild.id)
        bot = self._resolve_bot(interaction)
        if bot is None or getattr(bot, "greeting_service", None) is None:
            error_embed(
                t(guild_id, "setup.module.welcome.error_title"),
                t(guild_id, "setup.module.welcome.error_bot_unavailable"),
            )
            return

        if action == "test":
            await self._handle_test(interaction)
            return
        if action == "select_template":
            await self._handle_template_select(interaction)
            return
        if action in ("set_channel", "toggle", "set_message", "card_toggle", "set_theme", "set_onboarding"):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title=t(guild_id, "setup.module.welcome.editor_title"),
                    description=t(guild_id, "setup.module.welcome.editor_description"),
                    color=INFO,
                ),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=error_embed(
                t(guild_id, "setup.module.welcome.error_title"),
                t(guild_id, "setup.module.welcome.unknown_action", action=action),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )

    async def _on_template_select(self, interaction: discord.Interaction) -> None:
        """Select callback — dispatches to the module handler (persistent reroute path)."""
        await self.handle(interaction, "select_template")

    async def _handle_template_select(self, interaction: discord.Interaction) -> None:
        """Persist the picked template (greeting.manage gated) and refresh the panel."""
        await handle_template_select_flow(
            self,
            interaction,
            "welcome",
            persist=self.set_welcome_template_id,
        )

    async def _handle_test(self, interaction: discord.Interaction) -> None:
        await handle_preview_flow(self, interaction, "welcome")
