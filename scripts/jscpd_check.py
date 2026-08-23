"""Duplication budget checker — pinned jscpd@4.0.1 ratchet (D4).

Runs `npx jscpd@4.0.1` over `bot/` and `tests/` with JSON reporter into a
temporary directory, parses ``statistics.total.percentage`` per scope, and
compares against ``reports/jscpd-baseline.json`` ceilings.

Exit codes (spec duplication-budget):
  0 — every scope at or below its ceiling
  2 — any scope strictly above its ceiling (budget violation)
  1 — infrastructure failure (missing tool output, unparsable report, bad baseline)

No ``shell=True`` — pinned ``jscpd@4.0.1`` via ``npx`` list argv.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

BASELINE_PATH_CANDIDATES = [
    Path("reports/jscpd-baseline.json"),
    Path(__file__).resolve().parents[1] / "reports" / "jscpd-baseline.json",
]

SCOPES = ("bot", "tests")
PIN = "jscpd@4.0.1"


def _load_baseline(path: Path | None = None) -> dict[str, float]:
    """Load and validate the baseline ceiling JSON.

    Args:
        path: Optional explicit path; otherwise probes candidates.

    Returns:
        Dict with ``bot`` and ``tests`` float ceilings.

    Raises:
        FileNotFoundError, ValueError, json.JSONDecodeError on bad baseline
        (caller maps to exit 1).
    """
    candidate = path
    if candidate is None:
        for cand in BASELINE_PATH_CANDIDATES:
            if cand.is_file():
                candidate = cand
                break
        if candidate is None:
            candidate = BASELINE_PATH_CANDIDATES[0]

    raw = candidate.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        msg = f"Baseline {candidate} must be a JSON object"
        raise ValueError(msg)  # noqa: TRY004 -- baseline/report contract violation is ValueError
    out: dict[str, float] = {}
    for scope in SCOPES:
        if scope not in data:
            msg = f"Baseline {candidate} missing key {scope!r}"
            raise ValueError(msg)
        val = data[scope]
        if not isinstance(val, (int, float)):
            msg = f"Baseline {candidate}[{scope!r}] must be numeric, got {val!r}"
            raise ValueError(msg)  # noqa: TRY004 -- baseline contract is ValueError
        out[scope] = float(val)
    return out


def _measure_scope(scope: str, tmpdir: str) -> float:
    """Run pinned jscpd over *scope* and return its duplication percentage.

    Args:
        scope: ``bot`` or ``tests`` directory name.
        tmpdir: Temporary directory for the JSON reporter's output.

    Returns:
        ``statistics.total.percentage`` as float.

    Raises:
        ValueError, FileNotFoundError, json.JSONDecodeError, subprocess errors
        on infrastructure failure (caller maps to exit 1).
    """
    # Pinned invocation — list argv, never shell=True (threat-matrix)
    argv = ["npx", PIN, scope, "--reporters", "json", "--output", tmpdir]
    # We intentionally do not pass --threshold: the raw percentage is what we compare
    result = subprocess.run(argv, capture_output=True, text=True, shell=False)  # noqa: S603 — argv is pinned constant, no interpolation

    # jscpd may exit 1 when duplicates exceed its internal threshold; we still parse the report
    # If no report was produced at all, treat as infra failure
    tmp_path = Path(tmpdir)
    # jscpd writes jscpd-report.json (sometimes with subdir)
    candidates = list(tmp_path.rglob("*.json"))
    if not candidates:
        msg = f"jscpd produced no JSON report for {scope} (npx exit {result.returncode})"
        raise FileNotFoundError(msg)
    report_path = candidates[0]
    raw = report_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    # Prefer statistics.total.percentage; fall back to statistics.clone.percentage or formats.python.total
    stats = data.get("statistics") if isinstance(data, dict) else None
    if not isinstance(stats, dict):
        msg = f"jscpd report for {scope} missing statistics"
        raise ValueError(msg)  # noqa: TRY004 -- report contract is ValueError
    total = stats.get("total")
    if isinstance(total, dict) and "percentage" in total:
        val = total["percentage"]
        if isinstance(val, (int, float)):
            return float(val)
    # Fallback: statistics.clone.percentage (older spec phrasing)
    clone = stats.get("clone")
    if isinstance(clone, dict) and "percentage" in clone:
        val = clone["percentage"]
        if isinstance(val, (int, float)):
            return float(val)
    # Fallback: formats.python.total.percentage
    formats = stats.get("formats")
    if isinstance(formats, dict):
        py = formats.get("python")
        if isinstance(py, dict):
            py_total = py.get("total")
            if isinstance(py_total, dict) and "percentage" in py_total:
                val = py_total["percentage"]
                if isinstance(val, (int, float)):
                    return float(val)
    msg = f"jscpd report for {scope} has no percentage field"
    raise ValueError(msg)


def main(argv: list[str] | None = None) -> int:
    """Entry point — loads baseline, measures both scopes, compares.

    Args:
        argv: Unused (reserved for future CLI flags).

    Returns:
        Exit code per the spec contract (0/1/2).
    """
    _ = argv
    try:
        ceilings = _load_baseline()
    except (FileNotFoundError, ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"[jscpd] baseline error: {exc}", file=sys.stderr)  # noqa: T201
        return 1

    results: dict[str, float] = {}
    for scope in SCOPES:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                pct = _measure_scope(scope, tmpdir)
            results[scope] = pct
        except (FileNotFoundError, ValueError, json.JSONDecodeError, OSError, subprocess.SubprocessError) as exc:
            print(f"[jscpd] infra failure for {scope}: {exc}", file=sys.stderr)  # noqa: T201
            return 1

    # Compare
    violations: list[str] = []
    for scope in SCOPES:
        measured = results[scope]
        ceiling = ceilings[scope]
        print(f"[jscpd] {scope}: {measured:.2f}% (ceiling {ceiling:.2f}%)")  # noqa: T201
        if measured > ceiling:  # strictly above
            violations.append(f"{scope} {measured:.2f}% > ceiling {ceiling:.2f}%")

    if violations:
        for v in violations:
            print(f"[jscpd] VIOLATION: {v}", file=sys.stderr)  # noqa: T201
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
