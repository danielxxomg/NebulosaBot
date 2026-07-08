"""Validate .github/workflows/ci.yml for tooling-rigor change.

Covers the ci-workflow-file and qa-ci-pipeline spec scenarios:
    - Matrix includes Python 3.13
    - fail-fast disabled
    - Coverage gate --cov-fail-under=75 in pytest invocation
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CI_YML = _PROJECT_ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture()
def ci_config() -> dict:
    """Load ci.yml."""
    with open(_CI_YML) as f:
        return yaml.safe_load(f)


@pytest.fixture()
def qa_matrix_job(ci_config: dict) -> dict:
    """Extract the qa-matrix job definition."""
    return ci_config["jobs"]["qa-matrix"]


@pytest.fixture()
def matrix(qa_matrix_job: dict) -> dict:
    """Extract strategy.matrix."""
    return qa_matrix_job["strategy"]["matrix"]


# ---------------------------------------------------------------------------
# Scenario: Four Python versions in matrix (including 3.13)
# ---------------------------------------------------------------------------


class TestCIMatrix:
    """Matrix MUST include Python 3.11, 3.12, 3.13, 3.14."""

    def test_matrix_includes_313(self, matrix: dict) -> None:
        """Matrix MUST include Python 3.13."""
        versions = matrix.get("python-version", [])
        assert "3.13" in versions, f"Python 3.13 not in matrix. Current: {versions}"

    def test_matrix_includes_311(self, matrix: dict) -> None:
        """Matrix MUST include Python 3.11."""
        versions = matrix.get("python-version", [])
        assert "3.11" in versions, f"Python 3.11 not in matrix. Current: {versions}"

    def test_matrix_includes_312(self, matrix: dict) -> None:
        """Matrix MUST include Python 3.12."""
        versions = matrix.get("python-version", [])
        assert "3.12" in versions, f"Python 3.12 not in matrix. Current: {versions}"

    def test_matrix_includes_314(self, matrix: dict) -> None:
        """Matrix MUST include Python 3.14."""
        versions = matrix.get("python-version", [])
        assert "3.14" in versions, f"Python 3.14 not in matrix. Current: {versions}"

    def test_four_versions_in_matrix(self, matrix: dict) -> None:
        """Matrix MUST have exactly 4 Python versions."""
        versions = matrix.get("python-version", [])
        assert len(versions) == 4, f"Expected 4 Python versions, got {len(versions)}: {versions}"


# ---------------------------------------------------------------------------
# Scenario: One failure does not cancel others
# ---------------------------------------------------------------------------


class TestCIFailFast:
    """fail-fast MUST be disabled."""

    def test_fail_fast_disabled(self, qa_matrix_job: dict) -> None:
        """strategy.fail-fast MUST be false."""
        fail_fast = qa_matrix_job.get("strategy", {}).get("fail-fast")
        assert fail_fast is False, f"Expected fail-fast=false, got {fail_fast}"


# ---------------------------------------------------------------------------
# Scenario: Coverage gate blocks CI
# ---------------------------------------------------------------------------


class TestCICoverageGate:
    """CI MUST pass --cov-fail-under=75 to pytest."""

    def test_pytest_has_cov_fail_under_75(self, ci_config: dict) -> None:
        """The 'Tests with coverage' step MUST pass --cov-fail-under=75."""
        steps = ci_config["jobs"]["qa-matrix"]["steps"]
        test_step = None
        for step in steps:
            name = step.get("name", "")
            if "coverage" in name.lower() or "test" in name.lower():
                run_cmd = step.get("run", "")
                if "pytest" in run_cmd:
                    test_step = step
                    break

        assert test_step is not None, "No pytest step found in qa-matrix job"
        run_cmd = test_step.get("run", "")
        assert "--cov-fail-under=75" in run_cmd, f"--cov-fail-under=75 not in pytest command: {run_cmd}"
