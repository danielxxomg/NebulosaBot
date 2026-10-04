"""Goodbye setup module — parity with legacy /goodbye group + preview.

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

_GOODBYE_SELECT_CUSTOM_ID = "setup:goodbye:select_template"

# Preview forwards the resolved per-kind template via the shared factory:
# greetings.card greeting_title/member_count_text are t()-sourced there.
_PREVIEW_CARD_KEYS = ("greetings.card.goodbye_title", "greetings.card.member_count")

logger = logging.getLogger(__name__)


class GoodbyeSetupModule(GreetingSetupModuleBase):
    """Setup module for goodbye — gated by greeting.manage."""

    key = "goodbye"
    channel_field = "goodbye_channel_id"
    template_field = "goodbye_template_id"
    enabled_field = "goodbye_enabled"
    card_enabled_field = "goodbye_card_enabled"
    editor_actions = (
        "set_channel",
        "toggle",
        "set_message",
        "card_toggle",
    )

    async def set_goodbye_channel(self, guild_id: str, channel_id: str) -> None:
        """Persist the goodbye channel id."""
        b, _ = self._require_greeting_service()
        await self._save_channel(guild_id, channel_id, b)

    async def set_goodbye_template_id(
        self,
        guild_id: str,
        template_id: str | None,
        bot: typing.Any | None = None,
    ) -> None:
        """Persist the per-kind goodbye template id (migration 030 column)."""
        await self._save_template_id(guild_id, template_id, bot=bot)
