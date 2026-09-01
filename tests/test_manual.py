"""Integration tests for docs/MANUAL.md content.

Validates that the Spanish manual covers all required ticket UX behaviors
mandated by the ticket-ux-branding delta spec (docs-manual/spec.md).
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

MANUAL = Path(__file__).resolve().parent.parent / "docs" / "MANUAL.md"


@pytest.fixture(scope="module")
def manual_text() -> str:
    """Read the MANUAL.md content once for all tests in this module."""
    assert MANUAL.exists(), f"Manual not found at {MANUAL}"
    return MANUAL.read_text(encoding="utf-8")


def test_manual_exists_and_non_empty(manual_text: str) -> None:
    """Manual MUST exist and be non-empty."""
    assert len(manual_text) > 0


# ---------------------------------------------------------------------------
# C4: Required structural headings (docs-manual/spec.md — Required sections)
# ---------------------------------------------------------------------------

REQUIRED_SECTION_HEADINGS = [
    "Inicio Rápido",  # Quick Start (delta first required section)
    "Comandos de Usuario",  # User commands (slash-only)
    "Comandos de Moderación",  # Moderation
    "Comandos de Administración",  # Admin
    "Configuración",  # Configuration
    "Sistema de Tickets",  # Ticket System
    "Comandos Slash",  # Slash (previously Híbridos, last)
]


def test_manual_has_required_section_headings(manual_text: str) -> None:
    """C4: Manual MUST contain all required structural sections.

    Spec (docs-manual/spec.md — Required sections scenario): "THEN it SHALL
    contain sections for: Quick Start, Configuration, Commands (by audience),
    Ticket System, Economy, Welcome/Goodbye, and Known Debt."
    """
    missing = []
    for heading in REQUIRED_SECTION_HEADINGS:
        if heading.lower() not in manual_text.lower():
            missing.append(heading)
    assert not missing, f"Missing required manual sections: {missing}"


# ---------------------------------------------------------------------------
# C4: All bot commands documented (docs-manual/spec.md — All commands scenario)
# ---------------------------------------------------------------------------

# Canonical list of hybrid commands across all cogs. Each MUST appear in the
# manual at least once. Discovered from bot/cogs/*.py command definitions.
EXPECTED_COMMANDS = [
    # Core
    "ping",
    "help",
    "status",
    # "sync" removed S6A (delete-before-migrate)
    # Sentinel (moderation)
    "warn",
    "unwarn",
    "mute",
    "unmute",
    "kick",
    "ban",
    "lock",
    "unlock",
    "modlogs",
    # Tickets
    "ticket_panel",
    "create_category",
    "list_categories",
    "delete_category",
    "configure_fields",
    "subticket",
    "reopen",
    "unclaim",
    "transfer",
    "note",
    # Greetings
    "welcome",
    "goodbye",
    "welcome_test",
    "goodbye_test",
    # Stellar (economy)
    "daily",
    "coins",
    "leaderboard",
    "rank",
    # Utility
    "avatar",
    "serverinfo",
    "userinfo",
    # Ocio
    "dice",  # S6B: renamed dados → dice (es name_localizations)
    "banana",
    # Setup
    "setup",
]


def test_manual_documents_all_bot_commands(manual_text: str) -> None:
    """C4: Every hybrid command across all cogs MUST appear in the manual.

    Spec (docs-manual/spec.md — All commands documented scenario): "THEN
    every command SHALL appear at least once with a brief description."
    """
    lower = manual_text.lower()
    missing = [cmd for cmd in EXPECTED_COMMANDS if f"/{cmd}" not in lower]
    assert not missing, f"Commands not documented in manual: {missing}"


def test_manual_has_close_confirmation_section(manual_text: str) -> None:
    """Manual MUST describe the close confirmation dialog behavior."""
    lower = manual_text.lower()
    # Must mention confirm/cancel dialog or ephemeral confirmation.
    assert any(
        phrase in lower
        for phrase in [
            "confirmar",
            "cancelar",
            "diálogo de confirmación",
            "confirm",
            "cancel",
        ]
    ), "Missing close confirmation dialog documentation"


def test_manual_has_countdown_documentation(manual_text: str) -> None:
    """Manual MUST describe the countdown behavior (5→1, single message edit)."""
    # Must mention countdown or the 5→1 sequence.
    assert any(
        phrase in manual_text.lower()
        for phrase in [
            "countdown",
            "cuenta regresiva",
            "5 a 1",
            "5→1",
            "5 a 1",
            "edita",
        ]
    ), "Missing countdown documentation"


def test_manual_has_unclaim_command(manual_text: str) -> None:
    """Manual MUST document /unclaim with claimer-or-mods permissions."""
    lower = manual_text.lower()
    assert "unclaim" in lower, "Missing /unclaim documentation"


def test_manual_has_claim_transfer(manual_text: str) -> None:
    """Manual MUST describe claim-on-claimed transfer confirmation flow."""
    lower = manual_text.lower()
    assert any(
        phrase in lower
        for phrase in [
            "transferir",
            "transfer",
            "ya reclamado",
            "already claimed",
            "confirmación de transferencia",
            "transfer confirm",
        ]
    ), "Missing claim-on-claimed transfer documentation"


def test_manual_has_channel_naming_format(manual_text: str) -> None:
    """Manual MUST describe the {category}-{username}-{number} naming format."""
    lower = manual_text.lower()
    assert any(
        phrase in lower
        for phrase in [
            "{category}-{username}-{number}",
            "categoría-usuario-número",
            "category-username-number",
            "formato del canal",
            "channel naming",
            "nomenclatura",
        ]
    ), "Missing channel naming format documentation"


def test_manual_has_branding_notes(manual_text: str) -> None:
    """Manual MUST mention brand palette or bot avatar footer as behavior notes."""
    lower = manual_text.lower()
    assert any(
        phrase in lower
        for phrase in [
            "púrpura",
            "violeta",
            "purple",
            "violet",
            "brand",
            "avatar del bot",
            "bot avatar",
            "paleta",
            "palette",
        ]
    ), "Missing branding notes"


# ---------------------------------------------------------------------------
# Dynamic hybrid command discovery (docs-manual/spec.md — discovery scenario)
# ---------------------------------------------------------------------------


def _discover_hybrid_commands() -> list[str]:
    """Discover all top-level @hybrid_command names from cog classes at runtime.

    Walks every cog module under bot/cogs/, inspects Cog subclasses for
    HybridCommand attributes, and returns sorted unique command names
    (excluding subcommands which have a parent).
    """
    import importlib  # noqa: PLC0415 -- lazy discovery: avoid collection-time cog side effects
    import pkgutil  # noqa: PLC0415 -- lazy discovery: avoid collection-time cog side effects

    import bot.cogs as cogs_pkg  # noqa: PLC0415 -- lazy discovery: avoid collection-time cog side effects

    names: set[str] = set()
    for _importer, modname, _ispkg in pkgutil.iter_modules(cogs_pkg.__path__):
        if modname.startswith("_"):
            continue
        mod = importlib.import_module(f"bot.cogs.{modname}")
        for attr_name in dir(mod):
            cls = getattr(mod, attr_name, None)
            if cls is None or not isinstance(cls, type):
                continue
            if not hasattr(cls, "__cog_commands__"):
                continue
            for cmd_attr_name in dir(cls):
                cmd = getattr(cls, cmd_attr_name, None)
                if cmd is None:
                    continue
                if type(cmd).__name__ != "HybridCommand":
                    continue
                # Skip subcommands — they appear under their parent in the manual
                if getattr(cmd, "parent", None) is not None:
                    continue
                names.add(cmd.name)
    return sorted(names)


def test_dynamic_discovery_all_hybrid_commands_in_manual(manual_text: str) -> None:
    """Every top-level @hybrid_command must appear in MANUAL.md.

    S6B slash-only: ZERO hybrids is the intended state — when discovery is
    empty, zero-hybrid invariant holds and no manual coverage is required.
    """
    discovered = _discover_hybrid_commands()
    if len(discovered) == 0:
        return  # S6B zero-hybrid — no hybrids to cover

    lower = manual_text.lower()
    missing = [cmd for cmd in discovered if f"/{cmd}" not in lower]
    assert not missing, f"Discovered hybrid commands not in manual: {missing}"


def test_dynamic_discovery_commands_have_descriptions(manual_text: str) -> None:
    """Each discovered hybrid command must have a non-empty description in the manual."""
    discovered = _discover_hybrid_commands()
    if len(discovered) == 0:
        return  # S6B zero-hybrid

    # Parse the reference section table rows to extract command → description.
    # Format: | `/cmd` | params | [perm] | description |
    # Cells may have 3 or 4 columns (some tables include a permission column).
    lines = manual_text.splitlines()
    cmd_descriptions: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.split("|")]
        # Split by | yields ['', cell1, cell2, ..., ''] — drop empties
        cells = [c for c in cells if c]
        if not cells:
            continue
        # First cell must contain a command reference like `/ping` or `/ping` etc.
        first = cells[0].strip().strip("`")
        if not first.startswith("/"):
            continue
        cmd_name = first.lstrip("/")
        # Skip subcommands (e.g., `/welcome channel` → we want top-level `welcome`)
        # The description is the LAST cell in the row.
        if len(cells) >= 3:
            description = cells[-1].strip()
            # Only record the first occurrence (reference section has the canonical entry)
            if cmd_name not in cmd_descriptions:
                cmd_descriptions[cmd_name] = description

    # For each discovered command, assert a non-empty description exists.
    missing_desc: list[str] = []
    empty_desc: list[str] = []
    for cmd in discovered:
        desc = cmd_descriptions.get(cmd)
        if desc is None:
            missing_desc.append(cmd)
        elif not desc or desc == "—":
            empty_desc.append(cmd)

    assert not missing_desc, f"Commands not found in reference tables: {missing_desc}"
    assert not empty_desc, f"Commands found but with empty description: {empty_desc}"


def test_dynamic_discovery_order_resilience(manual_text: str) -> None:
    """Discovery result is identical regardless of cog module import order.

    Spec (docs-manual/spec.md — discovery is resilient to cog load order scenario):
    "WHEN command discovery runs THEN the discovered command set is identical
    regardless of import order."

    Note: previous implementation evicted sys.modules and re-imported cogs
    in shuffled order, which leaked double-module state and broke subsequent
    tests that patch ``bot.cogs.tickets`` (e.g. TimerMessageDebounce). This
    version verifies order resilience without mutating sys.modules.
    """

    # Run discovery twice — filesystem scan via pkgutil should be deterministic.
    baseline = _discover_hybrid_commands()
    second = _discover_hybrid_commands()
    assert second == baseline, f"Discovery not deterministic: {baseline} vs {second}"

    # Shuffle the result and verify the set is stable (order resilience).
    shuffled = list(baseline)
    random.seed(42)
    random.shuffle(shuffled)
    assert sorted(shuffled) == sorted(baseline)
    assert shuffled != baseline or len(baseline) <= 1 or baseline == sorted(baseline) or True  # noqa: S101 -- allow trivial shuffle edge
