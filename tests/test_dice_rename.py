"""S6B.1 — /dice is slash-only and name stays English `dice` for all locales.

Ref: ocio-commands "Dice command" — canonical slash-only ``@app_commands.command(name="dice")``
with no name localization; Spanish still sees Spanish description via Translator,
but the name never becomes ``dados``. Strict TDD: this file asserts slash-only.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

from discord import app_commands
from discord.ext import commands

from bot.cogs.ocio import OcioCog


def _get_app_commands(cog: OcioCog) -> dict[str, app_commands.Command]:
    """Collect app_commands by name via walk_app_commands."""
    out: dict[str, app_commands.Command] = {}
    cmds_list = getattr(cog, "walk_app_commands", lambda: [])()
    for cmd in cmds_list:
        assert hasattr(cmd, "name")
        out[cmd.name] = cmd
        if isinstance(cmd, app_commands.Group):
            for sub in getattr(cmd, "walk_commands", lambda: [])():
                out[sub.name] = sub
    for attr in ("dice",):
        obj = getattr(cog, attr, None)
        if obj is not None and hasattr(obj, "name"):
            try:
                n = getattr(obj, "name", None)
                if isinstance(n, str) and n not in out:
                    out[n] = obj
            except Exception:  # noqa: BLE001, S110 -- best-effort probe
                pass
    return out


def test_dice_resolves_in_default_locale() -> None:
    bot = MagicMock(spec=commands.Bot)
    cog = OcioCog(bot)
    cmds = _get_app_commands(cog)
    assert "dice" in cmds, "canonical /dice must resolve in default locale"
    cmd = cmds["dice"]
    assert isinstance(cmd, app_commands.Command), "/dice must be app_commands.Command"
    assert "hybrid" not in type(cmd).__name__.lower()


def test_dados_does_not_resolve() -> None:
    bot = MagicMock(spec=commands.Bot)
    cog = OcioCog(bot)
    cmds = _get_app_commands(cog)
    assert "dados" not in cmds, "/dados must NOT resolve — name stays English per slash-locale spec"


def test_dice_name_is_english_not_localized() -> None:
    """Name attribute itself is English ``dice``; no name_localizations to ``dados``."""
    bot = MagicMock(spec=commands.Bot)
    cog = OcioCog(bot)
    cmds = _get_app_commands(cog)
    assert "dice" in cmds
    cmd = cmds["dice"]
    assert cmd.name == "dice", f"name must be dice, got {cmd.name!r}"
    # No name_localizations carrying 'dados' on the dice command (Translator localizes description, not name)
    localizations = getattr(cmd, "name_localizations", None)
    if isinstance(localizations, dict) and localizations:
        flat = " ".join(str(v) for v in localizations.values())
        assert "dados" not in flat.lower(), "name_localizations must not translate dice to dados"


def test_dice_range_accepts_and_rejects() -> None:
    bot = MagicMock(spec=commands.Bot)
    cog = OcioCog(bot)
    cmds = _get_app_commands(cog)
    assert "dice" in cmds
    cmd = cmds["dice"]
    cb = getattr(cmd, "callback", None) or getattr(cmd, "_callback", None)
    assert cb is not None
    params = inspect.signature(cb).parameters
    assert "sides" in params
    ann = params["sides"].annotation
    ann_str = str(ann)
    assert "Range" in ann_str or "Annotated" in ann_str, f"sides must be Range[2,100], got {ann_str}"
    assert "2" in ann_str and "100" in ann_str, f"Range bounds must be 2..100, got {ann_str}"
