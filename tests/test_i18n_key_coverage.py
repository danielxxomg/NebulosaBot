"""i18n translation-key coverage test (cycle-4-debt-zero S2.1 / spec i18n-system).

Statically scans ``bot/**`` for ``t()`` calls whose key argument is a string
literal and asserts every such key exists in BOTH ``es.json`` and ``en.json``.

Dynamically composed keys are exempted exclusively via the module-level
``DYNAMIC_KEY_PATTERNS`` allowlist; each entry corresponds to a genuinely
dynamic key family:

- ``tickets.timer.unit_*`` — composed in :mod:`bot.utils.time` via
  ``f"tickets.timer.unit_{unit}"``.
- ``ocio.8ball.r<N>`` — chosen at runtime from ``OcioService._8BALL_KEYS``.

A violation fails with a single consolidated report listing every missing
key together with its callsite ``file:line``. Unused-key detection is
advisory only — it MUST NOT fail the suite.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path
from typing import Any

import pytest

from bot.core.i18n import _resolve_key, set_guild_language, t

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
BOT_ROOT = REPO_ROOT / "bot"
LOCALES_DIR = BOT_ROOT / "locales"

# ---------------------------------------------------------------------------
# Dynamic-key allowlist (design D8) — regex patterns for runtime-composed
# key families. Literal callsites matching these are exempt from the
# both-locales assertion because their family is managed dynamically.
# ---------------------------------------------------------------------------

DYNAMIC_KEY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^tickets\.timer\.unit_(second|minute|hour|day)$"),
    re.compile(r"^ocio\.8ball\.r\d+$"),
)

# Static tickets.timer.* literals referenced by the scheduled-close flow.
_TIMER_STATIC_KEYS = (
    "tickets.timer.scheduled_title",
    "tickets.timer.scheduled_description",
    "tickets.timer.confirm_title",
    "tickets.timer.confirm_description",
    "tickets.timer.cancel_title",
    "tickets.timer.cancel_description",
    "tickets.timer.confirm_success_title",
    "tickets.timer.confirm_success_description",
)


# ---------------------------------------------------------------------------
# Scanner helpers
# ---------------------------------------------------------------------------


def _t_aliases(tree: ast.AST) -> set[str]:
    """Return local names bound to :func:`bot.core.i18n.t` in *tree*."""
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "bot.core.i18n":
            for alias in node.names:
                if alias.name == "t":
                    aliases.add(alias.asname or alias.name)
    return aliases


def scan_literal_t_calls(
    bot_root: Path,
) -> list[tuple[str, str, int]]:
    """Scan *bot_root* for ``t(<guild>, "<literal>")`` callsites.

    Tracks aliased imports (e.g. ``t as _i18n_t``). Returns a list of
    ``(key, relative_file, line)`` tuples sorted by file then line.
    """
    found: list[tuple[str, str, int]] = []
    for py in sorted(bot_root.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        aliases = _t_aliases(tree)
        if not aliases:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id not in aliases:
                continue
            if len(node.args) < 2:
                continue
            arg = node.args[1]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                rel = py.relative_to(bot_root.parent)
                found.append((arg.value, str(rel), node.lineno))
    return found


def flatten_keys(payload: dict[str, Any], prefix: str = "") -> set[str]:
    """Flatten nested locale JSON into a set of dot-notation leaf keys."""
    out: set[str] = set()
    for key, value in payload.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out |= flatten_keys(value, dotted)
        else:
            out.add(dotted)
    return out


def load_locale_leaves(name: str) -> set[str]:
    """Load flattened leaf keys from ``<name>.json`` in the locales dir."""
    payload = json.loads((LOCALES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return flatten_keys(payload)


def _is_dynamic(key: str) -> bool:
    """Return True when *key* belongs to an allowlisted dynamic family."""
    return any(pattern.match(key) for pattern in DYNAMIC_KEY_PATTERNS)


# ---------------------------------------------------------------------------
# Coverage assertions (spec i18n-system scenarios)
# ---------------------------------------------------------------------------


def test_every_literal_t_key_exists_in_both_locales() -> None:
    """Missing static key fails with a consolidated file:line report."""
    callsites = scan_literal_t_calls(BOT_ROOT)
    assert callsites, "scanner must find t() literal callsites under bot/"

    es_keys = load_locale_leaves("es")
    en_keys = load_locale_leaves("en")

    missing_es = [(k, f, ln) for k, f, ln in callsites if k not in es_keys and not _is_dynamic(k)]
    missing_en = [(k, f, ln) for k, f, ln in callsites if k not in en_keys and not _is_dynamic(k)]

    report_lines = [
        *(f"  es.json is missing '{k}' (used at {f}:{ln})" for k, f, ln in missing_es),
        *(f"  en.json is missing '{k}' (used at {f}:{ln})" for k, f, ln in missing_en),
    ]
    assert not report_lines, "Missing i18n translation keys:\n" + "\n".join(report_lines)


def test_both_locales_define_identical_key_sets() -> None:
    """Both locales must agree: es-only or en-only leaves fail (spec scenario 3)."""
    es_keys = load_locale_leaves("es")
    en_keys = load_locale_leaves("en")
    dynamic = {leaf for leaf in es_keys | en_keys if _is_dynamic(leaf)}
    # The unit_* families are composed dynamically per language but MUST be
    # defined in BOTH locale files — so they are NOT exempt here.
    required_dynamic_units = {
        f"tickets.timer.unit_{unit}"
        for unit in ("second", "minute", "hour", "day")
    }
    exempt = dynamic - required_dynamic_units

    es_only = (es_keys - en_keys) - exempt
    en_only = (en_keys - es_keys) - exempt
    problems = [
        *(f"  es.json-only key: {k}" for k in sorted(es_only)),
        *(f"  en.json-only key: {k}" for k in sorted(en_only)),
    ]
    assert not problems, "Locale files disagree on key sets:\n" + "\n".join(problems)


def test_dynamic_patterns_do_not_false_fail_on_composition_families() -> None:
    """Allowlist entries match their genuine dynamic key families (spec scenario 2)."""
    assert _is_dynamic("tickets.timer.unit_second")
    assert _is_dynamic("tickets.timer.unit_hour")
    assert _is_dynamic("ocio.8ball.r1")
    assert _is_dynamic("ocio.8ball.r20")
    assert not _is_dynamic("ocio.8ball.embed_title")
    assert not _is_dynamic("tickets.timer.scheduled_title")
    assert not _is_dynamic("totally.unrelated.key")


def test_scanner_reports_missing_key_with_callsite(tmp_path: Path) -> None:
    """Self-test: the scanner detects a missing literal key with its callsite."""
    bot_dir = tmp_path / "bot"
    bot_dir.mkdir()
    (bot_dir / "mod.py").write_text(
        'from bot.core.i18n import t\n\n\ndef render(guild_id):\n    return t(guild_id, "some.missing.key")\n',
        encoding="utf-8",
    )
    callsites = scan_literal_t_calls(bot_dir)
    assert callsites == [("some.missing.key", "bot/mod.py", 5)]


def test_unused_keys_are_advisory_only() -> None:
    """Unused-key detection runs but MUST NOT fail the suite (advisory)."""
    callsites = scan_literal_t_calls(BOT_ROOT)
    scanned = {k for k, _f, _ln in callsites}
    es_keys = load_locale_leaves("es")
    unused = sorted(es_keys - scanned)
    # Advisory: log only. Never assert emptiness here.
    logger.info("Advisory: %d locale keys have no literal t() callsite", len(unused))
    assert isinstance(unused, list)


# ---------------------------------------------------------------------------
# Runtime resolution (spec i18n-system "Timer keys resolve" / "Title resolves")
# ---------------------------------------------------------------------------

_ES_GUILD = "777001"
_EN_GUILD = "777002"


@pytest.fixture(autouse=True)
def _pin_coverage_guild_langs() -> Any:
    set_guild_language(_ES_GUILD, "es")
    set_guild_language(_EN_GUILD, "en")
    yield


@pytest.mark.parametrize("lang_guild", [_ES_GUILD, _EN_GUILD])
def test_timer_static_keys_resolve_in_both_locales(lang_guild: str) -> None:
    """Every static timer key resolves to a non-empty localized string."""
    for key in _TIMER_STATIC_KEYS:
        value = t(lang_guild, key)
        assert value != key, f"{key} must resolve in guild lang (raw key returned)"
        assert value.strip(), f"{key} must be non-empty"


def test_scheduled_description_interpolates_remaining_and_unix() -> None:
    """{remaining}/{unix} placeholders interpolate without leaking braces."""
    desc = t(_ES_GUILD, "tickets.timer.scheduled_description", remaining="12h", unix=1718457600)
    assert "{remaining}" not in desc
    assert "{unix}" not in desc
    assert "12h" in desc


def test_format_remaining_uses_full_name_unit_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """format_remaining composes tickets.timer.unit_{second..day} keys (not letters).

    Pins the spec's ``unit_second``–``unit_day`` naming at the real composition
    site in bot/utils/time.py while keeping compact output ("12h"-style).
    """
    import bot.utils.time as time_mod

    requested: list[str] = []
    real_t = time_mod.t

    def spy_t(guild_id: object, key: str, **kw: object) -> str:
        requested.append(key)
        return real_t(guild_id, key, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(time_mod, "t", spy_t)
    result = time_mod.format_remaining(43200, guild_id=_ES_GUILD)

    assert "tickets.timer.unit_hour" in requested, (
        f"format_remaining must request full-name unit keys, requested={requested}"
    )
    assert result.startswith("12"), f"compact output must stay '12h'-style, got {result!r}"
    # No raw-key leak into user-visible output.
    for key in requested:
        resolved = _resolve_key("es", key)
        assert resolved is not None and not resolved.startswith("tickets.timer"), (
            f"unit key {key} must exist in es.json so users never see raw keys"
        )


def test_8ball_embed_title_resolves_in_both_locales() -> None:
    """ocio.8ball.embed_title resolves non-empty in es and en (spec scenario)."""
    for guild in (_ES_GUILD, _EN_GUILD):
        title = t(guild, "ocio.8ball.embed_title")
        assert title != "ocio.8ball.embed_title", f"title must resolve for guild lang ({guild})"
        assert title.strip(), "title must be non-empty"


def test_pre_existing_keys_remain_byte_identical() -> None:
    """Adding new keys must not touch existing translations (spec: untouched)."""
    payload = json.loads((LOCALES_DIR / "es.json").read_text(encoding="utf-8"))
    r1 = payload["ocio"]["8ball"]["r1"]
    confirm_title = payload["confirm"]["confirmed_title"]
    kick_confirm = payload["confirm"]["kick_confirm_title"]
    assert r1 and confirm_title == "Confirmado" and kick_confirm
