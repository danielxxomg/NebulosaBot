# NebulosaBot Development and Verification Guide

Guidelines, verification commands, and safety boundaries for developing and testing NebulosaBot across Python services and the Next.js dashboard.

## Quick path

Use the installed dependencies and package-manager offline modes for these checks.
The flags restrict dependency fetching; they do not sandbox test-process network
access. Service calls still require mocks and controlled test configuration.

```bash
# Python backend verification
UV_OFFLINE=1 UV_NO_SYNC=1 PYTHONDONTWRITEBYTECODE=1 make lint
UV_OFFLINE=1 UV_NO_SYNC=1 PYTHONDONTWRITEBYTECODE=1 make type
UV_OFFLINE=1 UV_NO_SYNC=1 PYTHONDONTWRITEBYTECODE=1 make tach
UV_OFFLINE=1 UV_NO_SYNC=1 PYTHONDONTWRITEBYTECODE=1 make test

# Dashboard frontend verification
cd dashboard
npm --offline test -- --run
npm --offline run lint
cd ..
```

## Verification safety boundaries

| Boundary | Policy | Implementation & Protection |
|---|---|---|
| **Git hooks & mutation** | Unit tests must not mutate the live working tree or invoke external review. | `prek.toml` defines git hooks (`ruff --fix`, `bash .gga`). In pytest (`tests/test_prek_config.py`), hook execution tests run exclusively inside disposable temporary Git repositories (`tmp_path`). Ordinary unit tests rely on deterministic tools (`make lint`, `make type`, `make tach`) and never run mutating hooks or external review models against live files. |
| **Fault injection** | Boundary violation tests must not modify production source code. | Architecture violation tests (`tests/test_pr6_tach_boundaries.py`) copy the required package tree to an isolated fixture directory (`tmp_path`) before injecting disallowed imports. The focused test checks that live `bot/models/ticket.py` content and modification time are unchanged; this is not a complete filesystem or Git-index audit. |
| **Vitest environment** | Tests must use dummy configuration rather than developer secrets. | `dashboard/vitest.config.ts` sets `envDir: false`, disabling Vite's automatic `.env` and `.env.local` loading. It does not remove inherited process variables or prevent explicit dotenv reads by other code. Use controlled values and mocked service clients. Production Next.js environment loading remains unchanged. |
| **Network & offline** | Tests must not contact real services without separate authorization. | `UV_OFFLINE=1` and `npm --offline` restrict package-manager fetches, not application HTTP/socket calls. Dependencies must already be installed, and service boundaries must be mocked or separately constrained; offline flags alone prove neither secret isolation nor zero network access. |

## Verification details

| Target | Command | Purpose |
|---|---|---|
| Python Linting | `make lint` | Runs `ruff check` and `ruff format --check` across `bot/` and `tests/`. |
| Python Type Checking | `make type` | Runs `ty check bot/ tests/` for type validation. |
| Python Architecture | `make tach` | Validates 7-layer architecture constraints (`tach check`) and external imports (`tach check-external`). |
| Python Unit Tests | `make test` | Runs the full `pytest` test suite with coverage enforcement. |
| Dashboard Unit Tests | `npm --offline test -- --run` | Runs all Vitest test suites with `jsdom` environment and `envDir: false`. |
| Dashboard Linting | `npm --offline run lint` | Runs `eslint` across dashboard TypeScript and React components. |

## Verification checklist

- [ ] `make lint` exits 0 with no formatting or linting errors.
- [ ] `make type` exits 0 with all type checks passing.
- [ ] `make tach` exits 0 with all module layers and external dependencies validated.
- [ ] `make test` exits 0 with full test suite passing.
- [ ] `cd dashboard && npm --offline test -- --run` exits 0 with all test suites passing.
- [ ] `cd dashboard && npm --offline run lint` exits 0 (pre-existing image warning documented).
- [ ] Before/after Git status contains only expected feature changes, with no unintended tracked edits or scratch files. Do not infer ignored-file integrity from Git status alone.
