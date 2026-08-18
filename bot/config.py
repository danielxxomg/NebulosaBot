"""Bot configuration — environment loading and validation."""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class ServiceRoleValidationError(RuntimeError):
    """Raised when SUPABASE_KEY is not a verifiable service_role credential."""


def _decode_jwt_role(key: str) -> str | None:
    key = key.strip()
    parts = key.split(".")
    if len(parts) != 3:
        return None
    payload_b64 = parts[1]
    pad = "=" * (-len(payload_b64) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + pad).decode())
    except Exception:
        return None
    role = payload.get("role")
    return str(role) if isinstance(role, str) else None


def _is_test_env() -> bool:
    import sys as _sys  # local import to avoid cycle

    if os.getenv("ENV", "").lower() == "test":
        return True
    return "PYTEST_CURRENT_TEST" in os.environ or any("pytest" in (a or "") for a in _sys.argv)


def validate_supabase_key(key: str) -> None:
    """Validate that *key* is a service_role credential; fail-closed otherwise.

    Re-raises as ``bot.config.ServiceRoleValidationError`` so callers can
    gate startup without importing ``bot.core.db.base``.

    Contract (fail-closed): any key that is not a verifiable ``service_role``
    JWT fails, except the modern opaque ``sb_secret_`` prefix which is
    accepted as a server-only credential and proven via a read-only RLS probe
    (see :meth:`bot.core.db.base.DatabaseBase.health_check`). The
    ``test-key`` sentinel bypasses ONLY in test environments
    (``PYTEST_CURRENT_TEST`` or ``ENV=test`` or pytest argv); in any other
    environment it is treated as unverifiable and fails closed.
    """
    if key in ("test-key",) or key.startswith("test-key-"):
        if _is_test_env():
            return
        raise ServiceRoleValidationError("test-key sentinel is only allowed in test env — expected service_role JWT")
    if not key or not key.strip():
        raise ServiceRoleValidationError("Supabase key is missing or empty — expected service_role")
    if key.startswith("sb_publishable_"):
        raise ServiceRoleValidationError("Publishable key is not service_role — RLS would deny anon access")
    # Modern Supabase secret key — opaque, not a JWT; acceptance is proven
    # by a read-only SELECT probe on RLS-enabled tables in health_check.
    if key.startswith("sb_secret_"):
        return
    role = _decode_jwt_role(key)
    if role is None:
        raise ServiceRoleValidationError("Supabase key is not a verifiable JWT — expected service_role JWT")
    if role != "service_role":
        raise ServiceRoleValidationError(f"Supabase key role is {role!r}, expected service_role")


INTEGRITY_BATCH_SIZE = 50
INTEGRITY_BACKOFF_SECONDS = 1.0
INTEGRITY_MAX_BACKOFF_SECONDS = 30.0
INTEGRITY_EVIDENCE_FRESHNESS_SECONDS = 3600


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
