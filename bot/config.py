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
    """Decode JWT role without verifying signature (structure check only).

    Signature verification is attempted by :func:`_verify_jwt_signature` when
    ``PyJWT`` and ``SUPABASE_JWT_SECRET`` are available; otherwise this payload-only
    path is retained for posture compatibility and explicit TODO for S4 JWKS.
    """
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


def _verify_jwt_signature(key: str) -> str | None:
    """Attempt PyJWT HS256 verification with SUPABASE_JWT_SECRET.

    Returns the ``role`` claim only when verification succeeds with algorithm
    allowlist ``["HS256"]``. Returns ``None`` when verification cannot be
    attempted (no library/secret) or fails (invalid signature/alg) — caller
    MUST treat ``None`` as unverifiable and fail-closed for legacy JWT path.

    TODO(S4): add JWKS/RS256 verification for Supabase JWTs signed with asymmetric
    keys; HS256 allowlist remains required and any non-allowlisted alg MUST be
    rejected. See plan.md cred rotation / JWKS follow-up.
    """
    secret = os.getenv("SUPABASE_JWT_SECRET", "").strip()
    if not secret:
        return None
    try:
        import jwt as pyjwt
    except Exception:
        return None
    try:
        payload: dict[str, object] = pyjwt.decode(key, secret, algorithms=["HS256"])
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
    # Legacy JWT path — fail-closed when signing source is absent. Only an sb_secret_
    # (proven via health_probe) or a verified service_role JWT is accepted; payload-only
    # without a signing source MUST NOT be accepted (prevents fake sig).
    if key.count(".") == 2:
        verified_role = _verify_jwt_signature(key)
        if verified_role is not None:
            if verified_role != "service_role":
                raise ServiceRoleValidationError(f"Supabase key role is {verified_role!r}, expected service_role")
            return
        raise ServiceRoleValidationError(
            "Supabase JWT signature verification failed or no signing source (SUPABASE_JWT_SECRET/JWKS) — "
            "expected verifiable service_role JWT or modern sb_secret_"
        )
    raise ServiceRoleValidationError("Supabase key is not a verifiable service_role credential")


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
