"""Entry point: ``python -m bot``.

Loads environment configuration, creates the :class:`NebulosaBot`
instance with appropriate intents, and connects to Discord.
"""

from __future__ import annotations

import asyncio
import logging

# ------------------------------------------------------------------
# Logging — sensible defaults so we see what's happening.
# Rotating file handler bounds disk to ~60 MB (10 MB x 5 backups + active).
# Operational config (config.toml) may override level/file at boot (restart-only).
# ------------------------------------------------------------------
from logging.handlers import RotatingFileHandler
from pathlib import Path

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
    asyncio.run(main())
