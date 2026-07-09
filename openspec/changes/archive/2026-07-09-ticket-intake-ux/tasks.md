# Tasks: Ticket Intake UX

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~320 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | stacked-to-main |

```
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low
```

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Full change: migration + model + service + views + embeds + i18n + tests | PR 1 | Self-contained; ~320 lines; all tests included |

## Phase 1: Migration & Model (Foundation)

- [x] 1.1 **RED**: Write failing tests in `tests/test_ticket_model.py` for `subject`/`description` fields — from_db_row maps populated values, from_db_row maps null values, to_db_dict includes populated values, to_db_dict includes null values, round-trip preservation
- [x] 1.2 **GREEN**: Add `subject: str | None = None` and `description: str | None = None` fields to `Ticket` dataclass in `bot/models/ticket.py`
- [x] 1.3 **GREEN**: Update `Ticket.from_db_row()` to map `row["subject"]` and `row["description"]`
- [x] 1.4 **GREEN**: Update `Ticket.to_db_dict()` to include `"subject"` and `"description"` keys
- [x] 1.5 **GREEN**: Create `migrations/013_ticket_intake_metadata.sql` with idempotent `ALTER TABLE ticket ADD COLUMN IF NOT EXISTS subject text, ADD COLUMN IF NOT EXISTS description text`
- [x] 1.6 **REFACTOR**: Run `uv run pytest tests/test_ticket_model.py` — all new tests pass

## Phase 2: Database & Service (Core Logic)

- [x] 2.1 **RED**: Write failing tests in `tests/test_ticket_service.py` for `create_ticket(subject=..., description=...)` — row includes metadata, row has null metadata when omitted
- [x] 2.2 **GREEN**: Add `subject: str | None = None` and `description: str | None = None` params to `TicketService.create_ticket()` in `bot/services/ticket_service.py`; pass them to `insert_ticket()`
- [x] 2.3 **GREEN**: Add `subject`/`description` params to `TicketService.create_ticket_channel()` and forward to `create_ticket()`/`create_subticket()`
- [x] 2.4 **GREEN**: Add `subject: str | None = None` and `description: str | None = None` params to `TicketDBMixin.insert_ticket()` in `bot/core/db/ticket_db.py`; include in the row dict
- [x] 2.5 **REFACTOR**: Run `uv run pytest tests/test_ticket_service.py tests/test_database.py` — all pass

## Phase 3: Embeds & i18n (Presentation)

- [x] 3.1 **RED**: Write failing tests in `tests/test_tickets_i18n.py` for new i18n keys: `tickets.modal.title`, `tickets.modal.subject_label`, `tickets.modal.subject_placeholder`, `tickets.modal.description_label`, `tickets.modal.description_placeholder`, `tickets.open.title_with_subject`
- [x] 3.2 **GREEN**: Update `build_ticket_embed()` in `bot/utils/embeds.py` — use subject as embed title prefix `"#{number} — {subject}"` when present, fallback to `"Ticket #{number}"` when null; add non-inline details field when description present
- [x] 3.3 **GREEN**: Add modal i18n keys to `bot/locales/en.json` and `bot/locales/es.json`
- [x] 3.4 **REFACTOR**: Run `uv run pytest tests/test_tickets_i18n.py` — all pass

## Phase 4: Views — Modal & Flow (Integration)

- [x] 4.1 **RED**: Write failing tests in `tests/test_tickets_cog.py` for: category select sends modal (not defer), modal submit defers then creates channel with subject/description, empty title shows ephemeral error, welcome embed is pinned after send
- [x] 4.2 **GREEN**: Create `TicketIntakeModal(discord.ui.Modal)` class in `bot/views/tickets.py` — Title input (required, short, max 100), Description input (optional, paragraph, max 2000); store `_guild` and `_category_id`; `on_submit` defers, validates non-empty subject, calls `create_ticket_channel(subject=..., description=...)`, sends+pins welcome embed, sends success followup
- [x] 4.3 **GREEN**: Modify `_CategorySelect.callback()` in `bot/views/tickets.py` — replace `await interaction.response.defer()` with `await interaction.response.send_modal(TicketIntakeModal(guild, category_id, ...))` passing guild context and category_id
- [x] 4.4 **GREEN**: Add `message.pin()` call after `channel.send()` in the creation flow; wrap in try/except for `HTTPException` (log warning, don't rollback)
- [x] 4.5 **REFACTOR**: Extract shared creation logic from `_CategorySelect.callback()` into a helper to avoid duplicating error handling between modal submit and any future callers
- [x] 4.6 **REFACTOR**: Run `uv run pytest tests/test_tickets_cog.py` — all pass

## Phase 5: Final Verification

- [x] 5.1 Run full test suite: `uv run pytest` — all tests green, no regressions
- [x] 5.2 Verify success criteria: modal appears on category select, title required, embed shows subject, embed is pinned, null subject fallback works, i18n keys present in both locales, sub-ticket flow unaffected
