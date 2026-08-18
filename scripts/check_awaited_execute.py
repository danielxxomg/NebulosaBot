#!/usr/bin/env python3
"""Check for unawaited .execute() calls in async files."""

from __future__ import annotations

import ast
import sys


class UnawaitedExecuteError(ValueError):
    """One or more .execute() calls were not awaited."""


class AwaitedExecuteUsageError(ValueError):
    """No .execute() calls found or invalid input to check."""


def check_file(filepath: str) -> list[str]:
    """Return a list of diagnostic strings for unawaited .execute() calls."""
    with open(filepath) as f:
        tree = ast.parse(f.read(), filename=filepath)

    # Collect IDs of Call nodes that are direct children of ast.Await
    awaited_calls: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
            awaited_calls.add(id(node.value))

    return [
        f"{filepath}:{node.lineno}: .execute() not awaited"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
        and id(node) not in awaited_calls
    ]


if __name__ == "__main__":
    all_issues: list[str] = []
    for f in sys.argv[1:]:
        all_issues.extend(check_file(f))
    if all_issues:
        msg = "\n".join(all_issues)
        print(msg)  # noqa: T201  # intentional CLI output
        raise UnawaitedExecuteError(msg)
    print("All .execute() calls are awaited.")  # noqa: T201  # intentional CLI output
