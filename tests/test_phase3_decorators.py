"""Tests for Phase 3: Cog decorator localization.

Verifies that all 8 cog hybrid commands have locale_str descriptions
with key="slash.descriptions.*" and @app_commands.describe params use
locale_str with key="slash.describes.*".

Also covers error handler localization and MANUAL default language.

Strict TDD: RED phase — tests written BEFORE the implementation.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from bot.core.i18n import SLASH_DESCRIPTIONS, SLASH_DESCRIBES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_cog_commands() -> list[tuple[str, commands.Cog, str, object]]:
    """Discover all hybrid commands across all cogs.

    Returns list of (cog_name, cog_instance, cmd_name, cmd_obj) tuples.
    We instantiate cogs with a MagicMock bot to avoid setup_hook.
    """
    from unittest.mock import MagicMock

    import bot.cogs as cogs_pkg

    results: list[tuple[str, commands.Cog, str, object]] = []
    mock_bot = MagicMock()

    for _importer, modname, _ispkg in pkgutil.iter_modules(cogs_pkg.__path__):
        if modname.startswith("_"):
            continue
        mod = importlib.import_module(f"bot.cogs.{modname}")
        for attr_name in dir(mod):
            cls = getattr(mod, attr_name, None)
            if cls is None or not isinstance(cls, type):
                continue
            if not issubclass(cls, commands.Cog) or cls is commands.Cog:
                continue
            try:
                cog_instance = cls(mock_bot)
            except Exception:
                continue
            if not hasattr(cog_instance, "__cog_commands__"):
                continue
            for cmd in cog_instance.__cog_commands__:
                results.append((cls.__name__, cog_instance, cmd.name, cmd))
                # Also check subcommands of groups
                if isinstance(cmd, commands.HybridGroup):
                    for sub_cmd in cmd.commands:
                        results.append((cls.__name__, cog_instance, f"{cmd.name} {sub_cmd.name}", sub_cmd))

    return results


def _is_locale_str(value: object) -> bool:
    """Check if a value is a discord.app_commands.locale_str instance."""
    return isinstance(value, app_commands.locale_str)


def _get_locale_str_key(value: object) -> str | None:
    """Extract the extras['key'] from a locale_str, or None."""
    if not _is_locale_str(value):
        return None
    extras = getattr(value, "extras", None)
    if extras and isinstance(extras, dict):
        return extras.get("key")
    return None


def _get_cmd_locale_key(cmd: object) -> str | None:
    """Get the locale_str key from a command's description.

    Checks _locale_description first (discord.py stores locale_str there),
    then falls back to description attribute.
    """
    locale_desc = getattr(cmd, "_locale_description", None)
    if locale_desc is not None and _is_locale_str(locale_desc):
        return _get_locale_str_key(locale_desc)
    desc = getattr(cmd, "description", None)
    if _is_locale_str(desc):
        return _get_locale_str_key(desc)
    return None


# ---------------------------------------------------------------------------
# Task 3.1: All hybrid commands have locale_str descriptions
# ---------------------------------------------------------------------------


class TestCogDescriptionsLocaleStr:
    """All hybrid commands/groups/subcommands MUST have locale_str descriptions."""

    def test_all_hybrid_commands_have_locale_str_description(self) -> None:
        """Every hybrid command's description MUST be a locale_str with a slash.descriptions.* key.

        In discord.py 2.7.1, the locale_str is stored on _locale_description,
        while description is a plain str. We check _locale_description.
        """
        cog_commands = _get_cog_commands()
        failures: list[str] = []

        for cog_name, _cog, cmd_name, cmd in cog_commands:
            key = _get_cmd_locale_key(cmd)
            if key is None:
                qualified = getattr(cmd, "qualified_name", cmd_name)
                failures.append(
                    f"{cog_name}.{qualified}: no locale_str key found (_locale_description missing or no key)"
                )
            elif not key.startswith("slash.descriptions."):
                qualified = getattr(cmd, "qualified_name", cmd_name)
                failures.append(
                    f"{cog_name}.{qualified}: key '{key}' does not start with 'slash.descriptions.'"
                )

        assert not failures, (
            f"Commands missing locale_str descriptions:\n"
            + "\n".join(f"  - {f}" for f in failures)
        )

    def test_all_describe_params_use_locale_str(self) -> None:
        """Every @app_commands.describe param MUST use locale_str with a slash.describes.* key.

        Inspects the command's app_command._params dict which stores
        CommandParameter objects with description=locale_str.
        In discord.py 2.7.1, @app_commands.describe wraps strings as
        locale_str automatically — but without extras['key']. We verify
        the key is present.
        """
        cog_commands = _get_cog_commands()
        failures: list[str] = []
        seen: set[str] = set()  # Avoid duplicate reports

        for cog_name, _cog, cmd_name, cmd in cog_commands:
            app_cmd = getattr(cmd, "app_command", None)
            if app_cmd is None:
                continue
            params_dict = getattr(app_cmd, "_params", None)
            if params_dict is None:
                continue

            qualified = getattr(cmd, "qualified_name", cmd_name)
            for param_name, param_obj in params_dict.items():
                # Skip ctx param
                if param_name == "ctx":
                    continue
                report_key = f"{qualified}.{param_name}"
                if report_key in seen:
                    continue

                desc = getattr(param_obj, "description", None)
                if _is_locale_str(desc):
                    key = _get_locale_str_key(desc)
                    if key is None:
                        seen.add(report_key)
                        failures.append(
                            f"{cog_name}.{qualified}.{param_name}: locale_str has no extras['key'] — needs key='slash.describes.*'"
                        )
                    elif not key.startswith("slash.describes."):
                        seen.add(report_key)
                        failures.append(
                            f"{cog_name}.{qualified}.{param_name}: key '{key}' wrong prefix"
                        )
                elif desc and isinstance(desc, str):
                    seen.add(report_key)
                    failures.append(
                        f"{cog_name}.{qualified}.{param_name}: description is plain string, not locale_str"
                    )

        assert not failures, (
            f"Parameters missing locale_str keys:\n"
            + "\n".join(f"  - {f}" for f in failures)
        )

    def test_registry_keys_match_cog_decorators(self) -> None:
        """SLASH_DESCRIPTIONS registry MUST contain keys for all commands with locale_str."""
        cog_commands = _get_cog_commands()
        failures: list[str] = []

        for cog_name, _cog, cmd_name, cmd in cog_commands:
            key = _get_cmd_locale_key(cmd)
            if key is None:
                continue
            qualified = getattr(cmd, "qualified_name", cmd_name)
            registry_key = SLASH_DESCRIPTIONS.get(qualified)
            if registry_key is None:
                registry_key = SLASH_DESCRIPTIONS.get(cmd_name)
            if registry_key is None:
                failures.append(
                    f"{cog_name}.{qualified}: locale_str key '{key}' not in SLASH_DESCRIPTIONS registry"
                )

        assert not failures, (
            f"Commands with locale_str not in registry:\n"
            + "\n".join(f"  - {f}" for f in failures)
        )


# ---------------------------------------------------------------------------
# Task 3.7: Error handler localization
# ---------------------------------------------------------------------------


class TestErrorHandlerLocalization:
    """on_app_command_error MUST use t() for title and description."""

    @pytest.mark.asyncio
    async def test_error_handler_uses_t_for_title_es(self) -> None:
        """Spanish guild error embed title MUST come from t() (not hardcoded)."""
        from bot.bot import NebulosaBot
        from bot.core.i18n import load_locales, set_guild_language

        # Load real locales
        load_locales(Path("bot/locales"))
        set_guild_language("111", "es")

        interaction = MagicMock(spec=discord.Interaction)
        interaction.command = MagicMock(spec=app_commands.Command)
        interaction.command.cog = None
        interaction.guild = MagicMock()
        interaction.guild.id = 111
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock()
        interaction.followup.send = AsyncMock()

        error = app_commands.AppCommandError("boom")

        await NebulosaBot.on_app_command_error(MagicMock(), interaction, error)

        interaction.response.send_message.assert_awaited_once()
        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        assert embed is not None
        # Title should be Spanish localized (not hardcoded "Unexpected Error")
        from bot.core.i18n import t
        expected_title = t("111", "common.error.unexpected_title")
        assert embed.title == expected_title
        assert embed.title != "Unexpected Error"  # Not the hardcoded English

    @pytest.mark.asyncio
    async def test_error_handler_uses_t_for_title_en(self) -> None:
        """English guild error embed title MUST come from t() — verified via mock."""
        from bot.bot import NebulosaBot
        from bot.core.i18n import load_locales, set_guild_language

        load_locales(Path("bot/locales"))
        set_guild_language("222", "en")

        interaction = MagicMock(spec=discord.Interaction)
        interaction.command = MagicMock(spec=app_commands.Command)
        interaction.command.cog = None
        interaction.guild = MagicMock()
        interaction.guild.id = 222
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock()
        interaction.followup.send = AsyncMock()

        error = app_commands.AppCommandError("boom")

        # Patch t() to return a marker to prove it's called
        with patch("bot.bot.t", return_value="MARKER_TITLE") as mock_t:
            await NebulosaBot.on_app_command_error(MagicMock(), interaction, error)

        mock_t.assert_called()
        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        assert embed is not None
        assert embed.title == "MARKER_TITLE"

    @pytest.mark.asyncio
    async def test_error_handler_resolves_guild_id_from_interaction(self) -> None:
        """Error handler MUST extract guild_id from interaction for t() resolution."""
        from bot.bot import NebulosaBot
        from bot.core.i18n import load_locales, set_guild_language

        load_locales(Path("bot/locales"))
        set_guild_language("333", "en")

        interaction = MagicMock(spec=discord.Interaction)
        interaction.command = MagicMock(spec=app_commands.Command)
        interaction.command.cog = None
        interaction.guild = MagicMock()
        interaction.guild.id = 333
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock()

        error = app_commands.AppCommandError("test")

        with patch("bot.bot.t", return_value="MARKER") as mock_t:
            await NebulosaBot.on_app_command_error(MagicMock(), interaction, error)

        # t() must be called with guild_id=333 (or str(333))
        call_args = mock_t.call_args_list
        guild_ids_used = [str(call.args[0]) for call in call_args if call.args]
        assert "333" in guild_ids_used, (
            f"Expected t() called with guild_id 333, got calls: {call_args}"
        )

    @pytest.mark.asyncio
    async def test_error_handler_no_guild_uses_none(self) -> None:
        """When interaction has no guild, error handler MUST call t(None, ...)."""
        from bot.bot import NebulosaBot
        from bot.core.i18n import load_locales

        load_locales(Path("bot/locales"))

        interaction = MagicMock(spec=discord.Interaction)
        interaction.command = MagicMock(spec=app_commands.Command)
        interaction.command.cog = None
        interaction.guild = None  # No guild
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock()

        error = app_commands.AppCommandError("test")

        with patch("bot.bot.t", return_value="MARKER") as mock_t:
            await NebulosaBot.on_app_command_error(MagicMock(), interaction, error)

        # t() must be called with guild_id=None
        call_args = mock_t.call_args_list
        guild_ids_used = [call.args[0] for call in call_args if call.args]
        assert None in guild_ids_used, (
            f"Expected t() called with guild_id=None, got calls: {call_args}"
        )


# ---------------------------------------------------------------------------
# Task 3.9: MANUAL.md default language
# ---------------------------------------------------------------------------


class TestManualDefaultLanguage:
    """MANUAL.md MUST state default language is es (Spanish)."""

    def test_manual_default_language_is_es(self) -> None:
        """Manual MUST reference default language as 'es', not 'en'."""
        manual_path = Path("docs/MANUAL.md")
        content = manual_path.read_text(encoding="utf-8")
        # Look for the language configuration section
        # Should say default is es, not en
        lower = content.lower()
        # Must NOT say default is en
        assert "por defecto: `en`" not in lower, "Manual incorrectly states default language is 'en'"
        assert "default: `en`" not in lower, "Manual incorrectly states default language is 'en'"
        # Must mention es as default somewhere in the language section
        assert "por defecto: `es`" in lower or "default: `es`" in lower, (
            "Manual must state default language is 'es'"
        )

    def test_manual_documents_localized_slash_descriptions(self) -> None:
        """Manual MUST document that slash descriptions are client-localized."""
        manual_path = Path("docs/MANUAL.md")
        content = manual_path.read_text(encoding="utf-8")
        lower = content.lower()
        # Must mention that slash descriptions are localized
        has_localization_note = any(
            phrase in lower
            for phrase in [
                "descripciones slash",
                "slash descriptions",
                "client-localized",
                "localizadas",
                "discord client locale",
                "idioma del cliente",
                "client locale",
            ]
        )
        assert has_localization_note, (
            "Manual must document that slash descriptions are client-localized"
        )
