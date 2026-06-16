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

    discord_token: str
    supabase_url: str
    supabase_key: str

    _required_vars: tuple[str, ...] = field(
        default=("DISCORD_TOKEN", "SUPABASE_URL", "SUPABASE_KEY"),
        init=False,
        repr=False,
    )

    @classmethod
    def from_env(cls, env_path: str | None = None) -> BotConfig:
        """Load configuration from environment variables.

        Args:
            env_path: Optional path to a .env file. If None, dotenv searches
                the current working directory for a .env file.

        Returns:
            A validated BotConfig instance.

        Raises:
            ValueError: If any required variable is missing or empty.
        """
        load_dotenv(dotenv_path=env_path, override=False)

        missing: list[str] = []
        values: dict[str, str] = {}

        for var in cls._required_vars:  # type: ignore[has-type]
            value = os.getenv(var)
            if not value:
                missing.append(var)
            else:
                values[var.lower()] = value

        if missing:
            msg = (
                f"Missing required environment variables: {', '.join(missing)}. "
                "Check your .env file — copy .env.example and set real values."
            )
            logger.error(msg)
            raise ValueError(msg)

        logger.info("Configuration loaded successfully (token: %s...)", values["discord_token"][:8])
        return cls(
            discord_token=values["discord_token"],
            supabase_url=values["supabase_url"],
            supabase_key=values["supabase_key"],
        )
