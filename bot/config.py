"""Bot configuration — environment loading and validation."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    """Configuration loaded from environment variables.

    Attributes:
        discord_token: Discord bot token from Discord Developer Portal.
        supabase_url: Supabase project URL.
        supabase_key: Supabase API key (anon or service_role).
    """

    discord_token: str = ""
    supabase_url: str = ""
    supabase_key: str = ""

    _env_vars: tuple[str, ...] = field(
        default=("DISCORD_TOKEN", "SUPABASE_URL", "SUPABASE_KEY"),
        init=False,
        repr=False,
    )

    @classmethod
    def from_env(cls, env_path: str | None = None) -> BotConfig:
        """Load configuration from environment variables.

        Missing or empty env vars fall back to field defaults (empty strings)
        rather than raising, so the bot can start in a degraded state.

        Args:
            env_path: Optional path to a .env file. If None, dotenv searches
                the current working directory for a .env file.

        Returns:
            A BotConfig instance — fields may be empty if env vars are missing.
        """
        load_dotenv(dotenv_path=env_path, override=False)

        values: dict[str, str] = {}
        missing: list[str] = []

        for var in cls._env_vars:
            value = os.getenv(var)
            if value:
                values[var.lower()] = value
            else:
                missing.append(var)

        if missing:
            logger.warning(
                "Missing env vars (falling back to defaults): %s",
                ", ".join(missing),
            )

        if "discord_token" in values:
            logger.info("Configuration loaded successfully (token: %s...)", values["discord_token"][:8])

        return cls(
            discord_token=values.get("discord_token", ""),
            supabase_url=values.get("supabase_url", ""),
            supabase_key=values.get("supabase_key", ""),
        )
