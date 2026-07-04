"""Pterodactyl entry point.

Runs as ``python /home/container/app.py`` (the egg's default PY_FILE).
Bootstraps cloudflared (downloaded on first run, no root needed) as a
background subprocess when TUNNEL_TOKEN is set, then starts the bot.

The bot itself lives in ``bot/__main__.py`` and expects ``python -m bot``
(absolute imports ``from bot.xxx``). Running that file directly breaks
because sys.path[0] becomes ``bot/`` instead of the repo root. This
wrapper fixes the path and delegates to ``bot.__main__.main``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the repo root (WORKDIR on Pterodactyl is /home/container).
load_dotenv(override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("app")

_REPO_ROOT = Path(__file__).resolve().parent
_CLOUDFLARED_BIN = _REPO_ROOT / "cloudflared"


def _cloudflared_url() -> str:
    """Return the download URL for the current architecture."""
    arch = platform.machine().lower()
    if arch in ("aarch64", "arm64"):
        suffix = "arm64"
    else:
        suffix = "amd64"  # safe default for x86_64 / amd64
    return f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{suffix}"


def ensure_cloudflared() -> bool:
    """Download the cloudflared binary if not present. Returns True on success."""
    if _CLOUDFLARED_BIN.exists():
        return True
    url = _cloudflared_url()
    logger.info("Downloading cloudflared from %s ...", url)
    try:
        urllib.request.urlretrieve(url, str(_CLOUDFLARED_BIN))
        _CLOUDFLARED_BIN.chmod(0o755)
        logger.info("cloudflared binary ready at %s", _CLOUDFLARED_BIN)
        return True
    except Exception:
        logger.exception("Failed to download cloudflared — bot will run without tunnel (degraded cache-sync mode)")
        return False


def start_tunnel() -> subprocess.Popen[bytes] | None:
    """Start cloudflared tunnel in background if TUNNEL_TOKEN is set."""
    token = os.environ.get("TUNNEL_TOKEN", "").strip()
    if not token:
        logger.info("TUNNEL_TOKEN not set — skipping cloudflared tunnel (webhook cache-sync disabled)")
        return None
    if not ensure_cloudflared():
        return None
    logger.info("Starting cloudflared tunnel ...")
    try:
        return subprocess.Popen(
            [str(_CLOUDFLARED_BIN), "tunnel", "run", "--token", token],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except Exception:
        logger.exception("Failed to start cloudflared — bot continues without tunnel")
        return None


def main() -> None:
    """Launch cloudflared (if configured) then the bot."""
    tunnel_proc = start_tunnel()
    try:
        # sys.path[0] is the script dir (repo root) — absolute imports work.
        from bot.__main__ import main as bot_main
        asyncio.run(bot_main())
    finally:
        if tunnel_proc is not None:
            logger.info("Stopping cloudflared ...")
            tunnel_proc.terminate()
            try:
                tunnel_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                tunnel_proc.kill()


if __name__ == "__main__":
    main()
