"""Structural tests for code-quality consolidation (SDD change: code-quality).

These tests enforce that refactoring goals are met:
- ``FALLBACK_PREFIX`` is the single production source for the "nb!" literal.
- ``_resolve_avatar_url`` is defined in exactly one file.
- CI quality workflow exists with report-only steps.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parent.parent / "bot"
CI_WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "code-quality.yml"

# ---------------------------------------------------------------------------
# Phase 1: "nb!" centralization
# ---------------------------------------------------------------------------


def test_nb_literal_only_in_constants():
    """The string literal "nb!" must appear ONLY in bot/constants.py.

    Scans all .py files under bot/ and collects every file that contains
    the literal ``"nb!"`` (inside a string).  After centralization, only
    ``bot/constants.py`` should contain it.
    """
    allowed_file = BOT_ROOT / "constants.py"
    offenders: list[str] = []

    for py_file in sorted(BOT_ROOT.rglob("*.py")):
        content = py_file.read_text(encoding="utf-8")
        if '"nb!"' in content or "'nb!'" in content:
            if py_file.resolve() != allowed_file.resolve():
                offenders.append(str(py_file.relative_to(BOT_ROOT.parent)))

    assert not offenders, (
        f'The literal "nb!" was found outside bot/constants.py in: {offenders}. '
        "Import FALLBACK_PREFIX from bot.constants instead."
    )


# ---------------------------------------------------------------------------
# Phase 2: _resolve_avatar_url deduplication
# ---------------------------------------------------------------------------


def test_resolve_avatar_url_single_definition():
    """_resolve_avatar_url must be defined in exactly one file.

    The canonical home is ``bot/services/greeting_service.py``.
    All other modules must import from there.
    """
    canonical_file = BOT_ROOT / "services" / "greeting_service.py"
    definition_pattern = re.compile(r"^def _resolve_avatar_url\b", re.MULTILINE)
    offenders: list[str] = []

    for py_file in sorted(BOT_ROOT.rglob("*.py")):
        content = py_file.read_text(encoding="utf-8")
        if definition_pattern.search(content):
            if py_file.resolve() != canonical_file.resolve():
                offenders.append(str(py_file.relative_to(BOT_ROOT.parent)))

    assert not offenders, (
        f"_resolve_avatar_url is defined in non-canonical files: {offenders}. "
        "Import it from bot.services.greeting_service instead."
    )


# ---------------------------------------------------------------------------
# Phase 3: CI workflow structure
# ---------------------------------------------------------------------------


def test_code_quality_workflow_exists():
    """The code-quality CI workflow file must exist."""
    assert CI_WORKFLOW.is_file(), f"Expected workflow at {CI_WORKFLOW}"


def test_code_quality_workflow_has_jscpd_step():
    """The workflow must contain a jscpd step with continue-on-error: true."""
    content = CI_WORKFLOW.read_text(encoding="utf-8")

    # Find the jscpd step block — look for jscpd in run or uses fields
    has_jscpd = "jscpd" in content
    assert has_jscpd, "Workflow must reference jscpd"

    # The workflow must be report-only (continue-on-error at step level)
    # We parse YAML structurally: find jscpd step and check continue-on-error
    # Simple heuristic: the string "continue-on-error: true" must appear
    assert "continue-on-error: true" in content, (
        "jscpd/vulture steps must have continue-on-error: true (report-only)"
    )


def test_code_quality_workflow_has_vulture_step():
    """The workflow must contain a vulture step with continue-on-error: true."""
    content = CI_WORKFLOW.read_text(encoding="utf-8")

    has_vulture = "vulture" in content
    assert has_vulture, "Workflow must reference vulture"

    assert "continue-on-error: true" in content, (
        "jscpd/vulture steps must have continue-on-error: true (report-only)"
    )


def test_code_quality_workflow_triggers_on_pull_request():
    """The workflow must trigger on pull_request events."""
    content = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request" in content, "Workflow must trigger on pull_request"
