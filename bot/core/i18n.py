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

import discord
from discord import app_commands

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


# ---------------------------------------------------------------------------
# LocaleTranslator — discord.py app_commands.Translator
# ---------------------------------------------------------------------------


# Discord locale variants that map to our supported languages.
# Discord uses hyphenated locale codes (e.g., "es-ES", "en-US").
_SPANISH_LOCALES: frozenset[str] = frozenset({
    "es-ES", "es-419", "es-MX", "es-AR", "es-CL", "es-CO",
    "es-CR", "es-DO", "es-EC", "es-GT", "es-HN", "es-NI", "es-PA",
    "es-PE", "es-PR", "es-PY", "es-SV", "es-UY", "es-VE",
})

_ENGLISH_LOCALES: frozenset[str] = frozenset({
    "en-US", "en-GB", "en-AU", "en-CA", "en-IN", "en-NZ",
    "en-PH", "en-SG", "en-ZA",
})

# Reverse map: Discord locale value → our language code.
_LOCALE_MAP: dict[str, str] = {loc: "es" for loc in _SPANISH_LOCALES}
_LOCALE_MAP.update({loc: "en" for loc in _ENGLISH_LOCALES})


class LocaleTranslator(app_commands.Translator):
    """Resolve ``locale_str`` keys from in-memory locale dictionaries.

    Reads the key from ``string.extras["key"]``, maps the Discord client
    locale to our supported language codes (``es`` or ``en``), and returns
    the translated string.  Returns ``None`` for unsupported locales so
    Discord falls back to the default (Spanish) message.

    Must NOT make database calls — all data is in-memory after startup.
    """

    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContextTypes,
    ) -> str | None:
        """Translate *string* for the given Discord *locale*.

        Args:
            string: The ``locale_str`` carrying the key in ``extras["key"]``.
            locale: The user's Discord client locale.
            context: Translation context (unused — in-memory only).

        Returns:
            The translated string, or ``None`` if the locale is unsupported
            or the key is missing.
        """
        key = string.extras.get("key") if string.extras else None
        if key is None:
            return None

        # Map Discord locale to our language code.
        lang = _LOCALE_MAP.get(str(locale))
        if lang is None:
            return None

        value = _resolve_key(lang, key)
        return value


# ---------------------------------------------------------------------------
# validate_slash_localizations — post-registration metadata check
# ---------------------------------------------------------------------------


def validate_slash_localizations(
    tree: app_commands.CommandTree[discord.Client],
) -> None:
    """Validate that all app commands have ``description_localizations``.

    Iterates every command in the tree and logs an error for any command
    whose ``description_localizations`` dict is empty.  This is a
    version-guarded compatibility check — on supported discord.py versions
    the hybrid decorators attach locale objects automatically.

    Args:
        tree: The bot's command tree to validate.
    """
    for cmd in tree.walk_commands():
        _check_localizations(cmd)


def _check_localizations(cmd: app_commands.Command | app_commands.Group) -> None:
    """Check and log if a command is missing description localizations.

    Safe for ``HybridAppCommand`` instances which do not expose a
    ``description_localizations`` attribute — we fall back to checking
    ``_locale_description`` for a ``locale_str`` with an extras key.
    """
    # HybridAppCommand (and plain Command) may not have
    # description_localizations as an instance attr. Use getattr.
    localizations = getattr(cmd, "description_localizations", None)

    # If there's a dict with content, the command is localized.
    if localizations:
        return

    # Fallback: check if a locale_str description was attached (discord.py
    # stores it on _locale_description when description= is a locale_str).
    locale_desc = getattr(cmd, "_locale_description", None)
    if locale_desc is not None and getattr(locale_desc, "extras", None):
        return

    logger.warning(
        "Command '%s' is missing description localization — "
        "slash metadata will not localize for non-default locales",
        cmd.qualified_name,
    )


# ---------------------------------------------------------------------------
# Slash metadata registry — maps qualified command name → locale key
# ---------------------------------------------------------------------------

# Registry of locale keys for slash command descriptions and parameter
# descriptions.  Used by validate_slash_localizations() to inject
# description_localizations into hybrid commands that did not retain
# their locale_str objects after registration.
#
# Format:
#   "qualified_name": {"description": "slash.descriptions.xxx", "params": {"param": "slash.describes.xxx.yyy"}}

SLASH_DESCRIPTIONS: dict[str, str] = {
    # Core
    "ping": "slash.descriptions.ping",
    "status": "slash.descriptions.status",
    "help": "slash.descriptions.help",
    "sync": "slash.descriptions.sync",
    # Sentinel
    "warn": "slash.descriptions.warn",
    "unwarn": "slash.descriptions.unwarn",
    "mute": "slash.descriptions.mute",
    "unmute": "slash.descriptions.unmute",
    "kick": "slash.descriptions.kick",
    "ban": "slash.descriptions.ban",
    "lock": "slash.descriptions.lock",
    "unlock": "slash.descriptions.unlock",
    "modlogs": "slash.descriptions.modlogs",
    # Tickets
    "ticket_panel": "slash.descriptions.ticket_panel",
    "create_category": "slash.descriptions.create_category",
    "list_categories": "slash.descriptions.list_categories",
    "delete_category": "slash.descriptions.delete_category",
    "configure_fields": "slash.descriptions.configure_fields._",
    "configure_fields set": "slash.descriptions.configure_fields.set",
    "subticket": "slash.descriptions.subticket._",
    "subticket create": "slash.descriptions.subticket.create",
    "reopen": "slash.descriptions.reopen",
    "transfer": "slash.descriptions.transfer",
    "unclaim": "slash.descriptions.unclaim",
    "note": "slash.descriptions.note._",
    "note add": "slash.descriptions.note.add",
    "note list": "slash.descriptions.note.list",
    "note delete": "slash.descriptions.note.delete",
    # Utility
    "avatar": "slash.descriptions.avatar",
    "serverinfo": "slash.descriptions.serverinfo",
    "userinfo": "slash.descriptions.userinfo",
    # Setup
    "setup": "slash.descriptions.setup",
    # Stellar
    "daily": "slash.descriptions.daily",
    "coins": "slash.descriptions.coins",
    "leaderboard": "slash.descriptions.leaderboard",
    "rank": "slash.descriptions.rank",
    # Greetings
    "welcome_test": "slash.descriptions.welcome_test",
    "goodbye_test": "slash.descriptions.goodbye_test",
    "welcome": "slash.descriptions.welcome._",
    "welcome channel": "slash.descriptions.welcome.channel",
    "welcome toggle": "slash.descriptions.welcome.toggle",
    "welcome message": "slash.descriptions.welcome.message",
    "goodbye": "slash.descriptions.goodbye._",
    "goodbye channel": "slash.descriptions.goodbye.channel",
    "goodbye toggle": "slash.descriptions.goodbye.toggle",
    "goodbye message": "slash.descriptions.goodbye.message",
    # Ocío
    "dados": "slash.descriptions.dados",
    "banana": "slash.descriptions.banana",
}

SLASH_DESCRIBES: dict[str, dict[str, str]] = {
    # Core
    "help": {"module": "slash.describes.help.module"},
    # Sentinel
    "warn": {"member": "slash.describes.warn.member", "reason": "slash.describes.warn.reason"},
    "unwarn": {"member": "slash.describes.unwarn.member"},
    "mute": {
        "member": "slash.describes.mute.member",
        "duration": "slash.describes.mute.duration",
        "reason": "slash.describes.mute.reason",
    },
    "unmute": {"member": "slash.describes.unmute.member"},
    "kick": {"member": "slash.describes.kick.member", "reason": "slash.describes.kick.reason"},
    "ban": {
        "member": "slash.describes.ban.member",
        "reason": "slash.describes.ban.reason",
        "delete_days": "slash.describes.ban.delete_days",
    },
    "lock": {"channel": "slash.describes.lock.channel"},
    "unlock": {"channel": "slash.describes.unlock.channel"},
    "modlogs": {
        "member": "slash.describes.modlogs.member",
        "type": "slash.describes.modlogs.type",
        "after": "slash.describes.modlogs.after",
    },
    # Tickets
    "ticket_panel": {
        "title": "slash.describes.ticket_panel.title",
        "description_text": "slash.describes.ticket_panel.description_text",
    },
    "create_category": {
        "name": "slash.describes.create_category.name",
        "emoji": "slash.describes.create_category.emoji",
        "description": "slash.describes.create_category.description",
        "position": "slash.describes.create_category.position",
    },
    "delete_category": {"category_id": "slash.describes.delete_category.category_id"},
    "configure_fields set": {
        "category_id": "slash.describes.configure_fields.set.category_id",
        "fields_json": "slash.describes.configure_fields.set.fields_json",
    },
    "subticket create": {"parent_id": "slash.describes.subticket.create.parent_id"},
    "reopen": {"ticket_ref": "slash.describes.reopen.ticket_ref"},
    "transfer": {"member": "slash.describes.transfer.member"},
    "note add": {"content": "slash.describes.note.add.content"},
    "note delete": {"note_id": "slash.describes.note.delete.note_id"},
    # Utility
    "avatar": {"member": "slash.describes.avatar.member"},
    "userinfo": {"member": "slash.describes.userinfo.member"},
    # Setup
    "setup": {
        "ticket_category": "slash.describes.setup.ticket_category",
        "mod_role": "slash.describes.setup.mod_role",
        "log_channel": "slash.describes.setup.log_channel",
        "language": "slash.describes.setup.language",
    },
    # Stellar
    "coins": {"member": "slash.describes.coins.member"},
    "leaderboard": {"lb_type": "slash.describes.leaderboard.lb_type"},
    "rank": {"member": "slash.describes.rank.member"},
    # Greetings
    "welcome channel": {"channel": "slash.describes.welcome.channel.channel"},
    "welcome message": {"template": "slash.describes.welcome.message.template"},
    "goodbye channel": {"channel": "slash.describes.goodbye.channel.channel"},
    "goodbye message": {"template": "slash.describes.goodbye.message.template"},
    # Ocío
    "dados": {"sides": "slash.describes.dados.sides"},
}
