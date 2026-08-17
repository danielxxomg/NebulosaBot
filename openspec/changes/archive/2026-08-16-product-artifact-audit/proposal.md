# Proposal: Product Artifact Audit

## Intent

Two active changes own the same ticket-integrity lifecycle and disagree: `ticket-integrity-reconciliation` claims all phases complete with no `verify-report.md`; `ticket-integrity-recovery` honestly stops after PR1/PR2. The audit also found channel-delete only logging, no sweep/manual repair wiring, and a stale TI-020 fixture. This change completes one bounded recovery cluster before any completion claim. Live Supabase evidence now recovered (2026-08-11, read-only) — see Dependencies for scope and boundary.

## Scope

### In Scope
- Make `ticket-integrity-recovery` canonical; supersede `ticket-integrity-reconciliation` by porting useful requirements and historical evidence into recovery's deltas, then archive.
- One idempotent evidence/repair path shared by channel-delete handling, sweeps, and manual fallback. Ambiguous cases enter a reviewable quarantine state, never mutated.
- Dual-audience bounds: guild admins act on their guild only; bot operators get systemic diagnosis. Actor attribution is informational only.
- Mark stale/diagram product-intent claims as shipped/deprecated/aspirational (governance only).

### Out of Scope
- Dashboard expansion, i18n, economy, moderation, giveaways/profile, broad RLS/Realtime remediation, archive cleanup, G.4 backup activation.

## Capabilities

### New Capabilities
- None. Quarantine and operator diagnosis reuse existing capabilities.

### Modified Capabilities
- `ticket-service`: idempotent conditional close/repair, evidence-gated sweep, manual fallback, reviewable quarantine, dual-audience bounds.
- `ticket-model`: integrity evidence, repair-result, quarantine-status contracts.
- `ticket-invariants`: denied-audit corroboration; quarantine never audited as mutation.
- `audit-listener`: authoritative `on_guild_channel_delete` routing to shared repair path; non-actor attribution.
- `database-layer`: migration 015 on-disk parity and deployment preflight evidence.
- `logging-service`: operator-grade systemic diagnosis distinct from per-guild admin audit.

## Approach

Adopt `ticket-integrity-recovery` as canonical; port complementary reconciliation deltas (CloseResult, close-reason mapping, localization, ordering). Extend TI-020 tests first, then the shared idempotent repair path (corroboration, bounded batches/backoff, immutable evidence). Schema/deployment preflight (G.2) is now verified via live read-only evidence; automatic mutation stays gated by BOTH verified preflight AND fresh per-ticket Discord channel-existence corroboration. Missing Discord corroboration → dry-run/report/queue only, never silent mutation.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `openspec/changes/ticket-integrity-recovery/` | Modified | Canonical; absorbs reconciled deltas + fresh verify. |
| `openspec/changes/ticket-integrity-reconciliation/` | Removed | Superseded; requirements ported, evidence preserved. |
| `bot/services/ticket_service.py`, `bot/core/db/ticket_db.py` | Modified | Conditional close/repair, quarantine state. |
| `bot/listeners/audit_listener.py` | Modified | Authoritative channel-delete routing. |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Reconciliation deltas lost on retirement | Med | Port before archive; preserve evidence. |
| False-positive repair | High | Mutation needs BOTH verified schema/deployment preflight AND fresh per-ticket Discord corroboration; conditional updates + audit; record limitation, never claim resolved. |
| Discord existence unverifiable from DB alone | High | Live DB confirms non-null `channelId`, not channel existence; require Discord corroboration per ticket before any mutation, else dry-run/report/queue. |

## Rollback Plan

Disable repair gates; revert each chained slice within its file boundary. Leave tickets untouched; restore deletion-only logging. Never reverse migration 015 or activate G.4.

## Dependencies

- `ticket-integrity-reconciliation` deltas as port source (not authoritative completion).
- Verified live Supabase evidence (2026-08-11, read-only) — schema/deployment preflight ONLY: project `ACTIVE_HEALTHY`; migration `015_ticket_lifecycle_reliability` applied; `ticket.closeReason` nullable; required active-channel/slot + guild ticket indexes present; Realtime pub covers `guild`, `greeting_config`, `ticket`, `ticket_note`; 3 active ticket rows all non-null `channelId`. This does NOT prove those Discord channels currently exist — per-ticket Discord corroboration is STILL UNRESOLVED and required before automatic repair.
- Out-of-scope (documented for boundary, not addressed): Security Advisor 1 WARN (leaked-password protection) + 9 INFO (`rls_enabled_no_policy`) — tech debt, later pass.

## Success Criteria

- [ ] One authoritative `ticket-integrity-recovery` lifecycle; reconciliation superseded with requirements preserved.
- [ ] Channel-delete + sweeps + manual fallback share one idempotent path; ambiguous cases quarantine, never mutate.
- [ ] Dual-audience bounds enforced; actor attribution informational only.
- [ ] `verify-report.md` proves the cluster; preflight verified via live evidence, Discord-corroboration limitation recorded, never claimed resolved.
- [ ] Denied-audit and guild-scope contract cases green; stale product-intent claims classified.
