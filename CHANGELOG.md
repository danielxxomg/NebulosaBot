# Changelog

All notable changes to NebulosaBot are documented here.

## [1.1.0] - 2026-10-03

### Added
- Weekly encrypted backup profile specification (`supabase-dump-encrypted`). Note: backup encryption profile is specified, but `BACKUP_ENCRYPTION_KEY` is not provisioned in the live environment, no successful backup run has ever been observed, and isolated restore acceptance has never been executed; this does not constitute production readiness.
- Database connection guard verifying connection health, fail-closed handling, and credential prerequisites prior to operations.
- Application data reset and cleanup runbook (`docs/runbooks/reset-procedure.md`) specifying controlled read-only pre-reset inventory and human sign-off gates without direct execution.
- Release and rollback runbook (`docs/runbooks/release-and-rollback.md`) documenting pre-cut verification gates, multi-surface version bump sequence, local Git rollback steps, and recovery constraints.

### Changed
- Reconciled version surfaces across `pyproject.toml`, `bot/__init__.py`, `uv.lock`, and embedded `dashboard/package.json` to 1.1.0.
  - Historical reconciliation note: Git release tag `v1.0.0` was cut on 2026-08-26 while repository metadata in `pyproject.toml` and `bot/__init__.py` declared `0.9.0`. Version 1.1.0 reconciles this historical metadata gap directly without backfilling intermediate release tags.
- Documented rollback irreversibility in staging-live parity runbook (`docs/runbooks/staging-live-parity.md`): migration 025 permanently dropped legacy table `ticket_backup_categoryid_text_20260818`, rendering migration 018 `DOWN` script unexecutable and requiring full database backup restoration for rollback.
- Hardened credential-scrubbing patterns and validation guards to prevent secret exposure in diagnostics.

### Fixed
- Synchronized embedded dashboard package metadata and package-lock to prevent client-bot release divergence.

### Notes
- The section previously titled `## Cycle 5 — Quality Zero (unreleased; v1.0 readiness)` is
  retitled below as `## [1.0.0] - 2026-08-26`. That retitle is a **historical reconciliation,
  not a fix delivered in 1.1.0**, and it is recorded here rather than under `### Fixed` so the
  two are not conflated.
  - Provenance of that section's date and content: the `v1.0.0` git tag (annotated, tagger date
    2026-08-26) and the tree at that tag. It was NOT reconstructed from a pre-existing 1.0.0
    changelog entry, because no such entry ever existed — the section had been sitting
    unbracketed and mislabeled as unreleased.
  - Verified against the tag: `bot/services/image_service.py` is already absent at `v1.0.0`,
    `AGENTS.md` is already at v3 there, and migrations through `029` are already present. The
    work described in that section had therefore already shipped inside `v1.0.0`.

## [1.0.0] - 2026-08-26

### Added
- Fatal `ty` type gate (`error-on-warning = true`); tests/ diagnostics 495 → 0.
- InfractionService mute/kick/ban persistence with caller-side single audit.
- CDC realtime for `member` / `economy_config`: publication + `updatedAt` columns,
  subscription, incremental poll, watchdog counter, echo suppression on RPC mutators.
- LoggingService i18n: moderation/voice events localized ES/EN with AST-level
  anti-drift guard.
- Resource-log heartbeat loop in CoreCog.

### Changed
- Slash-only command surface: prefix invocation inert (`_noop_prefix` returns `[]`);
  `,` reserved exclusively for the ticket close-timer listener.
- Global error handler delivers one channel embed via `t()`; DM-first branch removed.
- GreetingService is protocol-only (ImageService deleted; renderer contract enforced).
- Economy config reads are cache-first with TTL + invalidation; transcript HTML built
  via `asyncio.to_thread`; greeting dispatch raid-guarded; `,`-timer debounced 15 s.
- AGENTS.md v3: slash-only policy, PLC0415 exception policy, i18n/brand-token rules.
- Migrations resynced and pushed: 025 DROP legacy backup table, 026 realtime
  publication (26/26 local = remote).

### Removed
- `ImageService` shim and its test files (~780 lines).
- ~4,000 lines of duplicate/theater test code across consolidation batches while
  preserving behavioral twins.

## [0.9.0] - 2026-08-23

### Added
- Sentinel permission matrix gates with escalation chain.
- jscpd duplication ratchet gate (`scripts/jscpd_check.py`).
- betterleaks staged-scan pre-commit hook; `requirements.txt` regenerated from `uv.lock`.

### Changed
- AGENTS.md code review rules v3 (rule-cited, diff-scoped blocking).
- Toolchain hardening: PEP 735 dev dependency group, exact `ty` pin, `uv audit` replaces pip-audit.

### Fixed
- Version surfaces aligned to pyproject source of truth (`bot/__init__.py`, this changelog).

## [0.8.0] - 2026-08-19

### Added
- Hygiene baseline for welcome-svg-foundation Cycle 1 (version sync, gitignore, config, README, .env docs, SHA-pinned CI).
- Preparation for `greeting_config.updatedAt` (additive nullable timestamptz) and incremental Realtime poll.

### Changed
- Version bump `0.1.0` → `0.8.0` to match `v0.8.0-qa-modernization` release state.

### Fixed
- `openspec/config.yaml` now declares `ty` (was `mypy`), coverage `0.75` (was `0.70`), review budget `800` (was `400`).
- `.gitignore` now covers `.ty_cache/`, `.hypothesis/`, `*.tsbuildinfo`, `**/.next/`.
- `.env.example` documents Discord, Supabase, and feature vars.

## [0.1.0] - Initial
- Initial project scaffold.
