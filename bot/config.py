"""Bot configuration — environment loading and validation."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Webhook defaults (cache-sync-webhook spec — Environment configuration)
WEBHOOK_DEFAULT_HOST = "127.0.0.1"
WEBHOOK_DEFAULT_PORT = 8080


@dataclass
class BotConfig:
    """Configuration loaded from environment variables.

    Attributes:
        discord_token: Discord bot token from Discord Developer Portal.
        supabase_url: Supabase project URL.
        supabase_key: Supabase API key (anon or service_role).
        webhook_secret: Shared HMAC secret for dashboard webhook auth. Empty
            when unset — the webhook server MUST NOT start without it.
        webhook_host: Bind address for the webhook aiohttp server.
        webhook_port: Bind port for the webhook aiohttp server.
    """

    discord_token: str = ""
    supabase_url: str = ""
    supabase_key: str = ""
    webhook_secret: str = ""
    webhook_host: str = WEBHOOK_DEFAULT_HOST
    webhook_port: int = WEBHOOK_DEFAULT_PORT

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

        # Webhook configuration — defaults applied per spec; missing
        # WEBHOOK_SECRET disables the webhook server (logged separately).
        webhook_secret = os.getenv("WEBHOOK_SECRET", "")
        webhook_host = os.getenv("WEBHOOK_HOST", WEBHOOK_DEFAULT_HOST) or WEBHOOK_DEFAULT_HOST
        webhook_port_raw = os.getenv("WEBHOOK_PORT", str(WEBHOOK_DEFAULT_PORT))
        try:
            webhook_port = int(webhook_port_raw)
        except ValueError:
            logger.warning(
                "Invalid WEBHOOK_PORT %r — using default %d",
                webhook_port_raw,
                WEBHOOK_DEFAULT_PORT,
            )
            webhook_port = WEBHOOK_DEFAULT_PORT

        if not webhook_secret:
            # Demoted to DEBUG: start_webhook_server() already emits the single
            # startup WARNING ("webhook server not started"). Logging it here too
            # produced a duplicate signal for the same condition.
            logger.debug("WEBHOOK_SECRET not set — webhook server will not start")

        return cls(
            discord_token=values.get("discord_token", ""),
            supabase_url=values.get("supabase_url", ""),
            supabase_key=values.get("supabase_key", ""),
            webhook_secret=webhook_secret,
            webhook_host=webhook_host,
            webhook_port=webhook_port,
        )
