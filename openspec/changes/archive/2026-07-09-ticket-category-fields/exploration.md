# Exploration: ticket-category-fields

## Current State

The ticket intake modal (`TicketIntakeModal` in `bot/views/tickets.py`) currently shows a **universal** modal with 2 TextInputs after category selection:

1. **Title** — required, short style, max 100 chars
2. **Description** — optional, paragraph style, max 2000 chars

Categories are identified by **UUID** (`ticket_category.id`), not by name, slug, or emoji. The `_CategorySelect.callback` passes `category_id` to the modal; category name is resolved from select options for the modal title only.

The `TicketCategory` model has: `id`, `guild_id`, `name`, `emoji`, `description`, `position`, `active`, `created_at`. No field-configuration metadata exists.

The `Ticket` model has `subject` and `description` (added in migration 013). No structured storage for category-specific custom fields.

### Discord Modal Constraint

Discord modals allow **max 5 TextInput components**. Title + Description already consume 2 → **max 3 category-specific fields** per modal.

## Affected Areas

- `bot/views/tickets.py` — `TicketIntakeModal.__init__` must dynamically build TextInputs based on category field config
- `bot/models/ticket_category.py` — model needs field-configuration storage
- `bot/models/ticket.py` — model needs custom-field value storage
- `bot/core/db/ticket_category_db.py` — insert/update must handle new column
- `bot/core/db/ticket_db.py` — insert_ticket must handle custom fields
- `bot/services/ticket_service.py` — `create_ticket` / `create_ticket_channel` must pass custom fields through
- `bot/utils/embeds.py` — `build_ticket_embed` should display custom field values in the welcome embed
- `bot/cogs/tickets.py` — `create_category` command may need field-config args (or a separate command)
- `bot/locales/en.json`, `bot/locales/es.json` — i18n keys for new fields
- `migrations/` — new migration for field config + custom field storage
- `dashboard/` — ticket detail view may need to display custom fields
- Tests: `test_ticket_category.py`, `test_tickets_cog.py`, `test_ticket_service.py`, `test_ticket_model.py`

## Approaches

### 1. DB Config on ticket_category + JSONB on ticket (Recommended)

Add a `field_definitions` JSONB column to `ticket_category` that stores an ordered array of field definitions. Add a `custom_fields` JSONB column to `ticket` that stores submitted values.

**ticket_category.field_definitions** schema:
```json
[
  { "key": "player_nick", "label": "Player Nickname", "style": "short", "required": true, "max_length": 100, "placeholder": "The player's in-game name" },
  { "key": "evidence_url", "label": "Evidence URL", "style": "short", "required": false, "max_length": 500 }
]
```

**ticket.custom_fields** stored as:
```json
{ "player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/..." }
```

- **Pros**: Fully configurable per guild/category, no code changes for new field types, queryable via JSONB operators, clean separation of concerns
- **Cons**: Requires admin UX for defining fields (command or dashboard), one migration for each table
- **Effort**: Medium

### 2. Separate Tables (field_definitions + field_values)

Create `ticket_field_definition` and `ticket_field_value` tables with proper relational structure.

- **Pros**: Normalized, individually queryable field values, audit-friendly
- **Cons**: More complex (2 new tables, joins for reads), overkill for 1-3 fields per ticket, extra round-trips
- **Effort**: High

### 3. Hardcoded Templates by Category Name

Skip DB config entirely. Define field templates in code keyed by category name or a convention (e.g., "Report" → player_nick field).

- **Pros**: Simplest implementation, no migration, fast
- **Cons**: Not configurable per guild, requires code changes for every new template, categories with same name in different guilds share templates, doesn't scale
- **Effort**: Low

### 4. Embed-Only (No DB Storage)

Collect extra fields in the modal but only render them in the welcome embed — no DB persistence for custom fields.

- **Pros**: No migration, simplest storage story
- **Cons**: Data lost if embed deleted, not queryable, not shown in dashboard, not in transcripts
- **Effort**: Low

## Recommendation

**Approach 1 (DB Config + JSONB)** for ONE focused cycle.

Rationale:
- The JSONB approach fits naturally into the existing Supabase patterns (the codebase already uses camelCase JSON throughout)
- The `field_definitions` column on `ticket_category` is self-contained — no new tables, one migration
- The `custom_fields` column on `ticket` keeps all submitted data in one row — fast reads, no joins
- Max 3 extra fields (Discord limit of 5 total minus Title+Description) means the JSON stays small
- The modal is dynamically constructed from the config — zero code changes when admins add/modify fields
- Dashboard can read `custom_fields` directly from the ticket row for display

**Recommended scope for ONE cycle:**
1. Migration: `field_definitions` JSONB on `ticket_category`, `custom_fields` JSONB on `ticket`
2. Model updates: `TicketCategory.field_definitions`, `Ticket.custom_fields`
3. Dynamic modal: `TicketIntakeModal` reads field_definitions from the selected category and builds 0-3 extra TextInputs
4. Storage: pass `custom_fields` dict through `create_ticket_channel` → `insert_ticket`
5. Display: render custom fields in the welcome embed
6. Admin command: extend `create_category` with a `--fields` JSON arg, or add a new `configure_fields` command
7. Tests: TDD for all of the above

## Risks

- **Admin UX for field definition**: Defining fields via a JSON arg on `/create_category` is functional but not user-friendly. A dashboard UI or a guided wizard command would be better but adds scope. **Mitigation**: ship the JSON arg for v1, iterate with dashboard UI later.
- **Modal title length**: Discord limits modal titles to 45 characters. "Open Ticket — {category_name}" may truncate. **Mitigation**: truncate category name in title if needed (already handled by Discord truncation).
- **JSONB schema drift**: No DB-level validation on `field_definitions` shape. **Mitigation**: validate in Python on insert (enforce max 3 fields, valid styles, required key/label).
- **Backward compatibility**: Existing tickets have no `custom_fields`. **Mitigation**: nullable column, all display code handles `None`/empty dict gracefully.

## PRODUCT QUESTIONS for Orchestrator

1. **How do admins define fields?** Via a JSON arg on `/create_category` (e.g., `--fields '[{"key":"player_nick","label":"Player Nickname","style":"short","required":true}]'`)? Or via a separate `/configure_fields <category_id>` command? Or only via dashboard?

2. **Should the system support field types beyond short/paragraph?** Discord TextInputs only support `short` and `paragraph`. Do we need to document this constraint, or is it obvious?

3. **Should custom fields be visible in the dashboard ticket detail view?** The dashboard currently shows `subject` and `description`. Should it also render `custom_fields` as additional fields?

4. **What happens when an admin changes field_definitions for a category that already has tickets?** Old tickets keep their `custom_fields` snapshot (point-in-time). New tickets use the updated definitions. Is this acceptable?

5. **Is the max 3 extra fields constraint (Discord modal limit) acceptable?** The product intent says "1-3 extra inputs" — this aligns perfectly with the Discord limit. Should we document this as a hard constraint?

6. **Should field_definitions support `default_value` or `options` (for guided input)?** Discord TextInputs don't support dropdowns inside modals, so "options" would only be placeholder text. Worth adding?

## Ready for Proposal

**Yes** — with the caveat that PRODUCT QUESTION #1 (admin UX for field definition) needs a decision before the design phase. The technical approach (JSONB config + dynamic modal) is clear and implementable in one cycle.
