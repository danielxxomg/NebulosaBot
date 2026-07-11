"""Internationalization module for NebulosaBot.

Provides a synchronous, in-memory translation system backed by JSON locale
files loaded at startup.  Guild language preferences are maintained by
:class:`~bot.services.guild_service.GuildService` and published to this
module via :func:`set_guild_language`.

Design contract (from ``design.md``)::

    load_locales(locales_dir: Path | None = None) -> None
    set_guild_language(guild_id: str | int, language: str) -> None
    t(guild_id: str | int | None, key: str, **kwargs: object) -> str

Locale files use nested JSON addressed by flat dot-notation keys
(e.g. ``core.ping.title``).  The fallback chain is:

    1. Guild language → locale dict
    2. Missing key → ``es`` locale
    3. Key missing everywhere → raw key string
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Module-level state --------------------------------------------------------

# Locale dictionaries keyed by locale code ("es", "en").
_locales: dict[str, dict[str, Any]] = {}

# Guild ID (str) → language code ("es", "en").
_guild_languages: dict[str, str] = {}

# Default fallback locale per design decisions.
_DEFAULT_LOCALE = "es"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_locales(locales_dir: Path | None = None) -> None:
    """Load ``*.json`` locale files from *locales_dir* into memory.

    Called once during ``setup_hook()`` before cog loading.  Missing files
    log a warning and are skipped — the bot continues with whatever locales
    are available.

    Args:
        locales_dir: Path to the directory containing ``es.json``,
            ``en.json``, etc.  Defaults to ``bot/locales`` relative to cwd.
    """
    if locales_dir is None:
        locales_dir = Path("bot/locales")

    # Clear previous state so a restart (or test) starts clean.
    _locales.clear()

    for locale_file in locales_dir.glob("*.json"):
        locale_code = locale_file.stem
        try:
            data = json.loads(locale_file.read_text(encoding="utf-8"))
            _locales[locale_code] = data
            logger.info("Loaded locale: %s (%s)", locale_code, locale_file)
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to load locale file: %s", locale_file)

    # Warn about expected locales that didn't load.
    for expected in ("es", "en"):
        if expected not in _locales:
            logger.warning("Locale file not found for '%s' — skipping", expected)


def set_guild_language(guild_id: str | int, language: str) -> None:
    """Update the guild→language mapping.

    Called by :class:`~bot.services.guild_service.GuildService` whenever a
    guild config is loaded, saved, or created (``get_config``,
    ``save_config``, ``on_guild_join``, startup backfill).

    Args:
        guild_id: Discord guild ID (str or int).
        language: Locale code (``"es"`` or ``"en"``).
    """
    _guild_languages[str(guild_id)] = language


def t(
    guild_id: str | int | None,
    key: str,
    **kwargs: object,
) -> str:
    """Translate *key* for the guild's configured language.

    Resolution order:
        1. Look up guild language from the in-memory map.
        2. If guild_id is ``None`` or unknown, fall back to ``es``.
        3. Look up *key* in the locale dict using dot-notation.
        4. If missing, fall back to ``es`` locale.
        5. If still missing, return the raw *key* string.
        6. Interpolate ``{placeholder}`` tokens from *kwargs*.

    Args:
        guild_id: Discord guild ID, or ``None`` for default locale.
        key: Dot-notation locale key (e.g. ``core.ping.title``).
        **kwargs: Placeholder values for string interpolation.

    Returns:
        The localized (and interpolated) string, or the raw key on miss.
    """
    # Resolve language.
    lang = _DEFAULT_LOCALE
    if guild_id is not None:
        lang = _guild_languages.get(str(guild_id), _DEFAULT_LOCALE)

    # Resolve the nested value from the locale dict.
    value = _resolve_key(lang, key)

    # Fallback to default locale if missing.
    if value is None and lang != _DEFAULT_LOCALE:
        value = _resolve_key(_DEFAULT_LOCALE, key)

    # Exhausted fallback — return raw key.
    if value is None:
        logger.warning("Missing i18n key '%s' in all locales", key)
        return key

    # Interpolate placeholders.  Always attempt if the string contains
    # tokens — even when kwargs is empty — so missing placeholders are
    # detected and logged rather than silently returned raw.
    if "{" in value:
        try:
            return value.format_map(kwargs)
        except KeyError as exc:
            logger.warning(
                "Missing placeholder %s in i18n key '%s' (lang=%s)",
                exc,
                key,
                lang,
            )
            return value

    return value


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_key(lang: str, key: str) -> str | None:
    """Walk *key* (dot-notation) through the locale dict for *lang*.

    Returns the string value, or ``None`` if any segment is missing.
    """
    locale = _locales.get(lang)
    if locale is None:
        return None

    parts = key.split(".")
    current: object = locale
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None

    return str(current) if not isinstance(current, str) else current
