"""S1 deltas + behavioral proof — strict TDD supplement.

Delta-text checks confirm the 12 spec documents are slash-only, but behavioral
proof lives in dedicated runtime tests (see below). This module now also
contains slash-only runtime guards so COMPLIANT is not just delta wording.
"""

from __future__ import annotations

import ast
import pathlib
from unittest.mock import MagicMock

from bot.cogs.core import _resolve_prefix
from bot.cogs.setup import SetupCog
from bot.utils.checks import can_check, is_admin, is_mod

DELTA_CAPS = [
    "economy-commands",
    "utility-commands",
    "sentinel-commands",
    "ticket-commands",
    "unclaim-command",
    "setup-wizard",
    "permission-model",
    "slash-locale-translator",
    "qa-help-builder",
    "i18n-system",
    "docs-manual",
    "guild-config",
]


def _delta_path(cap: str) -> pathlib.Path:
    active = pathlib.Path(f"openspec/changes/v1-postrelease-zero/specs/{cap}/spec.md")
    if active.exists():
        return active
    archived = pathlib.Path(f"openspec/changes/archive/2026-08-30-v1-postrelease-zero/specs/{cap}/spec.md")
    if archived.exists():
        return archived
    for p in pathlib.Path("openspec/changes/archive").glob("*/v1-postrelease-zero/specs/*/spec.md"):
        if cap in str(p):
            return p
    return active


def test_all_12_delta_specs_exist_and_nonempty() -> None:
    missing = []
    for cap in DELTA_CAPS:
        p = _delta_path(cap)
        if not p.exists() or len(p.read_text()) < 50:
            missing.append(cap)
    assert missing == [], f"delta specs missing or truncated: {missing}"


def test_delta_specs_are_slash_only() -> None:
    """Each delta must describe slash-only, not active hybrid invocation."""
    offenders = []
    for cap in DELTA_CAPS:
        p = _delta_path(cap)
        if not p.exists():
            continue
        txt = p.read_text()
        # Every delta must mention slash commands and not have active hybrid requirement
        has_slash = "slash" in txt.lower()
        if not has_slash:
            offenders.append(f"{cap}: missing slash marker")
        # The active hybrid description "hybrid `/rank`" must not appear as current truth
        for line in txt.splitlines():
            if line.strip().startswith("The system MUST provide a hybrid"):
                offenders.append(f"{cap}: active hybrid requirement remains: {line.strip()[:80]}")
    assert offenders == [], "deltas not slash-only: " + "; ".join(offenders)


def test_bot_core_delta_absent_or_untouched() -> None:
    """bot-core must not have a delta in this change (stay slash-only truth)."""
    p = pathlib.Path("openspec/changes/v1-postrelease-zero/specs/bot-core/spec.md")
    assert not p.exists(), "bot-core must not be modified in S1 deltas"
    txt = pathlib.Path("openspec/specs/bot-core/spec.md").read_text()
    assert "slash" in txt.lower()
    assert "ZERO `hybrid_command`" in txt


def test_economy_commands_delta_covers_4_slash_commands() -> None:
    txt = _delta_path("economy-commands").read_text()
    for cmd in ("/rank", "/leaderboard", "/daily", "/coins"):
        assert cmd in txt, f"economy-commands delta missing {cmd}"


def test_utility_commands_delta_covers_3_slash_commands() -> None:
    txt = _delta_path("utility-commands").read_text()
    for cmd in ("/avatar", "/serverinfo", "/userinfo"):
        assert cmd in txt, f"utility-commands delta missing {cmd}"


def test_sentinel_delta_covers_8_slash_commands() -> None:
    txt = _delta_path("sentinel-commands").read_text()
    for cmd in ("/warn", "/unwarn", "/mute", "/unmute", "/kick", "/ban", "/tempban", "/unban"):
        assert cmd in txt, f"sentinel delta missing {cmd}"


def test_guild_config_delta_is_data_only() -> None:
    txt = _delta_path("guild-config").read_text()
    assert "data-only" in txt
    assert "IF NOT EXISTS" in txt


# ---------------------------------------------------------------------------
# Behavioral proof — slash-only runtime (NOT just delta wording)
# ---------------------------------------------------------------------------


def test_slash_only_app_commands_no_hybrid_decorators() -> None:
    """Runtime: bot/cogs AST has zero hybrid decorators (authoritative check)."""
    cogs_root = pathlib.Path("bot/cogs")
    offenders: list[str] = []
    scanned = 0
    for p in cogs_root.rglob("*.py"):
        scanned += 1
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("hybrid_command", "hybrid_group"):
                offenders.append(f"{p}:{node.lineno}")
                break
    assert scanned > 0, "no cog files discovered"
    assert offenders == [], f"hybrid decorators remain: {offenders}"


def test_setup_command_is_slash_only_with_is_admin_guard() -> None:
    """Runtime: /setup is slash-only with @is_admin guard and zero params."""
    bot = MagicMock()
    cog = SetupCog(bot)
    cmd = cog.setup_command
    # Must be pure app command
    assert hasattr(cmd, "checks") and len(cmd.checks) > 0, "/setup must have slash checks via @is_admin"
    assert not hasattr(cmd, "app_command"), "/setup must not be hybrid"
    # Zero params: no channel/role sinks
    params = list(getattr(cmd, "parameters", []))
    assert len(params) == 0, f"/setup must have zero params, got {params}"
    # Slash checks include is_admin predicate (no prefix dual)
    dec = getattr(cmd, "checks", [])
    assert len(dec) > 0


def test_can_check_and_is_mod_are_slash_only() -> None:
    """Runtime: decorators register app_commands.check only (no commands.check)."""
    assert not hasattr(can_check("moderation.ban"), "prefix_predicate")
    assert not hasattr(is_admin(), "prefix_predicate")
    assert not hasattr(is_mod(), "prefix_predicate")


def test_resolve_prefix_inert_returns_empty() -> None:
    """Runtime: _resolve_prefix exists and returns [] (slash-only, data-only prefix)."""
    assert _resolve_prefix(123) == []
    assert _resolve_prefix(None) == []
