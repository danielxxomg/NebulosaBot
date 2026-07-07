"""Guard tests for the app.py entry point (cache-sync-realtime PR 2).

The inbound webhook + Cloudflare Tunnel was replaced by the outbound Supabase
Realtime CDC subscriber, so app.py MUST be a bot-only entry point that
delegates to ``bot.__main__.main`` — no tunnel bootstrapping, no cloudflared,
no webhook references.
"""

from __future__ import annotations

from pathlib import Path

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"
APP_SOURCE = APP_PATH.read_text(encoding="utf-8")


class TestAppEntrySimplified:
    """cache-sync-realtime PR 2: app.py MUST be bot-only (< 20 lines)."""

    def test_no_cloudflared_or_tunnel_references(self) -> None:
        """No cloudflared / tunnel / TUNNEL_TOKEN references may remain."""
        assert "cloudflared" not in APP_SOURCE
        assert "TUNNEL_TOKEN" not in APP_SOURCE
        assert "tunnel" not in APP_SOURCE.lower()

    def test_no_tunnel_lifecycle_functions(self) -> None:
        """The start_tunnel / ensure_cloudflared helpers MUST be gone."""
        assert "def start_tunnel" not in APP_SOURCE
        assert "def ensure_cloudflared" not in APP_SOURCE
        assert "def _cloudflared_url" not in APP_SOURCE

    def test_delegates_to_bot_main(self) -> None:
        """app.py MUST reference bot.__main__ (delegates the bot launch)."""
        assert "bot.__main__" in APP_SOURCE

    def test_app_py_is_short(self) -> None:
        """Spec success criterion: app.py < 20 lines."""
        line_count = len(APP_SOURCE.splitlines())
        assert line_count <= 20, f"app.py is {line_count} lines — expected ≤ 20"
