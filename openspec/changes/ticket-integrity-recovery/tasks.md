# Tasks: Ticket Integrity Recovery

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Est. changed lines | ~1100–1400 (RED+GREEN, 5 units) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 → PR 5 |
| Delivery strategy | auto-forecast |
| Chain strategy | feature-branch-chain |
| Review budget (active) | 1500 lines (override of config 400) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

> `auto-forecast`: the maintainer selected `feature-branch-chain`; each unit stays below 400 lines so every child diff remains focused.

### Suggested Work Units

| Unit | Goal | PR | Focused test | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | 015 parity + domain/preflight | PR 1 | `uv run pytest tests/test_migrations.py tests/test_ticket_model.py tests/test_ticket_integrity.py -q` | N/A — read-only primitives; no live channel until PR 3 | `migrations/015_*`, `bot/models/ticket.py` dataclasses, `bot/services/integrity_report.py`, `bot/config.py` bounds; G.2 default-unresolved = nothing activates |
| 2 | Conditional DB + `close_ticket` repair, G.2-gated | PR 2 | `uv run pytest tests/test_ticket_db.py tests/test_ticket_service.py -q` | N/A — fake Supabase catalog; no Discord API at unit layer | `ticket_db.py` lookup + `transition_ticket_to_closed`, `ticket_service.py` zombie/`close_reason`; normal close UX untouched |
| 3 | Authoritative `on_guild_channel_delete` repair | PR 3 | `uv run pytest tests/test_audit_listener.py -q` | `uv run pytest tests/integration/test_ticket_flow.py -q` (mocked guild/channel) | `audit_listener.py` to deletion-only; inert when G.2 unresolved |
| 4 | Evidence-gated sweeps + manual fallback, bounded | PR 4 | `uv run pytest tests/test_tickets_cog.py -q` | `uv run pytest tests/integration/test_ticket_flow.py -q` (`@tasks.loop`, mocked bot) | `tickets.py` sweep wiring + mod command; PR 2 service stays unwired |
| 5 | Integration/regression + fresh evidence | PR 5 | `uv run pytest -q && python -m py_compile bot/__main__.py` | Full suite + build; artifacts under change folder | `tests/integration/test_ticket_flow.py` additions + verify-report; prior slices stay landed |

## Phase 1: Domain/Evidence/Preflight + 015 Parity (PR 1)

- [x] 1.1 RED `tests/test_migrations.py`: assert `migrations/015_*` absent (fails), then present + schema-matched to production-applied; `incompatible` on mismatch. Threat: Migration rollout.
- [x] 1.2 Restore `migrations/015_ticket_lifecycle_reliability.sql` from production-applied definition; parity only — never mark a new migration as applied.
- [x] 1.3 GREEN: `tests/test_migrations.py` passes; no re-apply/down-migrate.
- [x] 1.4 RED `tests/test_ticket_model.py` + `tests/test_ticket_integrity.py`: `IntegrityEvidence` ser/de; `corroborated` true only when `open`/`claimed` AND `channel_exists=False`; `to_db_dict` camelCase; no mutation. `RepairResult` action/outcome enums; `already_closed`/`skipped`/`error` determinism.
- [x] 1.5 GREEN: add frozen `IntegrityEvidence`, `RepairResult` to `bot/models/ticket.py` (`from_db_row`/`to_db_dict`).
- [x] 1.6 RED `tests/test_ticket_integrity.py`: preflight `resolved` only with 015 parity + supported mode + no drift; else `gate_unresolved`; never mutates ticket row. Threat: Environment evidence.
- [x] 1.7 GREEN: create `bot/services/integrity_report.py` (parity + mode + drift); modify `bot/config.py` for batch/backoff constants only.

## Phase 2: Conditional DB + Repair Service (PR 2 — G.2-gated)

- [x] 2.1 RED `tests/test_ticket_db.py`: `transition_ticket_to_closed(expected_statuses=("open","claimed"), close_reason=...)` closes or `already_closed`; guild-scoped active lookup by `(guild_id, channel_id)`.
- [x] 2.2 GREEN: add active lookup + `transition_ticket_to_closed` to `bot/core/db/ticket_db.py`; no read-then-write race.
- [x] 2.3 RED `tests/test_ticket_service.py`: `close_reason=None` MUST NOT overwrite; zombie path skips transcript + channel deletion; re-close raises `ValueError`, no mutation.
- [x] 2.4 GREEN: modify `bot/services/ticket_service.py` — optional `close_reason`, zombie branch, `ValueError` on already-closed.
- [x] 2.5 RED `tests/test_ticket_service.py`: `RepairResult` for `repaired`/`already_closed`/`skipped`/`error`; transient Discord error → `error` with reason class name. Threat: False positives.
- [x] 2.6 GREEN: repair builds `RepairResult` from `IntegrityEvidence` via `transition_ticket_to_closed`; mutations stay G.2-gated in tests.
## Phase 3: Authoritative `on_guild_channel_delete` (PR 3)

- [ ] 3.1 RED `tests/test_audit_listener.py`: duplicate event + cross-guild lookup map to correct ticket only; deletion logging retained. Threat: Event routing.
- [ ] 3.2 RED same: transient `discord.HTTPException` check → `skipped`, no mutation. Threat: Discord/API integration.
- [ ] 3.3 RED same: G.2 unresolved → logs detection, no `close_ticket`; resolved → conditional close, `closeReason="zombie:channel_deleted"`.
- [ ] 3.4 RED same: concurrent duplicate events → exactly one `repaired`, second `already_closed`.
- [ ] 3.5 GREEN: modify `bot/listeners/audit_listener.py` `on_guild_channel_delete` — retain logging then active lookup + G.2 gate + conditional repair (no-op when no mapping).

## Phase 4: Sweeps + Manual Fallback (PR 4 — bounded/rate-limit safe)

- [ ] 4.1 RED `tests/test_tickets_cog.py`: bounded batch (50/250); 429 → skip + backoff, no rate-limit breach. Threat: Rate limits.
- [ ] 4.2 RED same: dry-run only when G.2 unresolved; corroborated-close when resolved; missing-evidence candidate → `skipped`, no mutation.
- [ ] 4.3 GREEN: modify `bot/cogs/tickets.py` startup/hourly `@tasks.loop` → bounded service sweep with backoff.
- [ ] 4.4 RED `tests/test_tickets_cog.py`: mod `userM` manual repair closes corroborated zombie, `closeReason="zombie:manual_repair"`, audit `actorId=userM`; non-zombie `skipped`; idempotent re-run `already_closed`.
- [ ] 4.5 GREEN: add moderator manual-repair command to `bot/cogs/tickets.py` as thin delegator (G.2-gated; idempotent + bounded).

## Phase 5: Idempotency/Audit + Integration + Fresh Evidence (PR 5)

- [ ] 5.1 RED `tests/test_ticket_service.py`: idempotent re-run → no second close; audit-insert failure → close persists + WARNING. Threat: Audit best-effort.
- [ ] 5.2 GREEN: every repair path emits `RepairResult` + best-effort `ticket_audit` (`actorId="system"` auto/sweep, mod id manual); re-run after `already_closed` deterministic no-op.
- [ ] 5.3 RED `tests/integration/test_ticket_flow.py`: disabled slice leaves tickets untouched; deletion-only logging continues when gate off. Threat: Rollback/no-op.
- [ ] 5.4 GREEN: rollback flag/gate wiring; no-op run emits no `RepairResult(action="close")` and no repair audit rows.
- [ ] 5.5 Verify: `uv run pytest tests/test_ticket_integrity.py tests/test_ticket_model.py tests/test_ticket_db.py tests/test_ticket_service.py tests/test_audit_listener.py tests/test_tickets_cog.py tests/integration/test_ticket_flow.py tests/test_migrations.py -q`; then `uv run pytest` and `python -m py_compile bot/__main__.py`. Write fresh evidence in `verify-report.md`.

## Cross-Cutting Evidence (no activation until recorded)

- [ ] E.1 G.2 fresh-evidence: log authoritative deployment/migration evidence sufficient to flip `resolved` (else leave `gate_unresolved`). Maintainer says G.2 works operationally, but NO repair mutation runs until evidence is recorded.
- [ ] E.2 Ticket #3 corroboration: re-verify #3 against current DB + channel state; do NOT inherit stale quarantine receipt; record (corroborated / not present / unknown) without mutation.
- [x] E.3 Migration parity checks (per 1.1): filename, schema objects, applied-status MUST match production before any unit relies on 015; `incompatible` keeps G.2 unresolved.

Out of scope: backups/retention, `create_bot_archive.sh`, CI quality delta, greetings/dashboard polish, wholesale quarantine merge.
