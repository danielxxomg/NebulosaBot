# Apply Progress — ticket-category-fields

## PR2: Service + Views Slice

**Status**: Complete
**Mode**: Strict TDD
**Date**: 2026-07-09

### TDD Cycle Evidence

| Task | RED | GREEN | REFACTOR |
|------|-----|-------|----------|
| 2.1 Service custom_fields passthrough | 4 tests fail (TypeError/KeyError) | 4 tests pass | — |
| 2.2 create_ticket/create_ticket_channel +custom_fields param | (merged with 2.1) | Implementation added | — |
| 2.3 Dynamic modal tests | 11 tests fail (TypeError) | — | — |
| 2.4 TicketIntakeModal dynamic TextInputs | (merged with 2.3) | 11 tests pass | — |
| 2.5 Embed custom_fields rendering | 6 tests fail (TypeError/AssertionError) | — | — |
| 2.6 build_ticket_embed +field_definitions | (merged with 2.5) | 6 tests pass | — |
| 2.7 i18n keys | — | en.json + es.json updated | — |
| 2.8 Full suite | — | — | 1128 passed, 3 skipped, 84.97% coverage |

### Files Changed

| File | Action | Description |
|------|--------|-------------|
| `bot/services/ticket_service.py` | Modified | Added `custom_fields` param to `create_ticket` and `create_ticket_channel`, forwarding to `insert_ticket` |
| `bot/views/tickets.py` | Modified | `TicketIntakeModal` accepts `field_definitions`, builds dynamic TextInputs, validates required fields on submit, passes `custom_fields` and `field_definitions` through `_create_ticket_after_modal` to service and embed; `_CategorySelect`/`_CategorySelectView` pass category objects for field_definitions resolution |
| `bot/utils/embeds.py` | Modified | `build_ticket_embed` accepts `field_definitions`, renders custom fields as inline embed fields with label fallback and 1024-char truncation |
| `bot/locales/en.json` | Modified | Added `tickets.modal.field_required_title` and `tickets.modal.field_required_description` |
| `bot/locales/es.json` | Modified | Added Spanish translations for field validation error keys |
| `tests/test_ticket_service.py` | Modified | Added 4 tests for custom_fields passthrough in create_ticket and create_ticket_channel |
| `tests/test_ticket_views.py` | Created | 18 tests covering dynamic modal construction (0/1/3 fields), required/optional validation, custom_fields collection, and embed rendering |
| `tests/test_tickets_cog.py` | Modified | Fixed 3 existing `_CategorySelect` constructor calls to include `categories=[]` param |
| `openspec/changes/ticket-category-fields/tasks.md` | Modified | Checked off Phase 2 tasks 2.1–2.8 |

### Test Results

- **Baseline**: 1106 passed, 3 skipped, 84.93% coverage
- **After PR2**: 1128 passed (+22), 3 skipped, 84.97% coverage
- **Regressions**: 0

### Deviations from Design

None — implementation matches design.

### Issues Found

None.

### Remaining Tasks (PR3)

- [ ] 3.1 RED: Tests for `/configure_fields` in `tests/test_tickets_cog.py`
- [ ] 3.2 GREEN: Add `configure_fields` hybrid group in `bot/cogs/tickets.py`
- [ ] 3.3 RED: Update `tests/integration/test_ticket_flow.py` for custom fields flow
- [ ] 3.4 GREEN: Verify integration end-to-end
- [ ] 3.5 REFACTOR: Full `uv run pytest` passes, coverage >= 70%
- [ ] Phase 4: Verify

### Workload / PR Boundary

- Mode: chained PR (stacked-to-main)
- Current work unit: PR2 (Service + Views)
- Boundary: Phase 2 tasks 2.1–2.8 only
- Estimated review budget impact: ~280 changed lines
