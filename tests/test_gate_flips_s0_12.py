"""S0.12 gate flips — betterleaks blocking, coverage floor 80.

clean-1.0 S0.12:
- the ``security-advisory`` job (betterleaks + OSV-Scanner) in
  ``code-quality.yml`` loses its ``continue-on-error`` escape hatch —
  full-scan triage is clean, so secrets scanning is now BLOCKING;
- the pytest coverage floor rises 75 → 80 in every invocation surface
  that passes it explicitly (pyproject addopts, ci.yml, Makefile).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def code_quality_config() -> dict:
    with (_PROJECT_ROOT / ".github" / "workflows" / "code-quality.yml").open() as f:
        return yaml.safe_load(f)


def test_betterleaks_job_is_blocking(code_quality_config: dict) -> None:
    """security-advisory MUST NOT carry continue-on-error: true anymore."""
    job = code_quality_config["jobs"]["security-advisory"]
    assert job.get("continue-on-error") is not True, (
        "betterleaks triage is clean — secrets scanning MUST be blocking now"
    )
    # And the job still actually runs the scanners.
    runs = [step.get("run", "") for step in job.get("steps", [])]
    assert any("betterleaks" in run for run in runs), "betterleaks step missing from security job"
    assert any("osv-scanner" in run for run in runs), "osv-scanner step missing from security job"


def test_other_advisory_jobs_keep_their_escape_hatch(code_quality_config: dict) -> None:
    """Guard: dashboard stays advisory; vulture flips blocking in ops-zero-lite (S0.9)."""
    jobs = code_quality_config["jobs"]
    assert jobs.get("dashboard-lint-advisory", {}).get("continue-on-error") is True
    quality_steps = jobs.get("quality-reports", {}).get("steps", [])
    vulture = [s for s in quality_steps if "vulture" in s.get("run", "")]
    assert vulture and vulture[0].get("continue-on-error") is not True


def test_pyproject_coverage_floor_is_80() -> None:
    """pyproject addopts MUST enforce --cov-fail-under=80 and no stale 75."""
    text = (_PROJECT_ROOT / "pyproject.toml").read_text()
    assert "--cov-fail-under=80" in text, "coverage floor must be 80 (S0.12)"
    assert "--cov-fail-under=75" not in text, "stale 75 floor still present in pyproject addopts"


def test_makefile_coverage_gate_matches_floor() -> None:
    """Makefile test/cov targets pass --cov-fail-under=80 explicitly."""
    makefile = (_PROJECT_ROOT / "Makefile").read_text()
    assert "--cov-fail-under=80" in makefile
    assert "--cov-fail-under=75" not in makefile
