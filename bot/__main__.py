"""Entry point: ``python -m bot``.

Loads environment configuration, creates the :class:`NebulosaBot`
instance with appropriate intents, and connects to Discord.
"""

from __future__ import annotations

import asyncio
import logging
import os

# ------------------------------------------------------------------
# Logging — sensible defaults so we see what's happening.
# Rotating file handler bounds disk to ~60 MB (10 MB x 5 backups + active).
# Operational config (config.toml) may override level/file at boot (restart-only).
# ------------------------------------------------------------------
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import discord

from bot.bot import NebulosaBot
from bot.config import BotConfig
from bot.operational_config import load_operational_config

_op_cfg = load_operational_config()

logging.basicConfig(
    level=getattr(logging, _op_cfg.logging.level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Rotating file sink — replaces basicConfig file sink per D4 (S4.5)
try:
    _log_path = Path(_op_cfg.logging.file)
    _log_path.parent.mkdir(parents=True, exist_ok=True)
    _rotating = RotatingFileHandler(
        str(_log_path),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    _rotating.setLevel(getattr(logging, _op_cfg.logging.level.upper(), logging.INFO))
    _rotating.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    logging.getLogger().addHandler(_rotating)
except Exception:  # noqa: BLE001 -- logging bootstrap never crashes boot
    logging.getLogger(__name__).exception("Failed to attach RotatingFileHandler")

logger = logging.getLogger(__name__)

_SENSITIVE_SUBSTRINGS = ("token", "SECRET", "SUPABASE", "DISCORD")


def _scrub(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:  # noqa: ARG001, C901
    """Scrub PII/secrets from a Sentry event before sending.

    Drops any string value containing token/SECRET/SUPABASE/DISCORD
    (case-sensitive substring match per tasks S0.3) and removes raw
    ``message`` / breadcrumb message content so user content never leaves
    the host. Returns None to drop the event only when it would still
    carry PII after scrubbing — otherwise returns the scrubbed event.
    """
    import copy  # noqa: PLC0415 -- stdlib import inside function for lazy reuse boundary

    scrubbed = copy.deepcopy(event)
    # Drop raw message content — never send raw user content.
    scrubbed.pop("message", None)
    # Scrub breadcrumbs messages
    bcs = scrubbed.get("breadcrumbs")
    if isinstance(bcs, dict):
        vals = bcs.get("values")
        if isinstance(vals, list):
            for bc in vals:
                if isinstance(bc, dict):
                    bc.pop("message", None)
    # Generic scrub: drop any string leaf containing sensitive substrings
    # and also redact env-value matches if present in the payload.

    def _contains_sensitive(s: str) -> bool:
        if any(sub in s for sub in _SENSITIVE_SUBSTRINGS):
            return True
        # Also redact exact env values if they appear
        for k in ("DISCORD_TOKEN", "SUPABASE_DB_URL", "SUPABASE_URL", "SUPABASE_KEY", "SENTRY_DSN"):
            v = os.getenv(k, "")
            if v and v in s:
                return True
        return False

    def _scrub_obj(obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for kk, vv in obj.items():
                # Drop keys that look sensitive
                if any(sub in str(kk) for sub in _SENSITIVE_SUBSTRINGS):
                    continue
                # Scrub value
                if isinstance(vv, str) and _contains_sensitive(vv):
                    continue
                out[kk] = _scrub_obj(vv)
            return out
        if isinstance(obj, list):
            return [_scrub_obj(x) for x in obj]
        if isinstance(obj, str) and _contains_sensitive(obj):
            return "[Filtered]"
        return obj

    # Scrub extra/exception/message remnants (message already popped above)
    for key in ("extra", "exception", "contexts", "user", "tags"):
        if key in scrubbed:
            scrubbed[key] = _scrub_obj(scrubbed[key])
    # Also scrub any remaining top-level string values that may contain secrets
    for k in list(scrubbed.keys()):
        v = scrubbed[k]
        if isinstance(v, str) and _contains_sensitive(v):
            scrubbed[k] = "[Filtered]"
    return scrubbed


def _init_sentry() -> None:
    """Env-gated Sentry init. No-op when SENTRY_DSN is absent/empty."""
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk  # noqa: PLC0415 -- optional dep, env-gated
    except ImportError:
        logger.warning("sentry-sdk not installed — Sentry disabled")
        return
    sentry_sdk.init(dsn=dsn, send_default_pii=False, before_send=_scrub)


# Back-compat alias for tests that import init_sentry
init_sentry = _init_sentry


async def main() -> None:
    """Bootstrap the bot.

    1. Load config from environment / .env file.
    2. Build Discord intents (message content + members required).
    3. Instantiate ``NebulosaBot``.
    4. Connect to the Discord gateway.
    """
    logger.info("Loading configuration ...")
    config = BotConfig.from_env()

    # Intents — message_content is required for prefix commands to work.
    # Voice observatory (PR3 D1): requires Voice States intent. Prerequisite:
    # you MUST enable the Voice States intent in the Discord Developer Portal
    # (Bot → Privileged Gateway Intents → Voice States) or on_voice_state_update
    # will silently never fire. See docs/MANUAL.md § Voice Observatory.
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True  # needed for is_mod/is_admin role checks
    intents.voice_states = True

    logger.info("Creating NebulosaBot ...")
    bot = NebulosaBot(config=config, intents=intents)

    logger.info("Starting bot ...")
    async with bot:
        await bot.start(config.discord_token)


if __name__ == "__main__":
    _init_sentry()
    asyncio.run(main())
