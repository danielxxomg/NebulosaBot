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

---

## PR3: Commands + Integration Slice

**Status**: Complete
**Mode**: Strict TDD
**Date**: 2026-07-09

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 3.1 | `tests/test_tickets_cog.py` | Unit | N/A (new tests) | ✅ 13 tests fail (AttributeError) | — | — | — |
| 3.2 | `tests/test_tickets_cog.py` | Unit | — | — | ✅ 13 tests pass | ✅ 10 happy/error paths | ✅ Clean |
| 3.3 | `tests/integration/test_ticket_flow.py` | Integration | N/A (new tests) | ✅ 2 tests fail (AssertionError) | — | — | — |
| 3.4 | `tests/integration/test_ticket_flow.py` | Integration | — | — | ✅ 5 tests pass | ✅ embed rendering + fallback | ✅ Clean |
| 3.5 | Full suite | — | ✅ 1128 baseline | — | — | — | ✅ 1146 passed, 85.05% |

### Files Changed

| File | Action | Description |
|------|--------|-------------|
| `bot/cogs/tickets.py` | Modified | Added `configure_fields` hybrid group with `set` subcommand; imports `json` and `validate_field_definitions`; admin+mod gated, guild-scoped, ephemeral responses |
| `bot/locales/en.json` | Modified | Added 14 i18n keys under `tickets.configure_fields.*` |
| `bot/locales/es.json` | Modified | Added 14 Spanish i18n keys under `tickets.configure_fields.*` |
| `tests/test_tickets_cog.py` | Modified | Added 13 tests: `TestConfigureFieldsCommand` (10 tests), `TestConfigureFieldsGroup` (1 test), `TestConfigureFieldsPermissions` (2 tests) |
| `tests/integration/test_ticket_flow.py` | Modified | Added 5 integration tests: `TestCustomFieldsFlow` covering modal→service→embed chain, fallback labels, null custom_fields safety |
| `openspec/changes/ticket-category-fields/tasks.md` | Modified | Checked off Phase 3 tasks 3.1–3.5 and Phase 4 tasks 4.1–4.3 |

### Test Results

- **Baseline (PR2)**: 1128 passed, 3 skipped, 84.97% coverage
- **After PR3**: 1146 passed (+18), 3 skipped, 85.05% coverage
- **Regressions**: 0

### Phase 4 Verification

- ✅ 4.1 No regressions: 1146 passed (baseline was 1128, original was 1053+)
- ✅ 4.2 Migration idempotent and additive (verified in PR1)
- ✅ 4.3 Existing tickets with null custom_fields render without errors (covered by `test_existing_ticket_with_null_custom_fields_renders_safely`)

### Deviations from Design

None — implementation matches design.

### Issues Found

None.

### Workload / PR Boundary

- Mode: chained PR (stacked-to-main)
- Current work unit: PR3 (Commands + Integration)
- Boundary: Phase 3 tasks 3.1–3.5 + Phase 4 verification
- Estimated review budget impact: ~200 changed lines
