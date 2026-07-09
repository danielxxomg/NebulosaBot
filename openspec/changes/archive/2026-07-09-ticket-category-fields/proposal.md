# Proposal: Ticket Category Custom Fields

## Intent

Ticket intake only collects title+description regardless of category. Admins need per-category structured data (player nick, evidence URL) without separate forms.

## Scope

### In Scope
- `field_definitions` JSONB on `ticket_category` (max 3 fields)
- `custom_fields` JSONB on `ticket`
- Dynamic modal with extra TextInputs from config
- `/configure_fields` admin command
- Custom fields in welcome embed
- Migration + seed (Report → Player Nick + Evidence URL)
- TDD

### Out of Scope
- Dashboard UI
- bot-docs-polish
- Field types beyond short/paragraph

## Capabilities

### New Capabilities
- `ticket-custom-fields`: Per-category configurable intake fields stored as JSONB

### Modified Capabilities
- `ticket-category-model`: Add field_definitions JSONB
- `ticket-model`: Add custom_fields JSONB
- `ticket-intake-modal`: Dynamic TextInput construction
- `ticket-service`: custom_fields passthrough in create_ticket
- `ticket-commands`: /configure_fields command
- `ticket-views`: Pass field_definitions to modal; render in embed

## Approach

1. **Migration**: `field_definitions JSONB DEFAULT '[]'` on ticket_category, `custom_fields JSONB DEFAULT '{}'` on ticket.
2. **Models**: Add fields with None defaults for backward compat.
3. **Modal**: Accept field_definitions, build 0–3 extra TextInputs. Collect into custom_fields dict on submit.
4. **Service**: create_ticket/create_ticket_channel accept custom_fields, pass to insert_ticket.
5. **Embed**: build_ticket_embed renders custom fields as inline fields.
6. **Command**: /configure_fields validates JSON (max 3, require key+label), updates column.

## Affected Areas

| Area | Impact |
|------|--------|
| `migrations/` | New JSONB columns |
| `bot/models/ticket_category.py` | field_definitions field |
| `bot/models/ticket.py` | custom_fields field |
| `bot/views/tickets.py` | Dynamic modal |
| `bot/services/ticket_service.py` | custom_fields passthrough |
| `bot/core/db/ticket_db.py` | insert handles custom_fields |
| `bot/core/db/ticket_category_db.py` | update handles field_definitions |
| `bot/cogs/tickets.py` | /configure_fields command |
| `bot/utils/embeds.py` | Render custom fields |
| `bot/locales/*.json` | i18n keys |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| JSONB schema drift | Med | Python validation on write |
| JSON arg UX clunky | High | v1; dashboard deferred |
| Backward compat | Low | Nullable + None-safe |
| Modal title truncation | Low | Discord auto-truncates |

## Rollback Plan

Drop custom_fields from ticket, field_definitions from ticket_category. Revert modal to static title+description.

## Dependencies

None.

## Success Criteria

- [ ] /configure_fields sets field definitions on a category
- [ ] Modal shows 0–3 extra inputs per category config
- [ ] Custom fields persisted in ticket.custom_fields
- [ ] Welcome embed displays custom field values
- [ ] Existing tickets render without errors
- [ ] All code TDD-covered
