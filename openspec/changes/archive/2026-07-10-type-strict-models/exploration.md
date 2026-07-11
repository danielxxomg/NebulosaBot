## Exploration: Next type-strict slice after services and cogs

### Current State

Previous type-strict work archived:
- `type-strict-services` (2026-07-10) — cleared `bot.services.*` overrides
- `type-strict-cogs` (2026-07-10) — cleared `bot.cogs.*` overrides (only `untyped-decorator` remains)

Remaining mypy overrides in `pyproject.toml`:
```
bot.bot        → attr-defined
bot.cogs.*     → untyped-decorator  (sole remaining — discord.py stub gap)
bot.core.*     → no-any-return, type-arg
bot.listeners.* → assignment, arg-type
bot.models.*   → type-arg
tests.*        → 8 codes disabled
```

### Error Counts (strict mypy, overrides disabled)

| Module | Own-file Errors | Error Codes | Files |
|--------|----------------|-------------|-------|
| `bot.models.*` | **18** | `type-arg` (18) | 8/9 |
| `bot.listeners.*` | **2** | `assignment` (1), `arg-type` (1) | 2/3 |
| `bot.core.*` | **38** | `type-arg` (36), `no-any-return` (2) | ~14/17 |
| `bot.bot` | **2** | `attr-defined` (2) | 1/1 |
| `tests.*` | **~1030** | `arg-type` (527), `type-arg` (202), `no-untyped-def` (151), `attr-defined` (56), ... | 77/73 |

### Affected Areas — `bot.models.*` (recommended slice)

- `bot/models/guild.py` — 2 errors: bare `dict` in `from_db_row()` and `to_db_dict()`
- `bot/models/ticket.py` — 3 errors: bare `dict` in `custom_fields`, `from_db_row()`, `to_db_dict()`
- `bot/models/infraction.py` — 2 errors: bare `dict` in `from_db_row()`, `to_db_dict()`
- `bot/models/member.py` — 2 errors: bare `dict` in `from_db_row()`, `to_db_dict()`
- `bot/models/ticket_category.py` — 3 errors: bare `dict` in `_db_aliases`, `from_db_row()`, `to_db_dict()`
- `bot/models/ticket_note.py` — 2 errors: bare `dict` in `from_db_row()`, `to_db_dict()`
- `bot/models/economy_config.py` — 2 errors: bare `dict` in `from_db_row()`, `to_db_dict()`
- `bot/models/greeting_config.py` — 2 errors: bare `dict` in `from_db_row()`, `to_db_dict()`

### Approaches

1. **type-strict-models (RECOMMENDED)** — Fix all 18 `type-arg` errors in `bot.models.*`, remove override
   - Pros: Smallest slice (18 errors), all same code (`type-arg`), mechanical fix, foundation module
   - Cons: None significant
   - Effort: **Low** — add `[str, Any]` to bare `dict` annotations (~16 lines changed)

2. **type-strict-listeners** — Fix 2 errors in `bot.listeners.*`, remove override
   - Pros: Only 2 errors
   - Cons: Errors are discord.py type-hierarchy issues (`VoiceChannel | StageChannel | ForumChannel | TextChannel | CategoryChannel` vs `Messageable`; channel union vs `GuildChannel`), require type-narrowing or casts
   - Effort: **Low** — but needs careful discord.py type knowledge

3. **type-strict-core** — Fix 38 errors in `bot.core.*`, remove override
   - Pros: High-impact (36 are same `type-arg` pattern as models)
   - Cons: 38 errors across 14+ files, includes 2 `no-any-return` in `context.py` that need investigation
   - Effort: **Medium** — mostly mechanical but larger scope

4. **type-strict-bot** — Fix 2 `attr-defined` errors in `bot/bot.py`, remove override
   - Pros: Only 2 errors, single file
   - Cons: `_guild_config` is set dynamically on `NebulosaContext` — fix requires declaring it as a proper attribute on the context class or using a different pattern
   - Effort: **Low-Medium** — small but requires design decision

5. **type-strict-tests** — Fix ~1030 errors in `tests.*`
   - Pros: Would complete the entire type-strict journey
   - Cons: Massive scope, 8 different error codes, 77 files — not a first slice
   - Effort: **Very High**

### Recommendation

**`type-strict-models`** — the clear winner:

1. **Smallest high-value slice**: 18 errors, all same code (`type-arg`), 8 files
2. **Mechanical fix**: replace bare `dict` with `dict[str, Any]` — no design decisions needed
3. **Foundation module**: models are imported by core, services, cogs, and listeners — fixing them first means transitive clean-up for downstream slices
4. **Predictable PR size**: ~16 lines changed + override removal ≈ well under 400-line budget
5. **Pattern setter**: establishes the `dict[str, Any]` pattern that core (36 errors) and tests (202 errors) will reuse

The fix pattern for every model file is identical:
```python
# Before
def from_db_row(cls, row: dict) -> ClassName:
def to_db_dict(self) -> dict:

# After
def from_db_row(cls, row: dict[str, Any]) -> ClassName:
def to_db_dict(self) -> dict[str, Any]:
```

### Risks

- **Risk: None significant** — this is purely additive type annotation, no behavior change
- **Note**: `custom_fields: dict | None` in `ticket.py` line 31 should become `dict[str, Any] | None` for consistency, even though it's a field annotation not a method signature

### Ready for Proposal

**Yes** — the orchestrator should tell the user:
> Models is the best first slice: 18 errors, all `type-arg`, mechanical `dict → dict[str, Any]` fix across 8 files. Under 400-line budget. Ready for proposal.

### Recommended Change Name

`type-strict-models` — already created at `openspec/changes/type-strict-models/`
