#!/usr/bin/env python3
"""Check for unawaited .execute() calls in async files."""

from __future__ import annotations

import ast
import sys


def check_file(filepath: str) -> list[str]:
    """Return a list of diagnostic strings for unawaited .execute() calls."""
    issues: list[str] = []
    with open(filepath) as f:
        tree = ast.parse(f.read(), filename=filepath)

    # Collect IDs of Call nodes that are direct children of ast.Await
    awaited_calls: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
            awaited_calls.add(id(node.value))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "execute" and id(node) not in awaited_calls:
                issues.append(f"{filepath}:{node.lineno}: .execute() not awaited")
    return issues


if __name__ == "__main__":
    all_issues: list[str] = []
    for f in sys.argv[1:]:
        all_issues.extend(check_file(f))
    if all_issues:
        print("\n".join(all_issues))
        sys.exit(1)
    print("All .execute() calls are awaited.")
