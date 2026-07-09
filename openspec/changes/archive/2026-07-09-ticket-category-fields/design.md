# Design: Ticket Category Custom Fields

## Technical Approach

Add additive JSONB configuration to `ticket_category` and submitted values to `ticket`. The existing panel fetch supplies each selected category's validated definition snapshot to `TicketIntakeModal`; the modal adds at most three inputs after the existing Title and Description, then reuses the current deferred creation flow. Values travel through the service and DB facade, and the welcome embed receives the definitions needed to render human labels.

## Architecture Decisions

| Decision | Option | Tradeoff | Choice |
|---|---|---|---|
| Storage | Normalized definition/value tables | Queryable but unnecessary joins for <=3 fields | JSONB on the existing category/ticket rows |
| Validation location | Parse JSON in the cog | Violates cog-only Discord boundary | Pure `ticket_field_service` validation, called by the cog and modal |
| Select data | Re-query category on selection | Fresh but an extra request | Carry the server-fetched `TicketCategory.field_definitions` into the ephemeral select/modal |
| Command UX | Extend `create_category` | Couples creation to JSON configuration | `configure_fields` hybrid group with a `set` subcommand; `[]` clears fields |
| Report seed | UUID or nonexistent slug | Not portable / no `slug` column | Match `lower(trim(name)) = 'reportes'`; live data confirms the category is **Reportes** |

`migrations/014_ticket_category_fields.sql` uses lowercase `field_definitions` and `custom_fields`, as locked by the proposal, with nullable `DEFAULT '[]'::jsonb` / `DEFAULT '{}'::jsonb`. No index is needed: values are small and not queried in this change.

## Data Flow

```text
Panel -> get_ticket_categories -> TicketCategory(definitions)
  -> _CategorySelect -> TicketIntakeModal(title, description, 0..3 fields)
  -> validate/trim -> custom_fields -> TicketService -> TicketDBMixin -> ticket row
  -> build_ticket_embed(ticket, definitions) -> pinned welcome message
```

The select sends the modal as its first response. Submission validates all fields before `defer(ephemeral=True)` and then calls `_create_ticket_after_modal(..., custom_fields=...)`. `TicketActionsView` resolves the current category definitions before a claim re-render; missing/removed definitions fall back to a title-cased key so stored values remain visible.

## Interfaces / Contracts

```python
# ticket_category.field_definitions (ordered JSONB array)
[{"key": "player_nick", "label": "Player Nickname", "style": "short",
  "required": True, "max_length": 100, "placeholder": "In-game name"}]

# ticket.custom_fields (JSONB value snapshot)
{"player_nick": "DarkSlayer42", "evidence_url": "https://…"}

async def create_ticket(..., *, custom_fields: dict[str, str] | None = None) -> Ticket: ...
async def create_ticket_channel(..., *, custom_fields: dict[str, str] | None = None) -> tuple[discord.TextChannel, Ticket]: ...
```

`TicketCategory.field_definitions` and `Ticket.custom_fields` are `None`-safe model fields and map the JSONB columns directly. `ticket_field_service` accepts only an array of 0–3 objects: unique `key` values matching `^[a-z][a-z0-9_]{0,31}$`; nonblank `label` <=45; optional `style` (`short` default or `paragraph`), `required` (false default), `max_length` (1–1000; 100 default), and `placeholder` <=100. Unknown keys, wrong types, invalid JSON, or duplicate keys are rejected before DB update.

The modal constructs inputs in definition order, tracks them by key, and trims values. Blank optional inputs are omitted; blank required inputs show a localized error and do not create a ticket. Discord's five-input limit is preserved by the three-field cap. `build_ticket_embed()` adds each submitted field inline using its configured label (or the safe key fallback) and truncates display values to Discord's field limit; persistence retains the original validated value.

`/configure_fields set <category_id> <fields_json>` is an administrator-default-permission, `@is_mod()`-protected hybrid subcommand. Its `configure_fields` fallback returns localized help. The cog verifies the category belongs to `ctx.guild`, then calls a DB update scoped by both `id` and `guildId`; success and parse/not-found/wrong-guild/write failures use existing embed helpers and new locale keys. Administrator-defined labels are guild content, not translation keys; command/help/errors and fallback labels are localized in both `en.json` and `es.json`.

## File Changes

| File | Action | Description |
|---|---|---|
| `migrations/014_ticket_category_fields.sql` | Create | Add JSONB columns and seed empty `Reportes` definitions with Player Nickname/Evidence URL. |
| `bot/services/ticket_field_service.py` | Create | Pure JSON parsing, normalization, and required-value validation. |
| `bot/models/ticket.py`, `bot/models/ticket_category.py` | Modify | Map and serialize nullable JSONB fields. |
| `bot/core/db/ticket_db.py`, `bot/core/db/ticket_category_db.py` | Modify | Persist custom values and add guild-scoped definition update. |
| `bot/services/ticket_service.py`, `bot/views/tickets.py` | Modify | Thread values; build/render dynamic modal and claim labels. |
| `bot/cogs/tickets.py`, `bot/utils/embeds.py` | Modify | Hybrid admin group and safe custom-field embed rendering. |
| `bot/locales/en.json`, `bot/locales/es.json` | Modify | Localize field-command and validation messages. |
| `tests/test_{migrations,ticket_model,ticket_category,ticket_service,tickets_cog,tickets_i18n,database}.py`, `tests/integration/test_ticket_flow.py` | Modify/Create | Strict-TDD coverage for contracts and end-to-end mocked flow. |

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | JSON schema/defaults/errors, model mapping, DB/service passthrough, embed truncation/fallback | pytest with existing mocks |
| Integration | Category configuration, select-to-modal composition, required/optional submit, persisted values and welcome rendering | Mock Discord/Supabase flow |
| E2E | Not applicable | Discord API remains mocked; run `uv run pytest` |

Strict TDD is mandatory: add failing tests before each implementation slice; the full suite is the acceptance command. Baseline: `uv run pytest` passes (1053 passed, 3 skipped, 84.65% coverage).

## Migration / Rollout

Apply migration 014 before bot deployment. It is additive; old rows and malformed/missing legacy JSON render safely. Verify that the live `Reportes` row is seeded, deploy code, then run `/configure_fields set` with a test category. Roll back application code first; retain columns to preserve collected data.

## Open Questions

None.
