# Review Ledger: harden-command-permissions

**Phase**: design (Judgment Day Round 1)
**Date**: 2026-07-11
**Artifact store**: openspec

## Verdict synthesis

| Bucket | Count | Notes |
|--------|------:|-------|
| Confirmed (both judges) | 0 | No dual-judge BLOCKER/CRITICAL convergence |
| Suspect (one judge) | 1 | JD-B-001 non-member prefix denial test gap |
| Contradiction | 0 | |
| INFO (WARNING/SUGGESTION) | 7 | JD-B-002..008 |

**JUDGMENT: APPROVED** (design) — core security design is sound.

## Apply Round 1 (post-implementation)

| Bucket | Count | Notes |
|--------|------:|-------|
| Confirmed (both judges) | 0 | Judge A empty; Judge B 1 CRITICAL suspect |
| Suspect | 1 | JD-B-APP-001 false-closure on non-member test — remediated |
| INFO | several | message wording, coverage edges |

**Remediation applied**:
- Dedicated non-member prefix test + message fix
- Admin-with-configured-role scenario test
- Malformed cache + `_user_has_role(User)` tests
- Real `SentinelCog.warn` dual-path wiring test

**JUDGMENT: APPROVED** (apply, after remediation) — production dual-path gate closed; proof suite complete.

## Findings

| id | lens | location | severity | status | evidence |
|----|------|----------|----------|--------|----------|
| JD-B-001 | judgment-day | design.md testing vs tasks.md Phase 1 | CRITICAL | open | Suspect only (Judge A empty). Non-member (`User` not `Member`) prefix denial has no dedicated RED task despite design table. |
| JD-B-002 | judgment-day | design/proposal error-handler attribution | WARNING | info | Prefix errors handled by global `on_command_error`, not cog handlers. |
| JD-B-003 | judgment-day | proposal vs design vs tasks resolver shape | WARNING | info | Prefer design: shared bot/guild_id resolver + thin wrappers. |
| JD-B-004 | judgment-day | dual registration proof | WARNING | info | Integration test should assert both prefix and slash checks non-empty. |
| JD-B-005 | judgment-day | coverage gate 70 vs 75 | WARNING | info | Real gate is 75%. |
| JD-B-006 | judgment-day | MissingRole scenario precondition | WARNING | info | Spec scenario should state configured mod role in GIVEN. |
| JD-B-007 | judgment-day | cog count | SUGGESTION | info | 8 cogs not 9. |
| JD-B-008 | judgment-day | test count estimates | SUGGESTION | info | Narrative undercounts Phase 1 tasks. |

Judge A: empty ledger.
