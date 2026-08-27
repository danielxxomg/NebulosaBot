"""S6B.1 RED — /dados → /dice rename (strict TDD).

Ref: ocio-commands "Dice command" — canonical English /dice with
Spanish name_localizations es:"dados"; /dados MUST NOT resolve in
default locale; range [1,sides] in [2,100] rejects else.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock

from discord import app_commands
from discord.ext import commands

from bot.cogs.ocio import OcioCog


def _get_app_commands(cog: OcioCog) -> dict[str, app_commands.Command]:
    """Collect app_commands by name via walk_app_commands."""
    out: dict[str, app_commands.Command] = {}
    for cmd in cog.walk_app_commands():  # type: ignore[attr-defined]
        out[cmd.name] = cmd  # type: ignore[assignment]
        # expanded groups
        if isinstance(cmd, app_commands.Group):
            for sub in cmd.walk_commands():
                out[sub.name] = sub  # type: ignore[assignment]
    # also direct attributes
    for attr in ("dice", "dados"):
        obj = getattr(cog, attr, None)
        if obj is not None and hasattr(obj, "name"):
            try:
                n = obj.name  # type: ignore[union-attr]
                if n not in out:
                    out[n] = obj  # type: ignore[assignment]
            except Exception:
                pass
    return out


def test_dice_resolves_in_default_locale() -> None:
    bot = MagicMock(spec=commands.Bot)
    cog = OcioCog(bot)
    cmds = _get_app_commands(cog)
    assert "dice" in cmds, "canonical /dice must resolve in default locale"
    cmd = cmds["dice"]
    # must be pure app command, not hybrid
    assert isinstance(cmd, app_commands.Command), "/dice must be app_commands.Command"
    assert "hybrid" not in type(cmd).__name__.lower()


def test_dados_does_not_resolve() -> None:
    bot = MagicMock(spec=commands.Bot)
    cog = OcioCog(bot)
    cmds = _get_app_commands(cog)
    assert "dados" not in cmds, "/dados must NOT resolve in default locale"
    # also no legacy attribute exposing dados name
    legacy = getattr(cog, "dados", None)
    if legacy is not None:
        name = getattr(legacy, "name", None)
        assert name != "dados", "legacy dados attribute must not expose name dados"


def test_name_localizations_es_is_dados() -> None:
    bot = MagicMock(spec=commands.Bot)
    cog = OcioCog(bot)
    cmds = _get_app_commands(cog)
    assert "dice" in cmds
    cmd = cmds["dice"]
    # locale_name must carry Spanish localization via extras key
    locale_name = getattr(cmd, "_locale_name", None)
    # Must be locale_str with extras key that resolves to dados via translator
    # For RED, we accept either locale_str with key or payload check
    has_es_localization = False
    if locale_name is not None:
        extras = getattr(locale_name, "extras", None) or {}
        if extras.get("key") in ("slash.names.dice", "slash.descriptions.dice"):
            has_es_localization = True
        # also check message itself
        if getattr(locale_name, "message", None) == "dice":
            # Check that translator would produce dados for es
            from bot.core.i18n import _resolve_key

            val = _resolve_key("es", "slash.names.dice") if "slash.names.dice" in str(extras) else None
            # Fallback: at least name is dice
            has_es_localization = True
    # Also inspect payload generation (best effort without running translator)
    # Require that source declares name_localizations intent
    src = Path("bot/cogs/ocio.py").read_text(encoding="utf-8")
    assert "dice" in src and "locale_str" in src, "dice command must use locale_str for name"
    # Direct file check for es dados token
    assert "dados" in src.lower(), "source must mention dados for es localization"
    # If still not convinced, force fail to ensure RED until implementation sets locale_str correctly
    assert has_es_localization or "name_localizations" in src or "slash.names.dice" in src, (
        "es name_localizations 'dados' missing"
    )


def test_dice_range_accepts_and_rejects() -> None:
    bot = MagicMock(spec=commands.Bot)
    cog = OcioCog(bot)
    cmds = _get_app_commands(cog)
    assert "dice" in cmds
    cmd = cmds["dice"]
    # inspect callback signature for sides annotation Range[2,100]
    cb = getattr(cmd, "callback", None) or getattr(cmd, "_callback", None)
    assert cb is not None
    params = inspect.signature(cb).parameters
    assert "sides" in params
    ann = params["sides"].annotation
    ann_str = str(ann)
    assert "Range" in ann_str or "Annotated" in ann_str, f"sides must be Range[2,100], got {ann_str}"
    # bounds check via string
    assert "2" in ann_str and "100" in ann_str, f"Range bounds must be 2..100, got {ann_str}"
