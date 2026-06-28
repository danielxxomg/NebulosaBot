.PHONY: lint type security test cov ci audit

lint:
	ruff check bot/
	ruff format --check bot/

type:
	mypy bot/

security:
	bandit -r bot/ -c pyproject.toml

test:
	pytest

cov:
	pytest --cov=bot --cov-report=term --cov-report=html

ci: lint type security test cov

audit:
	uv run --with pip-audit pip-audit --strict
