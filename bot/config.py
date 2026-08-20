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


_JWKS_ALGS: list[str] = ["RS256", "ES256"]


def _verify_jwt_jwks(key: str) -> str | None:
    """Verify RS256/ES256 JWT via JWKS PyJWKClient with bounded kid refresh.

    Uses ``SUPABASE_JWKS_URL`` (or ``SUPABASE_JWKS_URI``), requires
    ``role``, ``iss``, ``aud``, ``exp``. Allowlist ``["RS256","ES256"]``;
    unknown ``kid`` triggers one bounded refresh (initial attempt + 1 refresh = 2
    total attempts); otherwise fails closed without HS256 fallback. EC P-256
    (ES256) and RSA (RS256) both via ``PyJWKClient`` ``kid``-bound selection.
    Returns ``role`` on success, ``None`` on any failure.
    """
    jwks_url = (
        os.getenv("SUPABASE_JWKS_URL", "").strip()
        or os.getenv("SUPABASE_JWKS_URI", "").strip()
        or os.getenv("JWKS_URL", "").strip()
    )
    if not jwks_url:
        return None
    # Reject algs not in allowlist to block alg confusion (no HS256 fallback).
    try:
        import jwt as pyjwt

        header = pyjwt.get_unverified_header(key)
    except Exception:
        return None
    alg = str(header.get("alg") or "")
    if alg not in _JWKS_ALGS:
        return None
    issuer = os.getenv("SUPABASE_JWT_ISSUER", "").strip()
    audience = os.getenv("SUPABASE_JWT_AUDIENCE", "").strip()
    # JWKS requires issuer/audience configured to avoid accepting arbitrary tokens.
    if not issuer or not audience:
        return None
    max_kid_refreshes = 1
    attempts = 0
    last_exc: Exception | None = None
    while attempts < 1 + max_kid_refreshes:
        attempts += 1
        try:
            client = pyjwt.PyJWKClient(jwks_url)
            signing_key = client.get_signing_key_from_jwt(key)
            payload: dict[str, object] = pyjwt.decode(
                key,
                signing_key.key,
                algorithms=_JWKS_ALGS,
                issuer=issuer,
                audience=audience,
                options={"require": ["exp", "iss", "aud"]},
            )
            role = payload.get("role")
            if not isinstance(role, str) or not role:
                return None
            return role
        except Exception as exc:
            last_exc = exc
            # Bounded kid refresh: retry only on JWK client kid-not-found errors.
            msg = str(exc).lower()
            if "kid" in msg or "jwk" in msg or "not found" in msg or "unable to find" in msg:
                if attempts <= max_kid_refreshes:
                    continue
                break
            return None
    # Exhausted retries
    _ = last_exc
    return None


def _verify_jwt_rs256(key: str) -> str | None:
    """Backward-compat alias — delegates to :func:`_verify_jwt_jwks`."""
    return _verify_jwt_jwks(key)


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
        msg = "test-key sentinel is only allowed in test env — expected service_role JWT"
        raise ServiceRoleValidationError(msg)
    if not key or not key.strip():
        msg = "Supabase key is missing or empty — expected service_role"
        raise ServiceRoleValidationError(msg)
    if key.startswith("sb_publishable_"):
        msg = "Publishable key is not service_role — RLS would deny anon access"
        raise ServiceRoleValidationError(msg)
    # Modern Supabase secret key — opaque, not a JWT; acceptance is proven
    # by a read-only SELECT probe on RLS-enabled tables in health_check.
    if key.startswith("sb_secret_"):
        return
    # Legacy JWT path — fail-closed when signing source is absent. Only an sb_secret_
    # (proven via health_probe) or a verified service_role JWT is accepted; payload-only
    # without a signing source MUST NOT be accepted (prevents fake sig).
    # RS256 via JWKS is the modern path; HS256 allowlist retained for legacy.
    if key.count(".") == 2:
        # Try JWKS (RS256+ES256) first when header says RS256/ES256 and JWKS configured.
        try:
            import jwt as _pyjwt

            hdr = _pyjwt.get_unverified_header(key)
            if hdr.get("alg") in _JWKS_ALGS:
                jwks_role = _verify_jwt_jwks(key)
                if jwks_role is not None:
                    if jwks_role != "service_role":
                        msg = f"Supabase key role is {jwks_role!r}, expected service_role"
                        raise ServiceRoleValidationError(msg)
                    return
                msg = (
                    "Supabase JWT JWKS verification failed (kid/iss/aud/exp/role) — "
                    "expected verifiable service_role JWT or modern sb_secret_"
                )
                raise ServiceRoleValidationError(msg)
        except ServiceRoleValidationError:
            raise
        except Exception:
            pass
        verified_role = _verify_jwt_signature(key)
        if verified_role is not None:
            if verified_role != "service_role":
                msg = f"Supabase key role is {verified_role!r}, expected service_role"
                raise ServiceRoleValidationError(msg)
            return
        msg = (
            "Supabase JWT signature verification failed or no signing source (SUPABASE_JWT_SECRET/JWKS) — "
            "expected verifiable service_role JWT or modern sb_secret_"
        )
        raise ServiceRoleValidationError(msg)
    msg = "Supabase key is not a verifiable service_role credential"
    raise ServiceRoleValidationError(msg)


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
