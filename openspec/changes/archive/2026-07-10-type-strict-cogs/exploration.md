## Exploration: Narrow mypy overrides for `bot.cogs.*`

### Current State

The wildcard `[[tool.mypy.overrides]]` for `bot.cogs.*` disables 7 error codes across all 8 cog modules:

```toml
module = "bot.cogs.*"
disable_error_code = ["attr-defined", "no-untyped-def", "arg-type", "type-arg", "untyped-decorator", "no-untyped-call", "unused-ignore"]
```

Running mypy strict with the override removed reveals **119 actual errors** across 8 cog files (`__init__.py` is clean):

| Module | Errors | Dominant codes |
|--------|--------|----------------|
| `sentinel.py` | 35 | `arg-type`, `type-arg`, `untyped-decorator`, `unused-ignore` |
| `tickets.py` | 33 | `untyped-decorator`, `type-arg`, `unused-ignore` |
| `greetings.py` | 27 | `arg-type`, `type-arg`, `unused-ignore` |
| `stellar.py` | 10 | `arg-type`, `type-arg`, `unused-ignore` |
| `utility.py` | 7 | `arg-type`, `type-arg` |
| `ocio.py` | 4 | `arg-type`, `type-arg` |
| `core.py` | 4 | `arg-type`, `untyped-decorator` |
| `setup.py` | 2 | `untyped-decorator`, `type-arg` |

### Error Code Breakdown

| Code | Count | Root cause | Fixable? |
|------|-------|------------|----------|
| `type-arg` | 51 | `Context` used without `[Any]` type argument | Yes — add `[Any]` |
| `arg-type` | 36 | 25 from hybrid_command stubs + 11 real type mismatches | 25 stub (inline), 11 real (fix) |
| `untyped-decorator` | 25 | `hybrid_command()`/`hybrid_group()` + `is_admin()`/`is_mod()` return `Any` | No — discord.py stub limitation |
| `unused-ignore` | 7 | Stale `# type: ignore[override]` comments with wrong error code | Yes — remove or update |

3 of the 7 overridden codes produce **zero errors**: `attr-defined`, `no-untyped-def`, `no-untyped-call`. They can be dropped outright.

### Root Cause Analysis

**RC1: discord.py hybrid_command/hybrid_group stub signatures (25 `untyped-decorator` + 25 `arg-type`)**

The discord.py type stubs define `hybrid_command()` and `hybrid_group()` decorators with `Never` parameters:
```
expected: def (Never, Never, /, *Never, **Never) -> Coroutine[Any, Any, Never]
```

This makes every decorated method produce both `untyped-decorator` (the decorator strips types) and `arg-type` (the signature doesn't match `Never`). This is a known discord.py stub limitation — no amount of annotation on our side fixes it.

`is_admin()` and `is_mod()` in `bot/utils/checks.py` return `Any`, contributing to the `untyped-decorator` count. These could theoretically be fixed with `Callable` return types, but the benefit is marginal since `hybrid_command` itself is the primary blocker.

**RC2: Missing `Context[Any]` type arguments (51 `type-arg`)**

Every `commands.Context` usage omits the required type argument. Fix: change `Context` → `Context[Any]` (or `commands.Context[Any]`). This is a mechanical find-and-replace across all 8 files.

**RC3: `User | Member` vs `Member` in moderation logging (8 `arg-type`)**

`LoggingService.log_moderation_action()` declares `moderator: discord.Member`, but `ctx.author` is `discord.User | discord.Member`. In guild context, `ctx.author` is always a `Member`, but mypy doesn't know that. Fix: assert or narrow `ctx.author` to `Member` before passing.

**RC4: Other real type mismatches (3 `arg-type`)**

- `utility.py:166` — `format_dt(datetime | None)` needs a None guard
- `greetings.py:119,169` — `to_thread(member_count=int | None)` needs `or 0`

**RC5: Stale `# type: ignore[override]` comments (7 `unused-ignore`)**

`greetings.py` and `stellar.py` have `# type: ignore[override]` on methods that changed signature. The ignore targets the wrong error code — the actual error is `type-arg`, not `override`. These need updating or removal.

### Affected Areas

- `pyproject.toml` (lines 131-133) — mypy overrides section
- `bot/cogs/sentinel.py` — 35 errors (8 real `arg-type` + 27 fixable)
- `bot/cogs/tickets.py` — 33 errors (all fixable or stub-related)
- `bot/cogs/greetings.py` — 27 errors (2 real `arg-type` + 25 fixable)
- `bot/cogs/stellar.py` — 10 errors (all fixable)
- `bot/cogs/utility.py` — 7 errors (1 real `arg-type` + 6 fixable)
- `bot/cogs/ocio.py` — 4 errors (all fixable)
- `bot/cogs/core.py` — 4 errors (all stub-related)
- `bot/cogs/setup.py` — 2 errors (1 stub + 1 fixable)

### Comparison to type-strict-services

The archived `2026-07-10-type-strict-services` change removed the `bot.services.*` wildcard by:
1. Fixing 16 errors at the source (cache generics, DB return types, annotations)
2. Inline-suppressing 4 stub limitations with `# type: ignore[code]`
3. Resulting in zero per-module overrides for services

The cogs situation is **different in one key way**: the discord.py `hybrid_command` stub limitation affects ALL cogs uniformly (50 of 119 errors). For services, each error had a distinct root cause. For cogs, one root cause (stub signatures) accounts for 42% of all errors across every module.

### Approaches

1. **Full strict — remove the wildcard entirely**
   - Fix all 119 errors: 51 type-arg (add `[Any]`), 11 real arg-type (fix), 7 unused-ignore (remove), 50 stub errors (inline `# type: ignore`)
   - Pros: Maximum type safety, zero wildcard overrides
   - Cons: 25+ inline `# type: ignore[arg-type]` on hybrid_command lines across all cogs — noise
   - Effort: Medium

2. **Narrow to `untyped-decorator` only, fix everything else**
   - Keep override for `untyped-decorator` (25 errors, pure stub limitation, no inline fix possible)
   - Remove 6 other codes from override
   - Fix 51 type-arg + 11 real arg-type + 7 unused-ignore
   - Inline-suppress 25 stub arg-type errors with rationale
   - Pros: Override is minimal and justified; 87 errors fixed at source; 25 inline suppressions are documented
   - Cons: Still has one wildcard override; 25 inline comments on decorator lines
   - Effort: Medium

3. **Keep `untyped-decorator` + `arg-type`, fix the rest**
   - Keep override for `untyped-decorator` (25) and `arg-type` (36)
   - Fix 51 type-arg + 7 unused-ignore
   - Pros: Smallest diff (58 errors fixed, no inline suppressions needed)
   - Cons: Hides 11 real `arg-type` bugs (User|Member, datetime|None, int|None); new real arg-type issues silently suppressed
   - Effort: Low

### Recommendation

**Approach 2 — Narrow to `untyped-decorator` only, fix everything else.**

Rationale:
- `untyped-decorator` is the ONE error code that genuinely cannot be fixed inline — the decorator itself strips types, and no annotation on the decorated function changes that. Keeping it as a wildcard override is justified and mirrors how `bot.bot` keeps `attr-defined`.
- `arg-type` is a MIX of stub limitations (25) and real bugs (11). Keeping it in the override hides the real bugs. The25 stub-related ones get inline `# type: ignore[arg-type]` with a rationale comment — noisy but correct.
- `type-arg` (51 errors) is entirely mechanical: `Context` → `Context[Any]`. This matches the pattern already used in `bot/core/context.py` (NebulosaContext extends `Context[Any]`).
- `unused-ignore` (7 errors) is stale suppressions that should be cleaned up regardless.
- 3 of 7 codes (`attr-defined`, `no-untyped-def`, `no-untyped-call`) produce zero errors — drop them.

**Concrete plan:**
1. Add `[Any]` to all `Context` usages in 8 cog files (51 fixes)
2. Fix 8 `arg-type` in sentinel.py: assert `isinstance(ctx.author, discord.Member)` or use `ctx.author` with a `Member` type guard before passing to `log_moderation_action`
3. Fix 3 other `arg-type`: None guards on `format_dt` and `to_thread` calls
4. Update or remove 7 stale `# type: ignore[override]` comments
5. Add `# type: ignore[arg-type]  # discord.py hybrid_command stub limitation` to 25 hybrid_command/hybrid_group decorator lines
6. Narrow pyproject.toml override to `disable_error_code = ["untyped-decorator"]`
7. Run mypy strict + full test suite to verify

**Estimated scope:** ~80-100 lines changed across 9 files (8 cogs + pyproject.toml).

### Risks

- **discord.py stub upgrades**: If discord.py ships better stubs, the 25 inline `# type: ignore[arg-type]` comments become stale. Mitigated by `unused-ignore` being enabled — mypy will flag them when stubs improve.
- **`is_admin()` / `is_mod()` return `Any`**: These contribute to `untyped-decorator` errors. They could be fixed with `Callable[..., Any]` return types, but the benefit is marginal since `hybrid_command` is the primary blocker. Deferred to a future cycle.
- **Test regression**: Type annotation changes don't affect runtime behavior, but the full test suite must pass.

### Ready for Proposal

Yes. Scope is well-defined: narrow the `bot.cogs.*` override from 7 error codes to 1 (`untyped-decorator`), fix94 errors at the source, inline-suppress 25 stub limitations. Mirrors the approach used in type-strict-services but adapted for the uniform discord.py stub limitation that affects all cogs.
