"""GreetingConfig model — mirrors the greeting_config table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class GreetingConfig:
    """Per-guild greeting configuration stored in Supabase.

    Mirrors the ``greeting_config`` table.  ``guild_id`` is the primary key
    and foreign key to ``guild(id)`` with ``ON DELETE CASCADE``.
    """

    guild_id: str  # Discord guild ID (PK, FK → guild.id)
    welcome_enabled: bool = False
    goodbye_enabled: bool = False
    welcome_channel_id: str | None = None
    goodbye_channel_id: str | None = None
    onboarding_channel_id: str | None = None
    welcome_message: str | None = None
    goodbye_message: str | None = None
    # Card toggles default to False for new guilds per greeting-config spec
    # (Scenario: Default values for new guild — "card toggles are false").
    welcome_card_enabled: bool = False
    goodbye_card_enabled: bool = False
    updated_at: datetime | None = None
    theme_id: str | None = None
    # Per-kind card template ids (migration 030). ``None`` → resolve via
    # theme_id → "default" (see GreetingService.select_template fallback chain).
    welcome_template_id: str | None = None
    goodbye_template_id: str | None = None

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> GreetingConfig:
        """Build a GreetingConfig from a Supabase row (camelCase keys)."""
        return cls(
            guild_id=row["guildId"],
            welcome_enabled=row.get("welcomeEnabled", False),
            goodbye_enabled=row.get("goodbyeEnabled", False),
            welcome_channel_id=row.get("welcomeChannelId"),
            goodbye_channel_id=row.get("goodbyeChannelId"),
            onboarding_channel_id=row.get("onboardingChannelId"),
            welcome_message=row.get("welcomeMessage"),
            goodbye_message=row.get("goodbyeMessage"),
            welcome_card_enabled=row.get("welcomeCardEnabled", False),
            goodbye_card_enabled=row.get("goodbyeCardEnabled", False),
            updated_at=row.get("updatedAt"),
            theme_id=row.get("themeId"),
            welcome_template_id=row.get("welcomeTemplateId"),
            goodbye_template_id=row.get("goodbyeTemplateId"),
        )

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to a dict with camelCase keys for Supabase.

        Dual-write: ``themeId`` mirrors the effective template selection so the
        legacy column stays consistent for one cycle (design D5). Explicit
        per-kind values win over the legacy mapping when both are present —
        welcome first, then goodbye (welcome-wins tie-break).
        """
        effective_template = self.welcome_template_id or self.goodbye_template_id or self.theme_id
        return {
            "guildId": self.guild_id,
            "welcomeEnabled": self.welcome_enabled,
            "goodbyeEnabled": self.goodbye_enabled,
            "welcomeChannelId": self.welcome_channel_id,
            "goodbyeChannelId": self.goodbye_channel_id,
            "onboardingChannelId": self.onboarding_channel_id,
            "welcomeMessage": self.welcome_message,
            "goodbyeMessage": self.goodbye_message,
            "welcomeCardEnabled": self.welcome_card_enabled,
            "goodbyeCardEnabled": self.goodbye_card_enabled,
            "updatedAt": self.updated_at,
            "themeId": effective_template,
            "welcomeTemplateId": self.welcome_template_id,
            "goodbyeTemplateId": self.goodbye_template_id,
        }
