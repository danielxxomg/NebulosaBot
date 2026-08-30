"""S1 guard — zero hybrid decorators in bot/cogs (repo-wide AST, D5).

Replaces the 8-file substring guard with a repo-wide AST scan over
``bot/cogs/**/*.py`` so no hybrid_command/hybrid_group decorator can
survive in any cog. The only surviving ``hybrid_command`` substrings
after S1 are docstring examples at ``bot/utils/checks.py:229,361``
per the 12-spec delta contract; those are NOT in ``bot/cogs`` so the
scan over ``bot/cogs`` must be 0 regardless of docstring survivors.
"""

from __future__ import annotations

import ast
import pathlib


def test_zero_hybrid_decorators_in_all_cogs() -> None:
    """AST scan: zero hybrid_command/hybrid_group decorators in bot/cogs/**/*.py."""
    cogs_root = pathlib.Path("bot/cogs")
    assert cogs_root.exists(), "bot/cogs must exist"
    offenders: list[str] = []
    scanned = 0
    for p in cogs_root.rglob("*.py"):
        scanned += 1
        src = p.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src, filename=str(p))
        except SyntaxError as e:
            offenders.append(f"{p}: SyntaxError {e}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("hybrid_command", "hybrid_group"):
                offenders.append(f"{p}:{node.lineno} {node.attr}")
                break
    assert scanned > 0, f"scan discovered 0 Python files under {cogs_root} — misconfigured guard"
    assert offenders == [], f"hybrid decorators remain in bot/cogs: {offenders}"


def test_zero_hybrid_substrings_in_all_cogs() -> None:
    """Substring guard: no hybrid_command/hybrid_group substrings in bot/cogs/*.py."""
    offenders: list[str] = []
    scanned = 0
    for p in pathlib.Path("bot/cogs").rglob("*.py"):
        scanned += 1
        src = p.read_text(encoding="utf-8")
        if "hybrid_command" in src or "hybrid_group" in src:
            offenders.append(str(p))
    assert scanned > 0, "scan discovered 0 Python files under bot/cogs — misconfigured"
    assert offenders == [], f"hybrid substrings remain in bot/cogs: {offenders}"
