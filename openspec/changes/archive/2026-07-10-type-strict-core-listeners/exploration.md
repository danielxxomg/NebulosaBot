## Exploration: type-strict-core-listeners

### Current State

Mypy strict mode is enabled project-wide. Three override blocks suppress errors for the in-scope modules:

| Module | Disabled codes | Errors (measured) |
|--------|---------------|-------------------|
| `bot.core.*` | `no-any-return`, `type-arg` | 38 |
| `bot.listeners.*` | `assignment`, `arg-type` | 2 |
| `bot.bot` | `attr-defined` | 2 |
| **Total** | | **42** |

Measurement command (overrides temporarily removed from pyproject.toml):
```
mypy --strict --python-version 3.11 bot/core/ bot/listeners/ bot/bot.py
```

### Error Inventory

#### bot.core.* — 38 errors (type-arg: 36, no-any-return: 2)

**type-arg (36):** Bare `dict` in function signatures missing `[str, Any]`. Purely mechanical.

| File | Count | Example |
|------|-------|---------|
| `bot/core/realtime.py` | 7 | `_record_for_event(data: dict)` → `dict[str, Any]` |
| `bot/core/db/ticket_db.py` | 6 | `-> dict` → `-> dict[str, Any]` |
| `bot/core/db/economy_db.py` | 5 | `-> dict | None` → `-> dict[str, Any] | None` |
| `bot/core/db/ticket_category_db.py` | 4 | same pattern |
| `bot/core/db/ticket_note_db.py` | 3 | same pattern |
| `bot/core/db/infraction_db.py` | 3 | same pattern |
| `bot/core/db/ticket_audit_db.py` | 2 | same pattern |
| `bot/core/db/base.py` | 1 | `_unwrap() -> list[dict]` → `list[dict[str, Any]]` |
| `bot/core/db/guild_db.py` | 1 | same pattern |
| `bot/core/db/member_db.py` | 1 | same pattern |
| `bot/core/db/greeting_db.py` | 1 | same pattern |
| `bot/core/i18n.py` | 1 | `_locales: dict[str, dict]` → `dict[str, dict[str, Any]]` |
| `bot/core/context.py` | 1 | `commands.Context` missing `[NebulosaBot]` type arg |

**no-any-return (2):** `context.py` lines 41, 46 — `self.bot.db` / `self.bot.cache` resolve to `Any` because the unparameterized `Context` base class types `self.bot` as `BotT` (unconstrained).

#### bot.listeners.* — 2 errors

| File | Line | Code | Cause |
|------|------|------|-------|
| `xp_listener.py` | 94 | `assignment` | `guild.get_channel()` returns `GuildChannel` subtypes, assigned to `Messageable` |
| `audit_listener.py` | 55 | `arg-type` | `before.channel` is `Messageable` union, passed to `can_log_in_channel(channel: GuildChannel)` |

#### bot.bot — 2 errors

| File | Line | Code | Cause |
|------|------|------|-------|
| `bot.py` | 325 | `attr-defined` | `ctx._guild_config` not visible on `Context[NebulosaBot]` |
| `bot.py` | 331 | `attr-defined` | same |

### Affected Files (16)

```
bot/core/context.py          — 3 errors (type-arg, no-any-return ×2)
bot/core/i18n.py             — 1 error  (type-arg)
bot/core/realtime.py         — 7 errors (type-arg ×7)
bot/core/db/base.py          — 1 error  (type-arg)
bot/core/db/economy_db.py    — 5 errors (type-arg ×5)
bot/core/db/greeting_db.py   — 1 error  (type-arg)
bot/core/db/guild_db.py      — 1 error  (type-arg)
bot/core/db/infraction_db.py — 3 errors (type-arg ×3)
bot/core/db/member_db.py     — 1 error  (type-arg)
bot/core/db/ticket_audit_db.py    — 2 errors (type-arg ×2)
bot/core/db/ticket_category_db.py — 4 errors (type-arg ×4)
bot/core/db/ticket_db.py          — 6 errors (type-arg ×6)
bot/core/db/ticket_note_db.py     — 3 errors (type-arg ×3)
bot/listeners/audit_listener.py   — 1 error  (arg-type)
bot/listeners/xp_listener.py      — 1 error  (assignment)
bot/bot.py                        — 2 errors (attr-defined ×2)
```

### Approaches

#### Approach 1: Mechanical type-arg + targeted casts (RECOMMENDED)

| Tier | Errors | Fix | Effort |
|------|--------|-----|--------|
| type-arg (36) | `dict` → `dict[str, Any]` | Bulk find-replace, already `from typing import Any` in every file | Low |
| no-any-return (2) | `cast(Database, self.bot.db)` / `cast(TTLCache, self.bot.cache)` | 2 lines, `cast` import | Low |
| attr-defined (2) | `assert isinstance(ctx, NebulosaContext)` after `super().get_context()` | 1 line, narrows type | Low |
| assignment (1) | Narrow `target_channel` type or use `cast` | 1 line | Low |
| arg-type (1) | Add `isinstance(before.channel, discord.abc.GuildChannel)` guard | 1 line | Low |

- Pros: Minimal, mechanical, zero behavioral change, all files already import `Any`
- Cons: `cast` is a type lie (safe at runtime — services guaranteed after setup_hook)
- Effort: **Low** — ~45 changed lines, mostly single-word substitutions

#### Approach 2: Protocol-based bot typing

Define `NebulosaBotProtocol` declaring `db`, `cache`, etc. Parameterize `NebulosaContext(commands.Context[NebulosaBotProtocol])`.

- Pros: Principled, solves no-any-return at the root
- Cons: Circular import with `bot.bot` requires `TYPE_CHECKING` guard; Protocol adds indirection; `NebulosaBot` already exists as the concrete type
- Effort: **Medium** — new Protocol class, import rewiring

#### Approach 3: Minimal — type-arg only

Fix only the 36 bare-dict errors. Leave `no-any-return` and `attr-defined` overrides active.

- Pros: Smallest possible change
- Cons: Only removes 1 of 3 target overrides; defers real cleanup
- Effort: **Low** — ~36 single-word changes

### Recommendation

**Approach1.** Three tiers, all low effort:

1. **Tier 1 (type-arg):** `dict` → `dict[str, Any]` across13 files. Mechanical, ~36 lines. Context's `type: ignore[type-arg]` on class def (can't parameterize `Context[NebulosaBot]` due to circular import with bot.py).

2. **Tier 2 (no-any-return + attr-defined):** `cast()` in context.py properties + `assert isinstance(ctx, NebulosaContext)` in bot.py. ~4 lines.

3. **Tier 3 (listeners):** One type-narrowing guard each. ~2 lines.

### Risks

- **Circular import (context ↔ bot):** context.py cannot import `NebulosaBot` at runtime. The `type: ignore[type-arg]` on the class definition is the justified workaround — this is a known discord.py typing limitation.
- **Cast safety:** `cast(Database, self.bot.db)` is safe because `setup_hook()` initializes all services before any command runs. If a command somehow runs before setup_hook, it would fail regardless (the underlying value would be `None`).
- **Listener guards:** The `isinstance` guard in `audit_listener.py` is semantically correct — DMs are already filtered, and guild channels are always `GuildChannel` subtypes.

### bot.bot In-Scope Recommendation

**YES.** The 2 `attr-defined` errors are trivially fixed with one `assert isinstance(ctx, NebulosaContext)`. Including bot.bot removes one more override from pyproject.toml and keeps the slice clean. Cost: ~1 line.

### Estimated Change Summary

| Metric | Value |
|--------|-------|
| Files changed | 16 |
| Lines changed | ~45 |
| Overrides removed | 3 (`bot.core.*`, `bot.listeners.*`, `bot.bot`) |
| Overrides remaining | 2 (`bot.cogs.*` untyped-decorator, `tests.*`) |
| Behavioral changes | 0 (annotations, casts, assert guards only) |
| Review risk | Low |

### Ready for Proposal

Yes — scope is clear, errors are measured, approaches are concrete. The orchestrator can proceed to `sdd-propose`.
