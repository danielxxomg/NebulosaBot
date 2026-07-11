# Design: Type-Strict Models

## Technical Approach

Remove the `bot.models.*` mypy `type-arg` exemption after a mechanical annotation pass across all eight affected dataclass modules. Every unparameterized database-row or serialization `dict` becomes `dict[str, Any]`; JSONB fields use the same value type. This preserves the existing Supabase camelCase mapping and satisfies the proposal without runtime changes.

## Architecture Decisions

| Decision | Options / trade-off | Choice and rationale |
|---|---|---|
| Row and output boundary type | Define per-model `TypedDict`s (more precise, larger schema-coupled change); use `dict[str, Any]` (preserves flexible Supabase boundary). | Use `dict[str, Any]`. Rows and serialized payloads already accept heterogeneous DB/JSON values, and this change only removes bare generic annotations. |
| JSONB model fields | Leave `dict`/`list[dict]` suppressed; type exact JSON shapes now. | Use `dict[str, Any] | None` for `Ticket.custom_fields` and `list[dict[str, Any]]` for `TicketCategory.field_definitions`. Their values are intentionally schema-flexible. |
| Mypy enforcement | Retain the models wildcard exemption; remove it after fixes. | Delete the complete `bot.models.*` override. A module-specific exemption would hide future model annotation regressions. |
| Regression proof | Rely on mypy command only; add config test. | Add a focused configuration test rejecting a `bot.models.*` override, consistent with the existing services guard. |

## Data Flow

No runtime data flow changes. Static contracts describe the current path:

    Supabase row (dict[str, Any])
             │
             v
    Model.from_db_row() ──→ dataclass ──→ to_db_dict() ──→ Supabase payload (dict[str, Any])

CamelCase database keys, default handling, timestamp serialization, and JSONB payload values remain unchanged.

## File Changes

| File | Action | Description |
|---|---|---|
| `bot/models/guild.py` | Modify | Import `Any`; type row and serialized payload contracts. |
| `bot/models/{infraction,member,ticket_note,economy_config,greeting_config}.py` | Modify | Import `Any`; parameterize `from_db_row()` and `to_db_dict()`. |
| `bot/models/ticket.py` | Modify | Import `Any`; parameterize row/output contracts and `custom_fields`. |
| `bot/models/ticket_category.py` | Modify | Import `Any`; parameterize row/output contracts and `field_definitions`. |
| `pyproject.toml` | Modify | Delete the `bot.models.*` `type-arg` override block. |
| `tests/test_mypy_config.py` | Modify | Add a regression assertion that no override targets `bot.models.*`. |

## Interfaces / Contracts

```python
from typing import Any

@classmethod
def from_db_row(cls, row: dict[str, Any]) -> Model: ...

def to_db_dict(self) -> dict[str, Any]: ...

custom_fields: dict[str, Any] | None = None
field_definitions: list[dict[str, Any]] = field(default_factory=list)
```

`Any` is deliberately limited to values crossing the untyped Supabase/JSONB boundary; keys remain strings. No public method names, mappings, or runtime validation behavior changes.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Override removal guard | Write the `bot.models.*`-absence test in `tests/test_mypy_config.py` first; it fails until the override is removed. |
| Static | All 18 prior `type-arg` locations | Run `uv run mypy bot/models/` and `uv run mypy`; require zero model errors after the override is deleted. Also search model annotations for bare `dict`. |
| Integration | Existing model serialization behavior | Run `uv run pytest`; existing model tests cover row mapping, defaults, JSONB fields, and round trips. |
| E2E | Not applicable | This is annotation/configuration-only work with no Discord or database interaction change. |

## Migration / Rollout

No migration required. Ship as one small type-safety PR (approximately 25--35 changed lines, below the 1,500-line review budget). Roll back by reverting the annotation/configuration/test change; no data or runtime state is affected.

## Open Questions

None.
