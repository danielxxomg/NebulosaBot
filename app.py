"""Pterodactyl entry point — delegates to bot.__main__.main (bot-only)."""

import asyncio
import logging

from dotenv import load_dotenv

load_dotenv(override=False)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from bot.__main__ import main as bot_main  # noqa: E402

if __name__ == "__main__":
    asyncio.run(bot_main())
