## Exploration: Narrow mypy overrides for bot.services.*

### Current State

The wildcard `[[tool.mypy.overrides]]` for `bot.services.*` disables 5 error codes across all 10 service modules:

```toml
module = "bot.services.*"
disable_error_code = ["attr-defined", "no-any-return", "no-untyped-def", "arg-type", "type-arg"]
```

Services are the business-logic layer — per AGENTS.md, they should be strict-typed. The current override is a blunt instrument inherited from earlier cycles.

Running mypy with the override removed reveals **20 actual errors** across 7 service files (3 modules + `__init__` are already clean):

| Module | Errors | Error codes |
|--------|--------|-------------|
| `guild_service.py` | 1 | `no-any-return` |
| `greeting_service.py` | 6 | `no-any-return`, `arg-type` ×2, `no-untyped-def` ×3 |
| `economy_service.py` | 5 | `no-any-return` ×2, `type-arg` ×3 |
| `logging_service.py` | 2 | `arg-type` ×2 |
| `ticket_service.py` | 3 | `type-arg` ×3 |
| `ticket_invariants.py` | 2 | `type-arg` ×2 |
| `image_service.py` | 2 | `attr-defined` ×2 |
| `transcript_service.py` | 0 | (clean) |
| `ticket_field_service.py` | 0 | (clean) |
| `__init__.py` | 0 | (clean) |

### Root Cause Analysis

The 20 errors fall into 4 root causes:

**1. TTLCache.get() returns `Any | None` (3 errors)**
- `guild_service.py:76`, `greeting_service.py:70`, `economy_service.py:284`
- `cache.get()` returns `Any | None` → functions returning the cached value get `no-any-return`
- Fix: Make `TTLCache` generic (`TTLCache[T]`) or use `cast()` at the call site

**2. DB methods return bare `dict` (8 errors)**
- `economy_service.py:274,295,331`, `ticket_service.py:558,581,582`, `ticket_invariants.py:109,184`
- Database mixins return `dict` (no type args) → `type-arg` errors on return annotations and parameter types
- Fix: Annotate as `dict[str, Any]` throughout DB layer + services

**3. Missing type annotations on helpers (3 errors)**
- `greeting_service.py:202,218,229`
- `_format_template(member)`, `_send_text_only_if_message(channel, member)`, `_resolve_avatar_url(member)` — all have untyped parameters
- Fix: Add `discord.Member` and `discord.abc.Messageable` type hints

**4. Discord.py / Pillow stub limitations (4 errors)**
- `image_service.py:144,288` — `Image.LANCZOS` not in stubs (Pillow)
- `logging_service.py:97,132` — `message.channel` is a union, not `GuildChannel`
- Fix: Inline `# type: ignore[...]` with rationale (stub limitations, not code bugs)

### Affected Areas

- `pyproject.toml` — mypy overrides section (lines 135-137)
- `bot/core/cache.py` — `TTLCache.get()` return type (root cause for 3 errors)
- `bot/core/db/*.py` — bare `dict` return types (root cause for 8 errors)
- `bot/services/greeting_service.py` — 6 errors (4 fixable, 2 stub limitations)
- `bot/services/economy_service.py` — 5 errors (all fixable via cast + dict[str, Any])
- `bot/services/logging_service.py` — 2 errors (stub limitation)
- `bot/services/ticket_service.py` — 3 errors (fixable via DB layer)
- `bot/services/ticket_invariants.py` — 2 errors (fixable via `dict[str, Any]`)
- `bot/services/image_service.py` — 2 errors (Pillow stub limitation)
- `bot/services/guild_service.py` — 1 error (fixable via cache or cast)

Total across services: 20 errors (16 fixable, 4 stub limitations)

### Approaches

1. **Full strict — remove the wildcard entirely**
   - Fix all 20 errors at the source (TTLCache generics, DB return types, annotations)
   - Pros: Maximum type safety, services fully strict
   - Cons: Requires touching `bot/core/cache.py` and all DB mixins (ripple effect beyond services)
   - Effort: High

2. **Narrow to per-module overrides with inline rationale**
   - Remove the wildcard; add per-module overrides only for modules with genuine stub limitations
   - Fix all fixable errors (root causes 1-3); inline `# type: ignore` for stub issues (root cause 4)
   - Pros: Each override has a documented reason; most services become strict
   - Cons: Still has some overrides (but justified and auditable)
   - Effort: Medium

3. **Minimal — narrow wildcard to only the 5 error codes that still fire**
   - Keep the wildcard but add inline `# type: ignore` on each known error line
   - Pros: Smallest diff
   - Cons: Doesn't actually narrow the override; just patches symptoms
   - Effort: Low

### Recommendation

**Approach 2 — Narrow per-module overrides with inline rationale.**

Rationale:
- Services are business logic — they SHOULD be strict. 5 of 10 modules are already clean.
- Root causes 1-3 are fixable without touching core infrastructure (cache/DB) in this cycle:
  - Use `cast()` at cache call sites (3 lines each) instead of making TTLCache generic
  - Change bare `dict` → `dict[str, Any]` in service signatures only (DB layer stays for a future cycle)
  - Add type annotations to 3 greeting helper functions
- Root cause 4 (4 errors) are genuine stub limitations → inline `# type: ignore[code]` with rationale
- The override section becomes: zero per-module overrides for services — all errors resolved at the source

**Concrete plan:**
1. Fix 4 `no-any-return` errors: `cast(GuildConfig, cached)`, `cast(GreetingConfig, cached)`, `cast(int, member.get(...))`, `cast(list[dict[str, Any]], cached)`
2. Fix 8 `type-arg` errors: change bare `dict` → `dict[str, Any]` in service return types and parameter annotations (economy_service, ticket_service, ticket_invariants)
3. Fix 3 `no-untyped-def` errors: add type hints to `_format_template`, `_send_text_only_if_message`, `_resolve_avatar_url`
4. Fix 2 `arg-type` for `member_count`: use `member_count or 0` to narrow `int | None` → `int`
5. Inline suppress 4 stub-limitation errors: `Image.LANCZOS` (attr-defined ×2), `channel` union types in logging_service (arg-type ×2)
6. Remove the `bot.services.*` wildcard override from pyproject.toml
7. Run mypy + full test suite (1375 tests) to verify

### Risks

- **DB layer still returns bare `dict`**: Services will annotate `dict[str, Any]` but the DB mixins remain untyped. This is acceptable — the DB layer is `bot.core.*`, not `bot.services.*`, and has its own override.
- **`cast()` hides real type mismatches**: Using `cast()` at cache sites is a pragmatic compromise. A future cycle could make `TTLCache` generic for proper safety.
- **Test regression**: Changing type annotations shouldn't affect runtime behavior, but the full test suite (1375 tests) must pass.

### Ready for Proposal

Yes. The scope is well-defined: remove the `bot.services.*` mypy wildcard, fix 16 errors at the source, inline-suppress 4 stub-limitation errors. No architectural changes, no runtime behavior changes. Estimated ~30-50 lines changed across ~8 files.
