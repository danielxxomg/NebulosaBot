# Tasks: refactor-ticket-domain S2 — Bounded Seams

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Total | 1200–1500 (S2.1 250–300, S2.2 300–400, S2.3 300–400, S2.4 350–400) |
| 800-line risk | Low (each ≤800) |
| Chained PRs | Yes — 4 stacked to main S2.1→S2.2→S2.3→S2.4 |
| Delivery | auto-chain |
| Chain | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low
800-line budget risk: Low

### Suggested Work Units

| Unit | Goal | PR | Focused test | Harness | Rollback boundary |
|------|------|-----|--------------|---------|-------------------|
| 1 | Typed `NebulosaContext`, 28 mypy, `is_mod` | PR1 | `mypy bot tests; pytest -k is_mod` | N/A types | `bot/core/context.py`, `bot/cogs/sentinel.py`, `utility.py`, `bot/utils/checks.py` |
| 2 | Guild-aware DB, cross-guild denial | PR2 | `pytest -k guild_scope` | N/A DB | `bot/core/db/ticket*.py`, `bot/services/ticket_service.py` |
| 3 | Verifier → `SchemaInventory`, live marker | PR3 | `pytest -k verifier` | `pytest -m live` gated/skip | `bot/services/schema_inventory.py`, `integrity_report.py` |
| 4 | Repair `evaluate_repair_eligibility`, facade | PR4 | `pytest -k repair` | mocked delete/sweep | `bot/services/ticket_service.py`+adapter |

## S2.1 Typed Surface (PR1→main)

- [ ] 1.1 RED `tests/test_context_typing_chars.py`+`tests/test_checks_is_mod.py` (23 decorator+21 inline, fail-closed). `pytest -k "is_mod or context"` fails.
- [ ] 1.2 `bot/cogs/sentinel.py`,`utility.py`→`NebulosaContext`/`Context[NebulosaBot]`; keep `interaction`; no broad `Any`. `mypy bot` 0.
- [ ] 1.3 Fix 28 `mypy tests` errors. `mypy bot tests` 0.
- [ ] 1.4 Gate `ruff check bot tests` 0 · `pytest -q` 1814 pass · `pre-commit` pass.

## S2.2 Guild DB (PR2→PR1)

- [ ] 2.1 RED `tests/test_guild_scope_gaps.py` denial for 12 gaps (`get_ticket`,`get_ticket_by_channel`,`update_ticket`,`get_tickets_by_parent`,`get_ticket_category`,`delete_ticket_category`,`insert_ticket_note`,`get_ticket_notes`,`delete_ticket_note`,`get_recent_notes_for_dedup`,`insert_audit_row`,`get_audit_rows`). `pytest -k guild_scope` fails.
- [ ] 2.2 Guild-aware entry points `bot/core/db/ticket_db.py`,`ticket_category_db.py`,`ticket_note_db.py`,`ticket_audit_db.py` (`WHERE guildId=:gid AND id=:id`, ownership before mutate).
- [ ] 2.3 Migrate one vertical `bot/cogs/tickets.py`+`bot/services/ticket_service.py` facade; keep old only if non-mutating/non-disclosive; note/audit denial reason non-empty. `pytest -k "guild or audit"` pass.
- [ ] 2.4 No DDL/migration. `mypy bot` 0 · `pytest -q` pass.

## S2.3 Live Verifier (PR3→PR2)

- [ ] 3.1 RED `tests/test_schema_inventory_verifier.py` mocked: 9 zero-policy RLS, 6 CASCADE FKs, 4 CDC (`guild,greeting_config,ticket,ticket_note`), 19 migrations, 12 gaps; drift→`resolved=False`+reason; no DDL.
- [ ] 3.2 Binder `bot/services/schema_inventory.py`+`integrity_report.py`: typed `SchemaInventory` (`no_ddl=True`, `SELECT` only `pg_constraint/pg_policies/pg_publication_tables/pg_stat_user_indexes`, anon/publishable→deny).
- [ ] 3.3 Opt-in `live` marker (`pytest -m live`) credential-gated; default `pytest` mocked-only skips live; live no DDL. `pytest -m live --collect-only`.
- [ ] 3.4 Gate `ruff` 0 · `mypy bot tests` 0 · `pytest -q` pass.

## S2.4 Repair Seam (PR4→PR3)

- [ ] 4.1 RED `tests/test_repair_eligibility.py`+`test_repair_convergence.py` for `evaluate_repair_eligibility(preflight_allows,corroborated)`→`skipped gate_unresolved|evidence_unresolved`, corroborated→one winner/second→`already_closed`.
- [ ] 4.2 Extract adapters behind `TicketService` facade (`handle_channel_delete`,`sweep_integrity`,`repair_ticket_by_ref|from_evidence`→adapter); single seam; no duplicated gate/evidence, no direct mutate; race via `transition_ticket_to_closed(guild_id,ticket_id)`.
- [ ] 4.3 Preserve `TicketService`,`TicketsCog`,`TicketPanelView`/`TicketActionsView`, IDs `ticket:open|claim|close|edit-category`,`timeout=None`+`bot.add_view()`, guild-scoped `get_ticket_by_number`.
- [ ] 4.4 Gate `ruff` 0 · `mypy bot` 0 · `pytest -q` 1814 pass · `pre-commit` pass.

## Out of Scope → S3

Lifecycle/query/views relocation · RLS policies · FK DDL/`migrations/*.sql` · economy/invalidation

## Per-PR Gates

`ruff` 0 · `mypy bot tests` 0 · `pytest -q` 1814 · `pre-commit` pass · `gh pr checks` green · `diff --stat origin/main` ≤800

## Work-Unit Commits

One behavior+tests per commit; `type(scope): outcome`. Record test cmd+result, harness/`N/A`, rollback.
