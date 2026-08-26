.PHONY: lint type test cov ci audit lint-full type-full tach tach-external

# -----------------------------------------------------------------
# Full blocking gates — bot/ + tests/ (scripts/ excluded). PR1a hygiene.
# Curated lists (lint-full/type-full aliases) retained for local triage.
# -----------------------------------------------------------------

lint:
	uv run ruff check bot/ tests/
	uv run ruff format --check bot/ tests/

type:
	uv run ty check bot/ tests/

# Aspirational full-project gates (non-blocking — inherited debt)
lint-full:
	uv run ruff check bot/ tests/
	uv run ruff format --check bot/ tests/

type-full:
	uv run ty check bot/ tests/

test:
	uv run pytest --cov-fail-under=80

cov:
	uv run pytest --cov-fail-under=80 --cov-report=term --cov-report=html

tach:
	uv run tach check
	uv run tach check-external

tach-external:
	uv run tach check-external

ci: lint type tach test cov

audit:
	uv audit
