# Archive Report: ops-hardening

**Change**: ops-hardening
**Archived**: 2026-07-08
**Mode**: openspec
**Verdict**: PASS WITH WARNINGS (user-approved override)

## Summary

Archived the `ops-hardening` change after full implementation and verification. All SQL migrations, structural tests, production verification, and zero-bot-diff criteria passed. Manual dashboard tasks remain pending (leaked password protection).

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| `rpc-least-privilege` | Created | NEW spec: 2 requirements, 6 scenarios (RPC EXECUTE revoked, Zero bot code impact) |
| `initial-schema` | Updated | 1 ADDED requirement: "Ticket channelId index" with 3 scenarios |

## Source of Truth Updated

- `openspec/specs/rpc-least-privilege/spec.md` — NEW (copied from delta)
- `openspec/specs/initial-schema/spec.md` — MODIFIED (appended Ticket channelId index requirement)

## Archive Contents

- `proposal.md` ✅
- `specs/` ✅ (2 domains: rpc-least-privilege, initial-schema)
- `design.md` ✅
- `tasks.md` ✅ (12/12 implementation tasks complete; 2 manual dashboard tasks pending)
- `verify-report.md` ✅
- `exploration.md` ✅
- `archive-report.md` ✅

## Verification Summary

| Check | Result |
|-------|--------|
| Migration tracking repaired (006-009) | ✅ |
| RPC grants revoked from anon/authenticated | ✅ |
| Security advisor: 0 RPC grant warnings | ✅ |
| Ticket channelId index exists | ✅ |
| Query uses index (Index Scan) | ✅ |
| Bot code untouched (`git diff bot/` empty) | ✅ |
| Structural tests: 27 passed | ✅ |
| Full suite: 971 passed, 3 skipped | ✅ |
| Coverage: 84.05% (threshold: 75%) | ✅ |
| TDD compliance: 6/6 | ✅ |

## Outstanding Warnings (User-Approved)

- **Manual dashboard task 4.1**: Enable "Leaked Password Protection" in Supabase Dashboard → Settings → Auth. NOT YET DONE.
- **Manual dashboard task 4.2**: Confirm toggle shows ENABLED. NOT YET DONE.
- **Engram reference**: #843 (leaked password protection still manual)
- **Ruff**: Pre-existing issues in `tests/test_migrations.py` outside this diff (not a blocker).

## Intentional Override

User explicitly approved archive with PASS WITH WARNINGS for the leaked password protection manual task. This is an ops-only toggle with no code artifact — tracked as follow-up work.

## SDD Cycle Complete

The change has been fully planned, implemented, verified, and archived. Ready for the next change.
