# Proposal: type-strict-models

## Intent

Clear all 18 `type-arg` mypy errors in `bot/models/*` by annotating bare `dict` as `dict[str, Any]`, so the per-file `type-arg` override for `bot.models.*` in `pyproject.toml` can be removed. No runtime behavior change.

## Scope

### In Scope
- Replace bare `dict` with `dict[str, Any]` across 8 model files
- Fix `custom_fields: dict | None` → `dict[str, Any] | None` in `ticket.py`
- Remove `type-arg` from the `[[tool.mypy.overrides]]` block for `bot.models.*`
- Verify `mypy --strict` passes cleanly for `bot/models/`

### Out of Scope
- Other override modules (`bot.core.*`, `bot.listeners.*`, `bot.bot`, `bot.cogs.*`, `tests.*`)
- Method renaming or schema validation at typed boundaries
- Recursive bar enforcement beyond `bot/models/`

## Capabilities

### New Capabilities
None — this change introduces no new domain behavior. It tightens mypy annotations and removes a config override.

### Modified Capabilities
- `pyproject-toml-qa-config`: Removing the `type-arg` error code from the per-file `[[tool.mypy.overrides]]` block for `bot.models.*`. The existing "Mypy configuration present" requirement MUST be updated to reflect that `bot.models` no longer requires error-code suppression.
- `ticket-model`: The `Ticket.custom_fields` field type annotation SHALL change from `dict | None` to `dict[str, Any] | None`. No runtime behavior or scenarios change.

## Approach

Mechanical per-file annotation pass following the established `type-strict-services` / `type-strict-cogs` pattern:

```python
def from_db_row(cls, row: dict[str, Any]) -> ClassName: ...
def to_db_dict(self) -> dict[str, Any]: ...
```

Import `Any` from `typing` where it isn't already imported.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/models/{guild,infraction,member,ticket_note,economy_config,greeting_config}.py` | Modified | 2 errors each: `from_db_row()`, `to_db_dict()` — bare `dict` → `dict[str, Any]` |
| `bot/models/ticket.py` | Modified | 3 errors: `custom_fields` field, `from_db_row()`, `to_db_dict()` |
| `bot/models/ticket_category.py` | Modified | 3 errors: `field_definitions`, `from_db_row()`, `to_db_dict()` |
| `pyproject.toml` | Modified | Remove `type-arg` from `bot.models.*` override block |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Model tests expect different annotations | Low | Tests call methods on runtime values, not type signatures |
| `dict[str, Any]` loses inner shape info | Low | Equals previous behavior — bare `dict` is `dict[Any, Any]` under strict |

## Rollback Plan

Re-add `type-arg` to the `bot.models.*` override block (one-line) and revert bare `dict` annotations via search/replace. Fallback: keep the override but apply annotations anyway, then escalate override removal in a separate change.

## Dependencies

- Prior archived `type-strict-services` and `type-strict-cogs` established the same pattern.

## Success Criteria

- [ ] `mypy --strict` on `bot/models/` reports 0 errors with the override removed
- [ ] Full strict mypy run confirms total error count drops by 18
- [ ] All existing model tests pass unchanged
- [ ] No bare `dict` type annotations remain in `bot/models/`
