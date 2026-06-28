"""Entry point: ``python -m bot``.

Loads environment configuration, creates the :class:`NebulosaBot`
instance with appropriate intents, and connects to Discord.
"""

from __future__ import annotations

import asyncio
import logging

import discord

from bot.bot import NebulosaBot
from bot.config import BotConfig

# ------------------------------------------------------------------
# Logging — sensible defaults so we see what's happening.
# ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
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
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True  # needed for is_mod/is_admin role checks

    logger.info("Creating NebulosaBot ...")
    bot = NebulosaBot(config=config, intents=intents)

    logger.info("Starting bot (token: %s...) ...", config.discord_token[:8])
    async with bot:
        await bot.start(config.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
