# Proposal: Ticket Integrity Recovery

## Intent

Restore ticket lifecycle integrity and zombie-ticket repair. On HEAD `a5dc81f`, auto-close skips missing channels, deletion is only logged, and `close_ticket` lacks conditional `close_reason` transition. Quarantine artifacts are stale reference material.

## Scope

### In Scope
- Restore on-disk parity for production-applied migration 015 and verify it before reliance.
- Define integrity evidence/preflight, bounded reporting, idempotent conditional close/repair contracts, and audit outcomes.
- Specify hybrid entry points: authoritative `on_guild_channel_delete`, evidence-gated startup/hourly sweeps, and manual fallback.
- Add tests and a fresh verification report with staged gates. First slice: primitives, preflight/reporting, and contracts—not sweep wiring.

### Out of Scope
- Backups, retention, or G.4 backup activation/restore.
- `create_bot_archive.sh`, CI quality delta, greeting/dashboard polish, or wholesale quarantine merging.
- Automatic repair while G.2 deployment-compatibility evidence is unresolved.

## Capabilities

### New Capabilities
- None; recovery requirements extend existing capabilities.

### Modified Capabilities
- `database-layer`: migration 015 parity and safe schema/deployment preflight evidence.
- `ticket-model`: lifecycle-integrity evidence and repair-result contracts.
- `ticket-service`: conditional close/repair semantics, idempotency, bounds, auditability, and false-positive safety.

## Approach

Recover domain primitives with evidence-based preflight and dry-run/reporting boundaries. Then implement conditional close/repair, the authoritative channel-delete path, and evidence-gated sweeps with integration verification. Mutations are idempotent, bounded, auditable, and rate-limit aware; G.2 gates activation, while G.4 remains separate.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `migrations/015*` | Restored/verified | Re-establish migration parity. |
| `bot/models/`, `bot/services/`, `bot/core/db/` | Modified | Integrity contracts, preflight/reporting, lifecycle repair. |
| `bot/cogs/`, listeners, tests, verification artifacts | Modified | Staged entry points and evidence. |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| G.2 evidence is insufficient | High | Keep automatic repair disabled until deployment/migration evidence passes. |
| False positives or rate limits | High | Corroborating evidence, conditional updates, bounded batches, dry runs, audit logs, and backoff. |
| Migration parity mismatch | Med | Restore and verify before dependent work. |

## Rollback Plan

Disable repair gates and revert only this slice; retain reports, leave tickets untouched, and restore prior close/channel-delete behavior. Do not activate sweeps or rely on migration 015 until parity returns.

## Dependencies

- Production/schema evidence for migration 015 and resolved G.2 deployment compatibility.
- Current specs and a new verification report; quarantine remains reference-only.

## Success Criteria

- [ ] Migration 015 is tracked on disk and safely verified against production prerequisites.
- [ ] Repair contracts are tested for idempotency, bounds, auditability, false positives, and rate limits.
- [ ] Entry points have explicit activation gates; automatic repair remains blocked when G.2 evidence is unresolved.
- [ ] A fresh verification report proves the staged slice without claiming quarantine completeness.
