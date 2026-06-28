# Archive Report: Phase 5 — Welcome/Goodbye + Audit Logging

**Change**: phase-5-welcome-logging  
**Archived on**: 2026-06-16  
**Archived to**: `openspec/changes/archive/2026-06-16-phase-5-welcome-logging/`  
**Mode**: openspec  

---

## Task Completion

| Metric | Value |
|--------|-------|
| Total tasks | 14 |
| Completed | 14 |
| Incomplete | 0 |

All 14 tasks marked `[x]` in `tasks.md`.

---

## Verification Summary

**Verdict at archive time**: PASS WITH WARNINGS (post-fix)

- 233/235 tests pass (2 pre-existing Python 3.14 asyncio teardown flakes)
- 7/7 audit events wired in `AuditListener`
- Build: ✅ Passed

### Verify Report Discrepancy Note

The `verify-report.md` records a FAIL verdict with a CRITICAL issue: AuditListener only implementing 5 of 7 required events. This was accurate at verification time. A subsequent fix added `on_member_join` and `on_member_remove` listeners to `AuditListener` (confirmed in `bot/listeners/audit_listener.py` lines 88-108). The orchestrator confirmed "7/7 audit events wired" and "PASS WITH WARNINGS" at archive time.

---

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| mod-logging | Updated | 4 requirements modified: added `LoggingService` routing, `Previously:` provenance notes, new "Log via LoggingService" scenario |

### Merge Details (mod-logging)

- **Log actions to channel**: Updated description to reference `LoggingService`; added `Previously:` note; added new scenario "Log via LoggingService"
- **Skip logging when disabled**: Added `Previously:` provenance note
- **Skip logging when no channel configured**: Added `Previously:` provenance note
- **Include escalation actions**: Added `Previously:` provenance note

---

## Archive Contents

| Artifact | Status |
|----------|--------|
| proposal.md | ✅ |
| exploration.md | ✅ |
| specs/mod-logging/spec.md | ✅ |
| design.md | ✅ |
| tasks.md | ✅ (14/14 complete) |
| verify-report.md | ✅ |
| archive-report.md | ✅ |

---

## Warnings Carried Forward

1. **Python 3.14 asyncio teardown flakes**: 2 tests fail non-deterministically in full suite; pass in isolation. Environmental issue, not code bug.
2. **Spec/design mismatch on greeting config storage**: `greeting-config` spec says "in the guild record" but implementation uses separate `greeting_config` table (correct per design).
3. **Weak triangulation on enabled greeting dispatch**: `dispatch_welcome()`/`dispatch_goodbye()` enabled path only indirectly tested through `GreetingsCog`.
4. **No escalation-specific moderation logging test**: Auto-mute escalation path not explicitly covered.

---

## Files Changed (Implementation)

- `migrations/004_greeting_config.sql`
- `bot/models/greeting_config.py`
- `bot/core/database.py`
- `bot/services/logging_service.py`
- `bot/services/greeting_service.py`
- `bot/services/image_service.py`
- `bot/cogs/greetings.py`
- `bot/cogs/sentinel.py`
- `bot/listeners/audit_listener.py`
- `bot/bot.py`
- `tests/test_logging_service.py`
- `tests/test_greeting_service.py`
- `tests/test_greetings_cog.py`
- `tests/test_audit_listener.py`
- `tests/test_image_service.py`
- `tests/test_greeting_config.py`

---

## SDD Cycle Status

Phase 5 fully planned, implemented, verified (post-fix), and archived.  
Ready for the next change.
