## Exploration: Harden Command Permissions

### Current State

`is_admin()` in `bot/utils/checks.py` dual-registers BOTH `commands.check` (prefix path) AND `app_commands.check` (slash path). However, `is_mod()` ONLY wraps `app_commands.check(predicate)` — **no prefix gate exists**. This means every `@is_mod()`-decorated hybrid command is wide open on the prefix (`!warn`, `!kick`, etc.) to ANY user.

`@app_commands.default_permissions()` is Discord UI metadata only — it controls what the client shows in the slash picker but does NOT enforce permissions at runtime.

### Affected Areas

#### Commands with OPEN prefix path (via `@is_mod()` only)

**SentinelCog** (`bot/cogs/sentinel.py`):
- `warn`, `unwarn`, `mute`, `unmute`, `kick`, `lock`, `unlock`, `modlogs` — 8 commands

**TicketsCog** (`bot/cogs/tickets.py`):
- `ticket_panel`, `create_category`, `list_categories`, `delete_category`, `configure_fields` (group + set), `subticket` (group + create), `reopen`, `transfer`, `note` (group + add + list + delete) — 14 commands

#### Commands with NO decorator at all

**TicketsCog** (`bot/cogs/tickets.py`):
- `unclaim` — has inline body check via `is_mod_check()` but no decorator gate

#### Commands using body-check pattern (functional but fragile)

**GreetingsCog** (`bot/cogs/greetings.py`):
- All 10 commands (`welcome_test`, `goodbye_test`, `welcome/*`, `goodbye/*`) use `_admin_guard()` inside the body instead of a decorator. Works today but is one refactor away from being open.

#### Correctly gated commands

- `ban` — `@is_admin()` (dual-path) ✅
- `sync` — `@is_admin()` (dual-path) ✅
- `setup` — `@is_admin()` (dual-path) ✅
- Public commands (ping, avatar, daily, etc.) — intentionally ungated ✅

### Root Cause Analysis

```python
# is_admin() — CORRECT: dual-path
def decorator(func):
    return _commands.check(_prefix_predicate)(app_commands.check(_app_predicate)(func))

# is_mod() — BUG: slash-only
return app_commands.check(predicate)  # no commands.check wrapper
```

### Approaches

#### A) Make `is_mod()` dual-path like `is_admin()` — Surgical Fix

Mirror the `is_admin()` pattern: add a `_prefix_predicate` that reads the guild config mod role from cache and wraps it with `commands.check()`.

- **Pros**: 1 file change, fixes ALL 22+ affected commands at once, follows proven `is_admin()` pattern, no new abstractions
- **Cons**: None significant — this is the intended design
- **Effort**: **Low**

#### B) Central permission matrix registry + decorator factory

Create a registry mapping `(command_name → permission_level)` and a factory that generates both gates from the registry.

- **Pros**: Single source of truth for all permissions, easier to audit, extensible
- **Cons**: Over-engineering for current scale (9 cogs), adds abstraction layer, more files to change
- **Effort**: **Medium**

#### C) Also require Discord guild perms as defense-in-depth

On top of A, additionally check `ctx.author.guild_permissions.kick_members` for kick, `ban_members` for ban, etc.

- **Pros**: Defense-in-depth, aligns with Discord's own permission model
- **Cons**: May break servers where mod role has bot-level mod perms but not Discord-level perms, introduces compatibility risk, complicates the permission model
- **Effort**: **Medium**

### Recommendation

**Approach A** (surgical fix to `is_mod()`). Reasons:

1. **Minimum blast radius**: 1 file change (`bot/utils/checks.py`), all 22+ commands fixed automatically
2. **Proven pattern**: `is_admin()` already does this correctly — copy the pattern
3. **No new abstractions**: No registry, no factory, no new concepts
4. **TDD-friendly**: Write 2 failing tests, implement, verify green

The fix adds ~15 lines to `is_mod()`:
```python
async def _prefix_predicate(ctx: commands.Context) -> bool:
    if not ctx.guild:
        raise commands.NoPrivateMessage(...)
    if not isinstance(ctx.author, discord.Member):
        raise commands.CheckFailure(...)
    if ctx.author.guild_permissions.administrator:
        return True
    mod_role_id = _resolve_mod_role_id_from_ctx(ctx)
    if mod_role_id is None:
        raise commands.CheckFailure("No moderator role configured...")
    if not _user_has_role(ctx.author, mod_role_id):
        raise commands.MissingRole(mod_role_id)
    return True

def decorator(func):
    return commands.check(_prefix_predicate)(app_commands.check(_app_predicate)(func))
```

### Secondary Issues (out of scope for this change, noted for future)

| Issue | Severity | Location |
|-------|----------|----------|
| `unclaim` has no decorator | Medium | tickets.py:681 |
| GreetingsCog body-check pattern | Low | greetings.py |
| Ticket one-per-user ValueError race | Low | tickets.py (production logs) |
| Close button NotFound after channel delete | Low | tickets.py (production logs) |

### Test Gaps

| Gap | Impact |
|-----|--------|
| No test verifies prefix path is gated for `@is_mod()` commands | **Critical** — the exact bug we're fixing |
| `test_checks.py` only unwraps `app_commands.check` predicate | Missing prefix predicate coverage |
| `test_setup_cog.py` has the correct pattern (`cmd.checks` assertion) | Should be replicated for sentinel/tickets |
| No integration test: regular user tries `!warn` via prefix | Would catch the regression |

**Test plan for this change** (TDD order):
1. `test_is_mod_dual_path_prefix_predicate_exists` — verify `is_mod()` exposes `prefix_predicate`
2. `test_is_mod_prefix_regular_user_raises` — verify prefix path denies non-mod
3. `test_is_mod_prefix_admin_passes` — verify prefix path allows admin
4. `test_is_mod_prefix_mod_role_passes` — verify prefix path allows configured mod role
5. Sentinel-level: `test_warn_prefix_check_present` — verify `warn` command has `cmd.checks`

### Product Decision: Unconfigured Mod Role

Current behavior: when no mod role is configured, only admins pass. This is the SAFE default — deny-by-default.

**Recommendation**: Keep current behavior (deny non-admins when unconfigured). Do NOT fall back to Discord `moderate_members` perm — it introduces a hidden permission path that admins can't see or control via the bot's config.

### Ready for Proposal

Yes. The scope is clear, the fix is surgical, and the test plan is defined. The orchestrator should tell the user:
- Root cause confirmed: `is_mod()` is slash-only, `is_admin()` is dual-path
- 22+ commands are open on prefix path
- Fix is ~15 lines in `bot/utils/checks.py`
- TDD: 4-5 new tests, then implement
- Estimated effort: 1 session
