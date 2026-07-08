"""Unit tests for bot.core.i18n — internationalization module.

Covers:
    - load_locales() — loads JSON files into memory
    - set_guild_language() — updates guild→language map
    - t() — Spanish lookup, English lookup, missing-key fallback to es,
      exhausted fallback returns raw key, interpolation, missing placeholder
      warning, None guild_id fallback

Strict TDD: RED phase — tests written BEFORE the implementation exists.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Reset fixture — clears module-level i18n state between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_i18n_state() -> None:
    """Clear module-level i18n state before each test."""
    from bot.core import i18n

    i18n._locales.clear()
    i18n._guild_languages.clear()


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
