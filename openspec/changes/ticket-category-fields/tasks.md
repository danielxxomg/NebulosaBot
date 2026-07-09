# Tasks: Ticket Category Custom Fields

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 850–950 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Foundation) → PR 2 (Service+Views) → PR 3 (Commands+Tests) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR |
|------|------|----|
| 1 | Migration, field_service, models, DB facades | PR 1 |
| 2 | Service passthrough, views, embeds, locales | PR 2 |
| 3 | `/configure_fields` command, integration tests | PR 3 |

## Phase 1: Foundation

- [x] 1.1 RED: Tests for `TicketCategory.field_definitions` in `tests/test_ticket_category.py`
- [x] 1.2 GREEN: Add `field_definitions` to `TicketCategory` in `bot/models/ticket_category.py`
- [x] 1.3 RED: Tests for `Ticket.custom_fields` in `tests/test_ticket_model.py`
- [x] 1.4 GREEN: Add `custom_fields` to `Ticket` in `bot/models/ticket.py`
- [x] 1.5 RED: Tests for `ticket_field_service` in `tests/test_ticket_field_service.py`
- [x] 1.6 GREEN: Create `bot/services/ticket_field_service.py` with `validate_field_definitions()`
- [x] 1.7 Create `migrations/014_ticket_category_fields.sql` + seed Reportes
- [x] 1.8 RED: Tests for DB facades in `tests/test_database.py`
- [x] 1.9 GREEN: Update `ticket_category_db.py` and `ticket_db.py` for JSONB fields
- [x] 1.10 REFACTOR: `uv run pytest` passes

## Phase 2: Service, Views, Embeds

- [x] 2.1 RED: Tests for `create_ticket`/`create_ticket_channel` with `custom_fields`
- [x] 2.2 GREEN: Add `custom_fields` param to `bot/services/ticket_service.py`
- [x] 2.3 RED: Tests for dynamic modal — 0/1/3 fields, required/optional validation
- [x] 2.4 GREEN: `TicketIntakeModal` in `bot/views/tickets.py` builds dynamic TextInputs
- [x] 2.5 RED: Tests for `build_ticket_embed` with custom_fields
- [x] 2.6 GREEN: `build_ticket_embed()` in `bot/utils/embeds.py` renders custom fields inline
- [x] 2.7 Add i18n keys to `bot/locales/en.json` and `bot/locales/es.json`
- [x] 2.8 REFACTOR: `uv run pytest` passes

## Phase 3: Commands + Integration

- [x] 3.1 RED: Tests for `/configure_fields` in `tests/test_tickets_cog.py`
- [x] 3.2 GREEN: Add `configure_fields` hybrid group in `bot/cogs/tickets.py`
- [x] 3.3 RED: Update `tests/integration/test_ticket_flow.py` for custom fields flow
- [x] 3.4 GREEN: Verify integration end-to-end
- [x] 3.5 REFACTOR: Full `uv run pytest` passes, coverage >= 70%

## Phase 4: Verify

- [x] 4.1 No regressions vs baseline (1053+ tests)
- [x] 4.2 Migration idempotent and additive
- [x] 4.3 Existing tickets with null custom_fields render without errors
