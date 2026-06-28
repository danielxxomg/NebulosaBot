.PHONY: lint type security test cov ci audit lint-full type-full

# -----------------------------------------------------------------
# Ratcheted gates — scoped to PR1-clean surfaces (rama-c-qa-tooling).
# Rename to the unqualified targets once full-project debt is cleared.
# -----------------------------------------------------------------

lint:
	uv run ruff check bot/services/economy_service.py tests/conftest.py tests/property/ tests/test_economy_service.py tests/test_guild_service.py
	uv run ruff format --check bot/services/economy_service.py tests/conftest.py tests/property/ tests/test_economy_service.py tests/test_guild_service.py

type:
	uv run mypy bot/services/economy_service.py tests/conftest.py tests/test_guild_service.py

security:
	uv run bandit -r bot/ -c pyproject.toml --severity-level medium

# Aspirational full-project gates (non-blocking — inherited debt)
lint-full:
	uv run ruff check bot/ tests/
	uv run ruff format --check bot/ tests/

type-full:
	uv run mypy bot/ tests/

test:
	uv run pytest

cov:
	uv run pytest --cov=bot --cov-report=term --cov-report=html

ci: lint type security test cov

audit:
	uv run --with pip-audit pip-audit -l --strict
