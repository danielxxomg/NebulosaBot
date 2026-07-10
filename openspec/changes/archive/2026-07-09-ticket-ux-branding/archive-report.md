# Archive Report: Ticket UX & Branding Overhaul

**Change:** `ticket-ux-branding`
**Archived:** 2026-07-09
**Archived to:** `openspec/changes/archive/2026-07-09-ticket-ux-branding/`

## Verification Summary

- **Verdict:** PASS WITH WARNINGS
- **Tests:** 1268 passed, 3 skipped, 6 warnings
- **Coverage:** 85.33% (threshold: 70%)
- **Tasks:** 43/43 implementation tasks checked
- **Spec compliance:** 24/24 scenario groups compliant

No CRITICAL issues. Warnings are non-blocking (lint, mypy, test quality, static phrase assertions, post-delete notification risk).

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| `brand-tokens` | Created | New spec: brand color tokens, bot avatar footer, guild icon fallback, cog adoption |
| `channel-naming` | Created | New spec: `{category}-{username}-{number}` format, sanitize helper, all paths |
| `close-confirmation` | Created | New spec: ephemeral Confirm/Cancel, manual-only, owner-only confirm |
| `close-countdown` | Created | New spec: 5→1 edited message, auto-close silent |
| `unclaim-command` | Created | New spec: `/unclaim` hybrid, claimer/mod perms, audit logging |
| `docs-manual` | Updated | MODIFIED: expanded requirement with close confirm, unclaim, transfer, naming, branding scenarios |
| `ticket-invariants` | Updated | ADDED: unclaim permission check (3 scenarios). MODIFIED: status state machine (unclaim→open), permission matrix (unclaim=claimer OR mod), 3 new scenarios |
| `ticket-service` | Updated | ADDED: unclaim method, countdown flow, channel naming in service (8 scenarios). MODIFIED: ticket creation (sanitized naming), ticket close (countdown vs silent) |
| `ticket-views` | Updated | MODIFIED: actions view (close confirm, transfer confirm, non-author/non-mod gate), 5 new scenarios |

## Archive Contents

- `proposal.md` ✅
- `specs/` ✅ (9 delta specs)
- `design.md` ✅
- `tasks.md` ✅ (43/43 tasks complete)
- `verify-report.md` ✅
- `exploration.md` ✅
- `review-ledger.md` ✅

## Source of Truth Updated

The following specs now reflect the new behavior:
- `openspec/specs/brand-tokens/spec.md`
- `openspec/specs/channel-naming/spec.md`
- `openspec/specs/close-confirmation/spec.md`
- `openspec/specs/close-countdown/spec.md`
- `openspec/specs/unclaim-command/spec.md`
- `openspec/specs/docs-manual/spec.md`
- `openspec/specs/ticket-invariants/spec.md`
- `openspec/specs/ticket-service/spec.md`
- `openspec/specs/ticket-views/spec.md`

## Known Warnings (carried from verify-report)

1. Two ticket-view direct embeds still use `discord.Color.green()`/`greyple()` instead of brand tokens
2. Close callback attempts `channel.send()` after service has deleted the channel (post-delete notification risk)
3. Ruff (10 errors) and mypy (9 errors) in changed files
4. Static phrase assertions in manual tests (non-critical)
