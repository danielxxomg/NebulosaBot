"""Guild configuration model — mirrors the Guild table."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GuildConfig:
    """Guild-level configuration stored in Supabase.

    Mirrors the Guild table columns. Discord IDs are stored as strings
    to avoid precision loss with large snowflakes.
    """

    id: str  # Discord guild ID (PK)
    prefix: str = "nb!"
    language: str = "es"
    mod_role_id: str | None = None
    log_channel_id: str | None = None
    ticket_category_id: str | None = None
    log_enabled: bool = False
    welcome_enabled: bool = False
    active: bool = True

    # Aliases matching DB column names for Supabase row mapping.
    _db_aliases: dict[str, str] = field(
        default_factory=lambda: {
            "modRoleId": "mod_role_id",
            "logChannelId": "log_channel_id",
            "ticketCategoryId": "ticket_category_id",
            "logEnabled": "log_enabled",
            "welcomeEnabled": "welcome_enabled",
        },
        init=False,
        repr=False,
    )

    @classmethod
    def from_db_row(cls, row: dict) -> GuildConfig:
        """Build a GuildConfig from a Supabase row (camelCase keys)."""
        return cls(
            id=row["id"],
            prefix=row.get("prefix", "nb!"),
            language=row.get("language", "es"),
            mod_role_id=row.get("modRoleId"),
            log_channel_id=row.get("logChannelId"),
            ticket_category_id=row.get("ticketCategoryId"),
            log_enabled=row.get("logEnabled", False),
            welcome_enabled=row.get("welcomeEnabled", False),
            active=row.get("active", True),
        )

    def to_db_dict(self) -> dict:
        """Convert to a dict with camelCase keys for Supabase."""
        return {
            "id": self.id,
            "prefix": self.prefix,
            "language": self.language,
            "modRoleId": self.mod_role_id,
            "logChannelId": self.log_channel_id,
            "ticketCategoryId": self.ticket_category_id,
            "logEnabled": self.log_enabled,
            "welcomeEnabled": self.welcome_enabled,
            "active": self.active,
        }
