.PHONY: lint type security test cov ci audit lint-full type-full

# -----------------------------------------------------------------
# Ratcheted gates — scoped to rama-c-qa-tooling surfaces.
# Rename to the unqualified targets once full-project debt is cleared.
# -----------------------------------------------------------------

PR3_FILES := tests/test_sentinel_cog.py tests/test_tickets_cog.py tests/test_greeting_service.py tests/integration/

lint:
	uv run ruff check bot/services/economy_service.py bot/config.py tests/conftest.py tests/property/ tests/test_economy_service.py tests/test_guild_service.py tests/test_config.py tests/test_database.py $(PR3_FILES)
	uv run ruff format --check bot/services/economy_service.py bot/config.py tests/conftest.py tests/property/ tests/test_economy_service.py tests/test_guild_service.py tests/test_config.py tests/test_database.py $(PR3_FILES)

type:
	uv run mypy bot/services/economy_service.py bot/config.py tests/conftest.py tests/test_guild_service.py tests/test_config.py tests/test_database.py

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
