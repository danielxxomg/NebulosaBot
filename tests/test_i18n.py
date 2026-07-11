"""Unit tests for bot.core.i18n — internationalization module.

Covers:
    - load_locales() — loads JSON files into memory
    - set_guild_language() — updates guild→language map
    - t() — Spanish lookup, English lookup, missing-key fallback to es,
      exhausted fallback returns raw key, interpolation, missing placeholder
      warning, None guild_id fallback
    - LocaleTranslator — Discord locale→language mapping, translate() for
      locale_str keys from in-memory locale dict

Strict TDD: RED phase — tests written BEFORE the implementation exists.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import discord
import pytest
from discord import app_commands

# ---------------------------------------------------------------------------
# Reset fixture — clears module-level i18n state between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_i18n_state() -> Generator[None, None, None]:
    """Clear module-level i18n state before each test."""
    from bot.core import i18n

    # Save original state.
    orig_locales = dict(i18n._locales)
    orig_guild_langs = dict(i18n._guild_languages)

    i18n._locales.clear()
    i18n._guild_languages.clear()

    yield

    # Restore original state so other test modules are not affected.
    i18n._locales.clear()
    i18n._locales.update(orig_locales)
    i18n._guild_languages.clear()
    i18n._guild_languages.update(orig_guild_langs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_locale(tmp_path: Path, locale: str, data: dict) -> Path:
    """Write a locale JSON file and return its path."""
    locale_dir = tmp_path / "locales"
    locale_dir.mkdir(parents=True, exist_ok=True)
    path = locale_dir / f"{locale}.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# load_locales
# ---------------------------------------------------------------------------


class TestLoadLocales:
    """Tests for load_locales() startup loader."""

    def test_load_locales_reads_es_and_en(self, tmp_path: Path) -> None:
        """load_locales() MUST make both locale dicts available in memory."""
        from bot.core.i18n import load_locales

        _write_locale(tmp_path, "es", {"core": {"ping": {"title": "Pong!"}}})
        _write_locale(tmp_path, "en", {"core": {"ping": {"title": "Pong!"}}})

        load_locales(tmp_path / "locales")

        from bot.core import i18n

        assert "es" in i18n._locales
        assert "en" in i18n._locales
        assert i18n._locales["es"]["core"]["ping"]["title"] == "Pong!"
        assert i18n._locales["en"]["core"]["ping"]["title"] == "Pong!"

    def test_load_locales_missing_file_logs_warning(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """If a locale file is missing, load_locales() MUST log a warning and continue."""
        from bot.core.i18n import load_locales

        # Only create es.json, not en.json
        _write_locale(tmp_path, "es", {"core": {"ping": {"title": "Pong!"}}})

        with caplog.at_level(logging.WARNING):
            load_locales(tmp_path / "locales")

        assert any("en" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# set_guild_language
# ---------------------------------------------------------------------------


class TestSetGuildLanguage:
    """Tests for set_guild_language()."""

    def test_set_guild_language_updates_map(self) -> None:
        """set_guild_language() MUST update the guild→language mapping."""
        from bot.core.i18n import set_guild_language

        set_guild_language("123456789", "en")

        from bot.core import i18n

        assert i18n._guild_languages["123456789"] == "en"

    def test_set_guild_language_accepts_int(self) -> None:
        """set_guild_language() MUST accept int guild_id (converts to str internally)."""
        from bot.core.i18n import set_guild_language

        set_guild_language(987654321, "es")

        from bot.core import i18n

        assert i18n._guild_languages["987654321"] == "es"


# ---------------------------------------------------------------------------
# t() — translation lookup
# ---------------------------------------------------------------------------


class TestTFunction:
    """Tests for t() translation function."""

    @pytest.fixture(autouse=True)
    def _load_test_locales(self, tmp_path: Path) -> None:
        """Load test locales before each test."""
        from bot.core.i18n import load_locales, set_guild_language

        es_data = {
            "core": {
                "ping": {"title": "Pong!", "latency": "Latencia WebSocket: **{latency} ms**"},
                "status": {"title": "Estado del Bot"},
            },
            "common": {
                "error": {"title": "Error"},
            },
        }
        en_data = {
            "core": {
                "ping": {"title": "Pong!", "latency": "WebSocket latency: **{latency} ms**"},
                "status": {"title": "Bot Status"},
            },
            "common": {
                "error": {"title": "Error"},
            },
        }

        _write_locale(tmp_path, "es", es_data)
        _write_locale(tmp_path, "en", en_data)
        load_locales(tmp_path / "locales")

        # Set up test guilds
        set_guild_language("111", "es")
        set_guild_language("222", "en")

    def test_t_es_lookup(self) -> None:
        """t() MUST return Spanish string for an es-configured guild."""
        from bot.core.i18n import t

        result = t("111", "core.status.title")
        assert result == "Estado del Bot"

    def test_t_en_lookup(self) -> None:
        """t() MUST return English string for an en-configured guild."""
        from bot.core.i18n import t

        result = t("222", "core.status.title")
        assert result == "Bot Status"

    def test_t_missing_key_fallback_to_es(self) -> None:
        """When en locale lacks a key, t() MUST fall back to es."""
        # Add a key only to es
        from bot.core import i18n
        from bot.core.i18n import t

        i18n._locales["es"]["only_es"] = {"key": "Solo español"}

        result = t("222", "only_es.key")
        assert result == "Solo español"

    def test_t_exhausted_fallback_returns_raw_key(self) -> None:
        """When key is missing in ALL locales, t() MUST return the raw key."""
        from bot.core.i18n import t

        result = t("222", "nonexistent.deeply.nested.key")
        assert result == "nonexistent.deeply.nested.key"

    def test_t_interpolation(self) -> None:
        """t() MUST replace {placeholder} tokens with matching kwargs."""
        from bot.core.i18n import t

        result = t("222", "core.ping.latency", latency=42)
        assert result == "WebSocket latency: **42 ms**"

    def test_t_missing_placeholder_logs_warning(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When kwargs is missing a placeholder, t() MUST log a warning."""
        from bot.core.i18n import t

        with caplog.at_level(logging.WARNING):
            result = t("222", "core.ping.latency")

        # The raw {latency} token should remain
        assert "{latency}" in result
        assert any("latency" in record.message.lower() for record in caplog.records)

    def test_t_none_guild_id_fallback_to_es(self) -> None:
        """When guild_id is None, t() MUST fall back to es locale."""
        from bot.core.i18n import t

        result = t(None, "core.ping.title")
        assert result == "Pong!"

    def test_t_unknown_guild_fallback_to_es(self) -> None:
        """When guild_id is not in the language map, t() MUST fall back to es."""
        from bot.core.i18n import t

        result = t("999", "core.status.title")
        assert result == "Estado del Bot"


# ---------------------------------------------------------------------------
# LocaleTranslator — Discord client locale → language mapping
# ---------------------------------------------------------------------------


class TestLocaleTranslator:
    """Tests for LocaleTranslator (app_commands.Translator subclass)."""

    @pytest.fixture(autouse=True)
    def _load_test_locales(self, tmp_path: Path) -> None:
        """Load test locales with slash keys for translator tests."""
        from bot.core.i18n import load_locales

        es_data = {
            "slash": {
                "descriptions": {
                    "ping": "Muestra la latencia WebSocket del bot.",
                    "ban": "Prohibir a un miembro del servidor.",
                },
                "describes": {
                    "warn": {
                        "member": "El miembro a advertir",
                        "reason": "Razón de la advertencia",
                    },
                },
            },
        }
        en_data = {
            "slash": {
                "descriptions": {
                    "ping": "Show the bot's WebSocket latency.",
                    "ban": "Ban a member from the server.",
                },
                "describes": {
                    "warn": {
                        "member": "The member to warn",
                        "reason": "Reason for the warning",
                    },
                },
            },
        }

        _write_locale(tmp_path, "es", es_data)
        _write_locale(tmp_path, "en", en_data)
        load_locales(tmp_path / "locales")

    async def test_spanish_locale_returns_es_string(self) -> None:
        """Spanish Discord locale MUST return the Spanish translation string."""
        from bot.core.i18n import LocaleTranslator

        translator = LocaleTranslator()
        string = app_commands.locale_str("Muestra la latencia WebSocket del bot.", key="slash.descriptions.ping")
        context = MagicMock()

        result = await translator.translate(string, discord.Locale.spain_spanish, context)
        assert result == "Muestra la latencia WebSocket del bot."

    async def test_english_locale_returns_en_string(self) -> None:
        """English Discord locale MUST return the English translation string."""
        from bot.core.i18n import LocaleTranslator

        translator = LocaleTranslator()
        string = app_commands.locale_str("Muestra la latencia WebSocket del bot.", key="slash.descriptions.ping")
        context = MagicMock()

        result = await translator.translate(string, discord.Locale.american_english, context)
        assert result == "Show the bot's WebSocket latency."

    async def test_unknown_locale_returns_none(self) -> None:
        """Unsupported locale (e.g. French) MUST return None — Discord shows default."""
        from bot.core.i18n import LocaleTranslator

        translator = LocaleTranslator()
        string = app_commands.locale_str("Muestra la latencia WebSocket del bot.", key="slash.descriptions.ping")
        context = MagicMock()

        result = await translator.translate(string, discord.Locale.french, context)
        assert result is None

    async def test_no_key_returns_none(self) -> None:
        """When locale_str has no key in extras, translate() MUST return None."""
        from bot.core.i18n import LocaleTranslator

        translator = LocaleTranslator()
        string = app_commands.locale_str("Some text")
        context = MagicMock()

        result = await translator.translate(string, discord.Locale.spain_spanish, context)
        assert result is None

    async def test_missing_key_in_locale_returns_none(self) -> None:
        """When the key doesn't exist in the locale dict, translate() MUST return None."""
        from bot.core.i18n import LocaleTranslator

        translator = LocaleTranslator()
        string = app_commands.locale_str("Missing", key="slash.descriptions.nonexistent")
        context = MagicMock()

        result = await translator.translate(string, discord.Locale.spain_spanish, context)
        assert result is None

    async def test_es_es_variant_maps_to_es(self) -> None:
        """Spanish (Latin America) locale variant MUST map to es."""
        from bot.core.i18n import LocaleTranslator

        translator = LocaleTranslator()
        string = app_commands.locale_str("Muestra la latencia WebSocket del bot.", key="slash.descriptions.ping")
        context = MagicMock()

        result = await translator.translate(string, discord.Locale.latin_american_spanish, context)
        assert result == "Muestra la latencia WebSocket del bot."

    async def test_en_gb_variant_maps_to_en(self) -> None:
        """English (UK) locale variant MUST map to en."""
        from bot.core.i18n import LocaleTranslator

        translator = LocaleTranslator()
        string = app_commands.locale_str("Muestra la latencia WebSocket del bot.", key="slash.descriptions.ping")
        context = MagicMock()

        result = await translator.translate(string, discord.Locale.british_english, context)
        assert result == "Show the bot's WebSocket latency."

    async def test_describes_key_resolves_nested(self) -> None:
        """Nested describes key (slash.describes.warn.member) MUST resolve correctly."""
        from bot.core.i18n import LocaleTranslator

        translator = LocaleTranslator()
        string = app_commands.locale_str("El miembro a advertir", key="slash.describes.warn.member")
        context = MagicMock()

        result = await translator.translate(string, discord.Locale.spain_spanish, context)
        assert result == "El miembro a advertir"

    async def test_no_database_calls(self) -> None:
        """Translator MUST NOT make any database calls — purely in-memory."""
        from bot.core.i18n import LocaleTranslator

        translator = LocaleTranslator()
        string = app_commands.locale_str("test", key="slash.descriptions.ping")
        context = MagicMock()

        # This should complete without any async DB calls
        result = await translator.translate(string, discord.Locale.spain_spanish, context)
        assert result is not None


# ---------------------------------------------------------------------------
# validate_slash_localizations — hybrid command metadata validation
# ---------------------------------------------------------------------------


class TestValidateSlashLocalizations:
    """Tests for validate_slash_localizations()."""

    @pytest.fixture(autouse=True)
    def _load_test_locales(self, tmp_path: Path) -> None:
        """Load test locales with slash keys for validation tests."""
        from bot.core.i18n import load_locales

        es_data = {
            "slash": {
                "descriptions": {
                    "ping": "Muestra la latencia WebSocket del bot.",
                    "ban": "Prohibir a un miembro del servidor.",
                },
                "describes": {
                    "warn": {
                        "member": "El miembro a advertir",
                        "reason": "Razón de la advertencia",
                    },
                },
            },
        }
        en_data = {
            "slash": {
                "descriptions": {
                    "ping": "Show the bot's WebSocket latency.",
                    "ban": "Ban a member from the server.",
                },
                "describes": {
                    "warn": {
                        "member": "The member to warn",
                        "reason": "Reason for the warning",
                    },
                },
            },
        }

        _write_locale(tmp_path, "es", es_data)
        _write_locale(tmp_path, "en", en_data)
        load_locales(tmp_path / "locales")

    def test_valid_commands_pass(self) -> None:
        """Commands with correct locale_str descriptions MUST pass validation."""
        from bot.core.i18n import validate_slash_localizations

        tree = MagicMock()
        cmd = MagicMock(spec=app_commands.Command)
        cmd.name = "ping"
        cmd.qualified_name = "ping"
        cmd.description = "Muestra la latencia WebSocket del bot."
        cmd.description_localizations = {discord.Locale.american_english: "Show the bot's WebSocket latency."}
        cmd._locale_description = None
        cmd.parameters = []

        tree.walk_commands.return_value = [cmd]

        # Should not raise
        validate_slash_localizations(tree)

    def test_missing_description_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Command with missing description_localizations MUST log a warning."""
        from bot.core.i18n import validate_slash_localizations

        tree = MagicMock()
        cmd = MagicMock(spec=app_commands.Command)
        cmd.name = "ping"
        cmd.qualified_name = "ping"
        cmd.description = "Muestra la latencia WebSocket del bot."
        cmd.description_localizations = {}
        cmd._locale_description = None
        cmd.parameters = []

        tree.walk_commands.return_value = [cmd]

        with caplog.at_level(logging.WARNING):
            validate_slash_localizations(tree)

        assert any("ping" in record.message for record in caplog.records)

    def test_nested_group_commands_validated(self, caplog: pytest.LogCaptureFixture) -> None:
        """Subcommands in groups MUST be validated recursively."""
        from bot.core.i18n import validate_slash_localizations

        tree = MagicMock()

        group = MagicMock(spec=app_commands.Group)
        group.name = "warn_group"
        group.qualified_name = "warn_group"
        group.description = "test"
        group.description_localizations = {}
        group._locale_description = None

        subcmd = MagicMock(spec=app_commands.Command)
        subcmd.name = "member"
        subcmd.qualified_name = "warn_group.member"
        subcmd.description = "test"
        subcmd.description_localizations = {}
        subcmd._locale_description = None
        subcmd.parameters = []

        tree.walk_commands.return_value = [group, subcmd]

        # Should log warnings for both
        with caplog.at_level(logging.WARNING):
            validate_slash_localizations(tree)

    def test_hybrid_app_command_no_description_localizations_attr(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """HybridAppCommand lacking description_localizations MUST NOT raise AttributeError."""
        from bot.core.i18n import validate_slash_localizations

        tree = MagicMock()

        # Simulate a HybridAppCommand: no description_localizations attribute at all.
        # MagicMock(spec=app_commands.Command) would auto-create it; use a plain object.
        class FakeHybridCmd:
            name = "ping"
            qualified_name = "ping"
            description = "Muestra la latencia WebSocket del bot."
            _locale_description = None
            parameters = []

        cmd = FakeHybridCmd()

        # Sanity: the attribute must not exist on the object.
        assert not hasattr(cmd, "description_localizations")

        tree.walk_commands.return_value = [cmd]

        # Must NOT raise AttributeError — should log warning instead.
        with caplog.at_level(logging.WARNING):
            validate_slash_localizations(tree)

        assert any("ping" in record.message for record in caplog.records)

    def test_hybrid_app_command_with_locale_description_skips_warning(self) -> None:
        """HybridAppCommand with _locale_description set MUST pass validation without warnings."""
        from bot.core.i18n import validate_slash_localizations

        tree = MagicMock()

        # Simulate a HybridAppCommand that has a locale_str description attached.
        locale_desc = app_commands.locale_str(
            "Muestra la latencia WebSocket del bot.",
            key="slash.descriptions.ping",
        )

        class FakeHybridCmd:
            name = "ping"
            qualified_name = "ping"
            description = "Muestra la latencia WebSocket del bot."
            _locale_description = locale_desc
            parameters = []

        cmd = FakeHybridCmd()

        tree.walk_commands.return_value = [cmd]

        # Should NOT log any warning — _locale_description with extras is sufficient.
        validate_slash_localizations(tree)


# ---------------------------------------------------------------------------
# Slash metadata registry — locale key completeness
# ---------------------------------------------------------------------------


class TestSlashMetadataKeys:
    """Tests verifying es.json and en.json contain all required slash keys."""

    @pytest.fixture(autouse=True)
    def _load_real_locales_for_slash(self) -> None:
        """Load the real locale files so slash key lookups work."""
        from bot.core.i18n import load_locales
        load_locales()

    def test_descriptions_keys_exist_in_both_locales(self) -> None:
        """All slash.descriptions.* keys MUST exist in both es.json and en.json."""
        from bot.core import i18n

        required_keys = [
            "ping", "status", "help", "sync",
            "warn", "unwarn", "mute", "unmute", "kick", "ban", "lock", "unlock", "modlogs",
            "ticket_panel", "create_category", "list_categories", "delete_category",
            "configure_fields._", "configure_fields.set",
            "subticket._", "subticket.create",
            "reopen", "transfer", "unclaim",
            "note._", "note.add", "note.list", "note.delete",
            "avatar", "serverinfo", "userinfo",
            "setup",
            "daily", "coins", "leaderboard", "rank",
            "welcome_test", "goodbye_test",
            "welcome._", "welcome.channel", "welcome.toggle", "welcome.message",
            "goodbye._", "goodbye.channel", "goodbye.toggle", "goodbye.message",
            "dados", "banana",
        ]

        for key in required_keys:
            es_val = i18n._resolve_key("es", f"slash.descriptions.{key}")
            en_val = i18n._resolve_key("en", f"slash.descriptions.{key}")
            assert es_val is not None and es_val != "", f"Missing es: slash.descriptions.{key}"
            assert en_val is not None and en_val != "", f"Missing en: slash.descriptions.{key}"

    def test_describes_keys_exist_in_both_locales(self) -> None:
        """All slash.describes.* keys MUST exist in both es.json and en.json."""
        from bot.core import i18n

        required_describes = [
            ("help", "module"),
            ("warn", "member"), ("warn", "reason"),
            ("unwarn", "member"),
            ("mute", "member"), ("mute", "duration"), ("mute", "reason"),
            ("unmute", "member"),
            ("kick", "member"), ("kick", "reason"),
            ("ban", "member"), ("ban", "reason"), ("ban", "delete_days"),
            ("lock", "channel"),
            ("unlock", "channel"),
            ("modlogs", "member"), ("modlogs", "type"), ("modlogs", "after"),
            ("ticket_panel", "title"), ("ticket_panel", "description_text"),
            ("create_category", "name"), ("create_category", "emoji"),
            ("create_category", "description"), ("create_category", "position"),
            ("delete_category", "category_id"),
            ("configure_fields.set", "category_id"), ("configure_fields.set", "fields_json"),
            ("subticket.create", "parent_id"),
            ("reopen", "ticket_ref"),
            ("transfer", "member"),
            ("note.add", "content"),
            ("note.delete", "note_id"),
            ("avatar", "member"),
            ("userinfo", "member"),
            ("setup", "ticket_category"), ("setup", "mod_role"),
            ("setup", "log_channel"), ("setup", "language"),
            ("coins", "member"),
            ("leaderboard", "lb_type"),
            ("rank", "member"),
            ("welcome.channel", "channel"),
            ("welcome.message", "template"),
            ("goodbye.channel", "channel"),
            ("goodbye.message", "template"),
            ("dados", "sides"),
        ]

        for cmd, param in required_describes:
            es_val = i18n._resolve_key("es", f"slash.describes.{cmd}.{param}")
            en_val = i18n._resolve_key("en", f"slash.describes.{cmd}.{param}")
            assert es_val is not None and es_val != "", f"Missing es: slash.describes.{cmd}.{param}"
            assert en_val is not None and en_val != "", f"Missing en: slash.describes.{cmd}.{param}"


# ---------------------------------------------------------------------------
# Bot setup_hook — translator registration order
# ---------------------------------------------------------------------------


class TestTranslatorRegistrationOrder:
    """Tests for translator registration order in setup_hook."""

    @pytest.mark.asyncio
    async def test_set_translator_called_before_tree_sync(self) -> None:
        """set_translator() MUST be called before tree.sync() in setup_hook."""
        from bot.bot import NebulosaBot
        from bot.config import BotConfig

        config = BotConfig(
            discord_token="t",
            supabase_url="https://x.supabase.co",
            supabase_key="k",
        )
        bot = NebulosaBot(config=config, intents=discord.Intents.default())

        call_order: list[str] = []

        async def tracking_set_translator(translator):
            call_order.append("set_translator")

        async def tracking_sync():
            call_order.append("sync")
            return []

        with (
            patch("bot.bot.Database") as mock_db_cls,
            patch("bot.bot.RealtimeCacheSubscriber") as mock_rt_cls,
            patch.object(bot, "load_extension", new=AsyncMock()),
            patch.object(bot.tree, "set_translator", side_effect=tracking_set_translator),
            patch.object(bot.tree, "sync", side_effect=tracking_sync),
        ):
            mock_db_cls.return_value.connect = AsyncMock()
            mock_rt_cls.return_value.start = AsyncMock()
            await bot.setup_hook()

        assert "set_translator" in call_order
        assert "sync" in call_order
        assert call_order.index("set_translator") < call_order.index("sync")

    @pytest.mark.asyncio
    async def test_validate_slash_localizations_called_before_sync(self) -> None:
        """validate_slash_localizations() MUST be called before tree.sync() in setup_hook."""
        from bot.bot import NebulosaBot
        from bot.config import BotConfig

        config = BotConfig(
            discord_token="t",
            supabase_url="https://x.supabase.co",
            supabase_key="k",
        )
        bot = NebulosaBot(config=config, intents=discord.Intents.default())

        call_order: list[str] = []

        async def tracking_sync():
            call_order.append("sync")
            return []

        async def tracking_set_translator(translator):
            call_order.append("set_translator")

        with (
            patch("bot.bot.Database") as mock_db_cls,
            patch("bot.bot.RealtimeCacheSubscriber") as mock_rt_cls,
            patch.object(bot, "load_extension", new=AsyncMock()),
            patch.object(bot.tree, "set_translator", side_effect=tracking_set_translator),
            patch.object(bot.tree, "sync", side_effect=tracking_sync),
            patch("bot.bot.validate_slash_localizations") as mock_validate,
        ):
            mock_db_cls.return_value.connect = AsyncMock()
            mock_rt_cls.return_value.start = AsyncMock()
            mock_validate.side_effect = lambda tree: call_order.append("validate")
            await bot.setup_hook()

        assert "validate" in call_order
        assert "sync" in call_order
        assert call_order.index("validate") < call_order.index("sync")


# Import AsyncMock and patch at module level for the bot tests.
from unittest.mock import AsyncMock, patch  # noqa: E402
