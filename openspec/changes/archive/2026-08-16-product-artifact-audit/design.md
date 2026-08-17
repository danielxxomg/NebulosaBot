# Design: Product Artifact Audit

## Technical Approach

`ticket-integrity-recovery` remains canonical. Extend the existing `TicketService`
repair coordinator so channel-delete events, bounded sweeps, and manual repair use
one evidence-gated, guild-scoped conditional transition. The listener preserves
deletion logging; adapters discover candidates and bounds, while services own
authorization, evidence evaluation, mutation, and result/audit mapping.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| Coordinator | Extend `TicketService.repair_ticket_from_evidence`. | Parallel repair API. | One gate and one DB race boundary prevent divergent behavior. |
| Evidence freshness | Source-specific, immutable, single-use evidence. | Shared evidence cache or redundant event lookup. | An exact delete event already proves the observed guild/channel deletion; independent attempts need current observations. |
| Authority | Provisional one-role core model plus scoped owner/admin exceptions. | Mandatory parallel specialized roles or global bypass. | It reduces configuration ambiguity while preserving multi-guild isolation. |
| Quarantine/concurrency | Result-only quarantine; one conditional active-to-closed update. | Persistent `quarantined` ticket status or unconditional close. | Active/closed remains authoritative and duplicate attempts have one winner. |

## Data Flow and Contracts

```text
delete event ── immediate event evidence ──┐
sweep/manual ── fresh Discord probe ───────┼─→ coordinator/gates ─→ DB conditional close ─→ audit/result
                                          └─→ quarantine/no-op on uncertainty
```

`on_guild_channel_delete` supplies immediate, exact guild/channel evidence for
that event only; the coordinator MUST NOT make a Discord lookup solely to
rediscover the deletion. Every sweep and manual attempt MUST perform a fresh
Discord probe. Evidence is never reused across independent attempts. Only an
explicit, guild-matched absence is corroborating. 403, timeout, rate limit,
missing permission, unknown, conflicting, future-dated, or stale responses are
unresolved and quarantine/no-op; they never imply absence. Mutation also requires
current read-only schema/deployment preflight.

```python
repair_ticket_from_evidence(
    evidence: IntegrityEvidence,
    preflight: PreflightResult,
    source: RepairSource,
    authority: RepairAuthority,
) -> RepairResult
```

`IntegrityEvidence` carries immutable ID, guild/channel/ticket, source,
observation time, tri-state existence, and corroboration. `RepairResult` carries
source/evidence, outcome, and non-empty reason. The DB filters guild, ticket, and
active status; its conditional transition is the one-winner boundary. Adapters
never mutate ticket state.

## Authority Model

One canonical configurable moderator-like role is the only core role. Specialized
roles are optional refinements, never mandatory parallel permission sources. The
configured role supplies normal guild-scoped operational authority where the
action contract permits it. Guild owner and Discord Administrator may bypass the
configured-role check only inside their own guild. The Discord application/bot
owner receives global diagnosis, not a silent cross-guild mutation bypass. Any
global mutation requires an explicit, targeted, confirmed, audited grant naming
actor, scope, target, and outcome. Deletion actors remain informational.

## File Changes

| File | Action | Responsibility |
|---|---|---|
| `bot/models/ticket.py` | Modify | Immutable evidence/result contracts. |
| `bot/services/ticket_invariants.py` | Modify | Evidence gates and provisional authority checks. |
| `bot/services/ticket_service.py` | Modify | Shared coordinator, batches, retries, and outcomes. |
| `bot/core/db/ticket_db.py`, `ticket_audit_db.py`, `integrity_report.py` | Modify | Scoped lookup/transition, audit persistence, read-only preflight. |
| `bot/listeners/audit_listener.py`, `bot/cogs/tickets.py` | Modify | Event, sweep, and manual adapters only. |
| `bot/services/logging_service.py` | Modify | Guild audit versus global diagnosis. |

No new table, lifecycle status, coordinator, or migration is required.

## Testing Strategy

Strict TDD RED tests cover immediate event evidence without a redundant probe;
fresh probe-per-attempt for sweeps/manual repair; every listed uncertain response;
preflight, serialization, guild filters, one-winner duplicate races, audit
failure, bounds, and backoff. Authority tests cover same-guild role/owner/admin,
cross-guild denial, global diagnosis, and explicit targeted operator mutation.
Contract tests cover every result outcome. Integration tests use fake Supabase
and mocked Discord across all entry points; live checks remain read-only.

## Threat Matrix

| Boundary | Applicability, safe/failure behavior, planned RED |
|---|---|
| Event routing/process integration | **Applicable** — all sources converge; event evidence is single-use, probes are per-attempt; duplicate RED proves one winner. |
| Discord API/rate limits | **Applicable** — 403/timeout/429/permission failures defer to quarantine/no-op; RED covers each class. |
| False positives | **Applicable** — only matched explicit absence permits mutation; unknown/conflict/stale RED blocks it. |
| Environment evidence | **Applicable** — unresolved preflight never mutates; RED covers stale/missing schema evidence. |
| Migration rollout | **Applicable** — verify 015 only; never apply/reverse; mismatch RED. |
| Documentation-like paths | **N/A** — no documentation is executed. |
| Git repository selection, commit state, push state, PR commands | **N/A** — no VCS or PR automation exists in this runtime path. |

## Migration / Rollout

No migration required. Roll out disabled-by-default: preflight, detection/reporting,
manual delegation, then sweeps. Rollback disables repair and restores
deletion-only logging without touching tickets or migration 015. A future dedicated
SDD permission audit—not this recovery—will review `/setup`, guild config, checks,
and the complete capability matrix.

## Open Questions

None blocking. Evidence freshness and the provisional authority model are resolved
above; their implementation must preserve those decisions.
