# Design: Ticket Integrity Recovery

## Technical Approach

Recover the missing migration parity and add a read-only G.2 preflight before wiring repair. Keep Discord interaction in cogs/listeners and put evidence, bounded reconciliation, conditional transitions, and audit handling in services/DB. Preserve existing close UX, transcript behavior, embeds, and cache invalidation. Quarantine artifacts are reference only; stale receipts, including ticket #3, are not current evidence.

## Architecture Decisions

| Decision | Alternatives / rationale |
|---|---|
| Use authoritative `on_guild_channel_delete` as the fastest automatic path | It is stronger than a sweep because Discord supplies the deletion event; still require guild+channel active lookup and G.2. |
| Make conditional close the sole repair mutation | Avoids read-then-write races: DB updates only `open`/`claimed`; a loser becomes deterministic `already_closed`. |
| Keep sweeps evidence-gated, bounded, and rate-limit safe | Startup/hourly reconciliation is useful but weaker than an event; unresolved G.2 means dry-run only. |
| Keep manual repair as a moderator fallback | It still requires corroborated evidence and bounds; the delta currently allows it outside automatic G.2, pending operational confirmation. |

## Data Flow

```text
delete event → audit log → active DB lookup → G.2 gate → conditional close → RepairResult + best-effort audit
startup/hourly → bounded candidates → channel check → IntegrityEvidence → gate/dry-run → conditional close
manual mod → ticket lookup → channel check → IntegrityEvidence → repair service → result + mod audit
```

## File Changes

**Domain/preflight:** Create `migrations/015_ticket_lifecycle_reliability.sql` from the production-applied definition; modify `bot/models/ticket.py` with frozen `IntegrityEvidence`/`RepairResult`; create `bot/services/integrity_report.py` for parity, deployment-mode, and schema-drift evidence. Modify `bot/config.py` only for bounded batch/backoff settings. No changes to `bot/views/tickets.py` or `bot/utils/embeds.py`.

**Conditional close:** Modify `bot/core/db/ticket_db.py` with guild-scoped active lookup and `transition_ticket_to_closed`; modify `bot/services/ticket_service.py` so normal close preserves transcript/channel deletion, zombie close skips both, and `close_reason=None` does not overwrite.

**Channel-delete:** Modify `bot/listeners/audit_listener.py` to retain deletion logging and delegate repair after authoritative lookup/preflight; no repair when G.2 is unresolved.

**Sweeps:** Modify `bot/cogs/tickets.py` startup/hourly tasks to call the bounded service sweep; add the moderator manual-repair command as a thin delegator. Automatic sweep wiring follows migration parity verification.

**Integration tests:** Extend `tests/test_ticket_model.py`, `tests/test_ticket_db.py`, `tests/test_ticket_service.py`, `tests/test_audit_listener.py`, and `tests/test_tickets_cog.py`; add focused `tests/test_ticket_integrity.py`, migration parity cases in `tests/test_migrations.py`, and event/sweep harness cases in `tests/integration/test_ticket_flow.py`.

## Interfaces / Contracts

```python
IntegrityEvidence(ticket_id, guild_id, channel_id, status,
                  channel_exists: bool, corroborated: bool)
RepairResult(ticket_id, guild_id, action, outcome, reason,
             evidence_id, timestamp)
await db.transition_ticket_to_closed(
    ticket_id, expected_statuses=("open", "claimed"), close_reason=...
) -> dict[str, Any] | None
```

`IntegrityEvidence` is derive-only; `corroborated` requires an active DB mapping and a completed channel check returning false. Unknown/transient checks produce `skipped`, not evidence. Preflight returns `resolved` or `gate_unresolved` and never mutates tickets. Audit insertion is best-effort and logs WARNING on failure.

## Testing Strategy

Strict TDD: RED first, then focused unit tests for serialization, parity/gate outcomes, guild scoping, conditional races, idempotency, audit failure, bounds, and 429/5xx backoff. Runtime harnesses use fake Supabase catalog/rows and mocked Discord guild/channel APIs—never the Discord API. Run: `uv run pytest tests/test_ticket_integrity.py tests/test_ticket_model.py tests/test_ticket_db.py tests/test_ticket_service.py tests/test_audit_listener.py tests/test_tickets_cog.py tests/integration/test_ticket_flow.py -q`; then `uv run pytest tests/test_migrations.py -q`, `uv run pytest`, and `python -m py_compile bot/__main__.py`.

## Threat Matrix

| Boundary | Applicability, safe/failure behavior, planned RED test |
|---|---|
| Event routing | Applicable: always log delete; unresolved gate/no mapping is no-op. RED duplicate event and cross-guild lookup. |
| Discord/API process integration | Applicable: authoritative event repairs; API/network errors never mutate. RED transient channel check. |
| Rate limits | Applicable: bounded batches, backoff, skip candidate on 429/5xx. RED 429 continuation. |
| False positives | Applicable: active mapping plus completed missing-channel proof only. RED existing channel/unknown check. |
| Environment evidence | Applicable: missing deployment/schema evidence returns `gate_unresolved`. RED unsupported mode and no ticket mutation. |
| Migration rollout | Applicable: restore/compare 015 before dependent wiring; never re-apply or down-migrate. RED parity mismatch. |
| Documentation-like paths | N/A: no executable-file classification. |
| Git selection/commit/push/PR boundaries | N/A: no Git, shell, subprocess, or PR automation. |

## Migration / Rollout

Restore 015 on disk, compare filename/schema objects/applied status with production, and keep G.2 unresolved while deployment compatibility is unknown. Roll out domain/preflight, then conditional close, event path, and finally sweeps/manual entry points. G.4 backup/restore and `create_bot_archive.sh` remain separate changes. Rollback disables the repair gate/flag, retains reports, leaves tickets untouched, and restores deletion-only logging; do not drop a production-applied migration.

## Open Questions

- [ ] What authoritative deployment/migration evidence source resolves G.2?
- [ ] Is ticket #3 still present and corroborated? Do not treat the stale receipt as evidence.
- [ ] Is category-name normalization part of 015 parity only, or this change's scope?
- [ ] Is manual repair explicitly permitted to bypass G.2, as the delta currently states?
