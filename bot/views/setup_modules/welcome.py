"""Welcome setup module — parity with legacy /welcome group + preview.

Kind-specific configuration deriving from GreetingSetupModuleBase.
"""

from __future__ import annotations

import logging
import typing

from bot.utils.checks import can_member  # noqa: F401  # re-export: test patch target
from bot.views.setup_modules._greeting_base import GreetingSetupModuleBase
from bot.views.setup_modules._template_picker import (  # noqa: F401  # re-export parity
    build_template_select,
    handle_preview_flow,
    handle_template_select_flow,
)

_WELCOME_SELECT_CUSTOM_ID = "setup:welcome:select_template"

# Preview forwards the resolved per-kind template via the shared factory:
# greetings.card greeting_title/member_count_text are t()-sourced there.
_PREVIEW_CARD_KEYS = ("greetings.card.welcome_title", "greetings.card.member_count")

logger = logging.getLogger(__name__)


class WelcomeSetupModule(GreetingSetupModuleBase):
    """Setup module for welcome — gated by greeting.manage."""

    key = "welcome"
    channel_field = "welcome_channel_id"
    template_field = "welcome_template_id"
    enabled_field = "welcome_enabled"
    card_enabled_field = "welcome_card_enabled"
    editor_actions = (
        "set_channel",
        "toggle",
        "set_message",
        "card_toggle",
        "set_theme",
        "set_onboarding",
    )

    async def set_welcome_channel(self, guild_id: str, channel_id: str) -> None:
        """Persist the welcome channel id."""
        b, _ = self._require_greeting_service()
        await self._save_channel(guild_id, channel_id, b)

    async def set_welcome_card_enabled(self, guild_id: str, enabled: bool) -> None:
        """Expose orphan column cardEnabled (welcome_card_enabled) for editor."""
        b, _ = self._require_greeting_service()
        cfg = await b.greeting_service.get_config(guild_id)
        cfg.welcome_card_enabled = enabled  # orphan: cardEnabled
        await b.greeting_service.save_config(cfg)

    async def set_theme_id(self, guild_id: str, theme_id: str | None) -> None:
        """Expose orphan column themeId."""
        b, _ = self._require_greeting_service()
        cfg = await b.greeting_service.get_config(guild_id)
        cfg.theme_id = theme_id  # orphan: themeId
        await b.greeting_service.save_config(cfg)

    async def set_onboarding_channel_id(self, guild_id: str, channel_id: str | None) -> None:
        """Expose orphan column onboardingChannelId."""
        b, _ = self._require_greeting_service()
        cfg = await b.greeting_service.get_config(guild_id)
        cfg.onboarding_channel_id = channel_id  # orphan: onboardingChannelId
        await b.greeting_service.save_config(cfg)

    async def set_welcome_template_id(
        self,
        guild_id: str,
        template_id: str | None,
        bot: typing.Any | None = None,
    ) -> None:
        """Persist the per-kind welcome template id (migration 030 column)."""
        await self._save_template_id(guild_id, template_id, bot=bot)

    def _render_extra_status_lines(self, guild_id: str, cfg: typing.Any, not_cfg: str) -> list[str]:  # noqa: ARG002
        theme_display = getattr(cfg, "theme_id", None) or self._t(guild_id, "theme_not_set")
        return [f"**{self._t(guild_id, 'theme_label')}:** {theme_display}"]

    def _render_post_template_status_lines(self, guild_id: str, cfg: typing.Any, not_cfg: str) -> list[str]:
        onboarding_id = getattr(cfg, "onboarding_channel_id", None)
        onboarding_display = f"<#{onboarding_id}>" if onboarding_id else not_cfg
        return [f"**{self._t(guild_id, 'onboarding_label')}:** {onboarding_display}"]
