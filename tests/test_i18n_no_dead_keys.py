"""Dead-key detector — dynamic-safe, literal+dynamic inventory (S5.3).

Literal t() keys + dynamic-prefix whitelist (runtime-built families) form the
reference inventory. Every locale leaf outside that inventory is considered
dead — green only after the locale files are pruned symmetrically.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BOT_ROOT = REPO_ROOT / "bot"
LOCALES_DIR = BOT_ROOT / "locales"

# Families whose keys are composed at runtime (not literal t("...") calls).
# Each prefix must genuinely exist as a dynamic composition site (review-time
# audit). Adding a prefix to silence a dead key without a real site is debt.
DYNAMIC_PREFIXES: tuple[str, ...] = (
    "setup.module.",  # Setup module family (tickets/welcome/goodbye/log/language)
    "tickets.integrity.",  # integrity sweep/repair (f"{key}_title" families via embeds helpers)
    "tickets.actions.",  # ticket actions (f"tickets.actions.{action}_*")
    "tickets.timer.",  # timer units already allowlisted in coverage test; full family here
    "tickets.timer.unit_",  # explicit timer unit family
    "ocio.8ball.r",  # 8ball random responses
    "slash.",  # slash command descriptions (locale_str key=)
    "voice.",  # voice event embeds (logging_service reuse)
    "log.",  # logging service keys
    "greetings.",  # greeting card family (still wired via dynamic kind)
    # Families wired via cog_err/cog_ok dynamic suffix helpers (f"{key}_title/_description")
    # and info/warning/success title embeds — literal scanner misses these.
    "tickets.note.",  # ticket notes flow (cog_err/cog_ok dynamic suffix)
    "tickets.open.",  # ticket open flow (build_ticket_embed, _ok helpers)
    "tickets.close.",  # close flow close embed families
    "tickets.close_modal.",  # close modal flow
    "tickets.panel.",  # panel deploy flow
    "tickets.create.",  # admin flow create
    "tickets.delete.",  # admin flow delete
    "tickets.list.",  # admin list
    "tickets.modal.",  # ticket modal intake
    "tickets.configure_fields.",  # configure_fields flow
    "tickets.reopen.",  # reopen flow
    "tickets.subticket.",  # subticket flow
    "tickets.transfer.",  # transfer flow
    "setup.panel.breadcrumb.",  # breadcrumb f"setup.panel.breadcrumb.{module}"
    "setup.panel.option.",  # setup panel option labels
    "common.",  # common.info/success/warning/info_embed titles
    "core.help.",  # help paginator prev/next labels
    "sentinel.",  # sentinel modlogs/warn/tempban embeds via helpers
    "stellar.leaderboard.",  # leaderboard embed titles
    "ocio.banana.",  # banana render fallback
    "setup.",  # setup.success/error families
)

# Regex for slash locale_str key="..."
_LOCALE_STR_RE = re.compile(r'key\s*=\s*"([^"]+)"')


def _t_aliases(tree: ast.AST) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "bot.core.i18n":
            for alias in node.names:
                if alias.name == "t":
                    aliases.add(alias.asname or alias.name)
    return aliases


def _scan_literal_t_keys(bot_root: Path) -> set[str]:
    keys: set[str] = set()
    for py in sorted(bot_root.rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeError):  # noqa: BLE001 -- test scanner best-effort skip
            continue
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
                keys.add(arg.value)
    return keys


def _scan_locale_str_keys(bot_root: Path) -> set[str]:
    keys: set[str] = set()
    for py in sorted(bot_root.rglob("*.py")):
        txt = py.read_text(encoding="utf-8", errors="ignore")
        for m in _LOCALE_STR_RE.finditer(txt):
            k = m.group(1)
            keys.add(k)
    return keys


def _flatten(payload: dict, prefix: str = "") -> set[str]:
    out: set[str] = set()
    for k, v in payload.items():
        dotted = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out |= _flatten(v, dotted)
        else:
            out.add(dotted)
    return out


def _load_flat(name: str) -> set[str]:
    payload = json.loads((LOCALES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return _flatten(payload)


def _is_dynamic_key(key: str) -> bool:
    return any(key.startswith(p) for p in DYNAMIC_PREFIXES)


def test_no_dead_keys_in_both_locales() -> None:
    """Every locale leaf must be either a literal t() key, a locale_str key, or dynamic-family.

    Green only after locales are pruned symmetrically.
    """
    literals = _scan_literal_t_keys(BOT_ROOT)
    locale_strs = _scan_locale_str_keys(BOT_ROOT)
    referenced = literals | locale_strs
    es_keys = _load_flat("es")
    en_keys = _load_flat("en")
    # es/en must stay symmetric — asserted elsewhere, but we check both sides here
    all_keys = es_keys | en_keys
    dead = sorted(k for k in all_keys if k not in referenced and not _is_dynamic_key(k))
    assert not dead, (
        "Dead i18n keys (no literal t() or locale_str, not dynamic-family):\n"
        + "\n".join(f"  {k}" for k in dead)
        + "\nAdd to DYNAMIC_PREFIXES only if a real runtime composition site exists."
    )


def test_dead_detector_catches_synthetic_dead_key(tmp_path: Path) -> None:
    """Self-test: synthetic locale leaf not in code is flagged dead."""
    # Use the real scanner logic on a tmp bot tree; synthetic key must be dead
    bot_dir = tmp_path / "bot"
    bot_dir.mkdir()
    (bot_dir / "mod.py").write_text(
        'from bot.core.i18n import t\n\ndef f(gid): return t(gid, "real.key")\n',
        encoding="utf-8",
    )
    literals = _scan_literal_t_keys(bot_dir)
    fake_leaf = "totally.dead.synth_key"
    assert fake_leaf not in literals
    assert not _is_dynamic_key(fake_leaf)
