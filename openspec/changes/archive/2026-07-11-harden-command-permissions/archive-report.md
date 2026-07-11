# Archive Report: Harden Command Permissions

**Change**: `harden-command-permissions`
**Archived**: 2026-07-11
**Archived to**: `openspec/changes/archive/2026-07-11-harden-command-permissions/`
**Artifact store**: openspec

## Verification Summary

| Field | Value |
|-------|-------|
| Verdict | PASS WITH WARNINGS |
| Blockers | 0 |
| Critical findings | 0 |
| Requirements | 2/2 |
| Scenarios | 11/11 |
| Tests passed | 1509 |
| Coverage | 88.22% (threshold: 75%) |

## Task Completion

| Phase | Tasks | Status |
|-------|-------|--------|
| Phase 1: RED | 8/8 | ✅ Complete |
| Phase 2: GREEN | 6/6 | ✅ Complete |
| Phase 3: Regression | 3/3 | ✅ Complete |
| **Total** | **17/17** | **✅ All checked** |

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| permission-model | Updated | 2 modified requirements (Moderator check, Unconfigured moderator role) |

### Requirements Changed

**Moderator check** — MODIFIED:
- Expanded from generic role/admin check to explicit dual-path enforcement (`commands.check` + `app_commands.check`)
- Added 8 scenarios covering prefix path (admin pass, mod role, regular user denied, DM denied, dual registration proof) and slash path preservation
- Preserved slash-path regression contract

**Unconfigured moderator role** — MODIFIED:
- Extended from slash-only denial to BOTH prefix and slash paths
- Added 2 new scenarios: missing mod role via prefix (`CheckFailure`), admin passes when unconfigured via prefix

**Preserved (untouched)**:
- Administrator check (2 scenarios)
- Ban command requires administrator (2 scenarios)

## Archive Contents

- proposal.md ✅
- specs/permission-model/spec.md ✅
- design.md ✅
- tasks.md ✅ (17/17 tasks complete)
- verify-report.md ✅
- apply-progress.md ✅
- explore.md ✅
- review-ledger.md ✅

## Source of Truth Updated

- `openspec/specs/permission-model/spec.md` — merged delta; 4 requirements, 13 scenarios

## Warnings (non-blocking)

1. **Stale TDD receipt metadata** — `apply-progress.md` reports 7 tests/23 in-module/1504 suite; current evidence is 12 tests/27 in-module/1509 suite. Audit-receipt issue only; does not affect runtime proof.
2. **Task 1.2 triangulation label** — describes "admin + non-admin" but both current cases are administrator variants. Metadata inaccuracy only.

## Archive Classification

**Intentional archive with warnings** — PASS WITH WARNINGS, no CRITICAL blockers. Runtime authorization proof is complete. TDD receipt metadata is stale but does not affect the security remediation's correctness.
