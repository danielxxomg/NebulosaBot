.PHONY: lint type security test cov ci audit lint-full type-full

# -----------------------------------------------------------------
# Full blocking gates — bot/ + tests/ (scripts/ excluded). PR1a hygiene.
# Curated lists (lint-full/type-full aliases) retained for local triage.
# -----------------------------------------------------------------

lint:
	uv run ruff check bot/ tests/
	uv run ruff format --check bot/ tests/

type:
	uv run mypy --follow-imports=silent bot/

security:
	uv run bandit -r bot/ -c pyproject.toml --severity-level medium

# Aspirational full-project gates (non-blocking — inherited debt)
lint-full:
	uv run ruff check bot/ tests/
	uv run ruff format --check bot/ tests/

type-full:
	uv run mypy bot/ tests/

test:
	uv run pytest --cov-fail-under=75

cov:
	uv run pytest --cov-fail-under=75 --cov-report=term --cov-report=html

ci: lint type security test cov

audit:
	uv run --with pip-audit pip-audit -l --strict
