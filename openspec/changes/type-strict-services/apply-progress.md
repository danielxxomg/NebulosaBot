# Apply Progress: Type-Strict Services

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/test_mypy_config.py` | Unit | ✅ 4/4 | ✅ Written (1 FAIL) | ✅ Passed (5/5) | ➖ Single (config assertion) | ➖ None needed |
| 2.1–2.8 | `tests/test_mypy_config.py` | Unit | ✅ 5/5 | N/A (GREEN phase) | ✅ 1376 passed, 0 warnings | ➖ N/A | ✅ Clean |

### Test Summary
- **Total tests written**: 1 (regression test for override removal)
- **Total tests passing**: 1376 (full suite) + 5 (mypy config tests)
- **Layers used**: Unit (1), Static analysis via mypy
- **Approval tests** (refactoring): None — no refactoring tasks
- **Pure functions created**: 0 (annotation/type-only changes)

## Implementation Details

### Task 1.1 — RED: Regression Test
- Added `TestMypyNoServicesWildcard` class to `tests/test_mypy_config.py`
- Test asserts no override has `module == "bot.services.*"`
- Verified RED: test FAILED against current pyproject.toml (override present)

### Task 2.1 — guild_service.py
- Imported `cast` from `typing`
- Cast `self._cache.get(cache_key)` to `GuildConfig` before accessing `.language`
- Removed redundant `config: GuildConfig` type annotation to fix `no-redef`

### Task 2.2 — greeting_service.py
- Imported `cast` from `typing`
- Cast `self._cache.get(cache_key)` to `GreetingConfig` on cache hit
- Added `discord.Member` annotation to `_format_template` parameter
- Added `discord.abc.Messageable` annotation to `_send_text_only_if_message` channel parameter
- Added `discord.Member` annotation to `_resolve_avatar_url` parameter
- Coalesced `member.guild.member_count` with `or 0` in both welcome and goodbye paths
- Added `# type: ignore[arg-type]` at both `_send_text_only_if_message` call sites (guild.get_channel returns broader union)

### Task 2.3 — economy_service.py
- Imported `Any`, `cast` from `typing`
- Typed `get_leaderboard` return as `list[dict[str, Any]]`
- Typed `get_rank_info` return as `dict[str, Any] | None`
- Typed `get_economy_config` return as `dict[str, Any] | None`
- Cast cached leaderboard to `list[dict[str, Any]]`
- Cast `member.get("coins", 0)` to `int` in `get_balance`

### Task 2.4 — ticket_service.py
- Imported `Any` from `typing`
- Changed `_resolve_ticket_category` `guild_row` param from `dict | None` to `dict[str, Any] | None`
- Changed `_build_reopen_channel` params `closed_row` and `guild_row` from bare `dict` to `dict[str, Any]`

### Task 2.5 — ticket_invariants.py
- Imported `Any` from `typing`
- Changed `check_can_unclaim` `ticket` param from `dict` to `dict[str, Any]`
- Changed `check_subticket_parent` `parent` param from `dict | None` to `dict[str, Any] | None`

### Task 2.6 — logging_service.py
- Added `# type: ignore[arg-type]` with rationale at both `can_log_in_channel(message.channel)` call sites
- Rationale: discord.py `Message.channel` is a broader union than `GuildChannel`; runtime guard in `can_log_in_channel` handles non-text

### Task 2.7 — image_service.py
- Added `# type: ignore[attr-defined]` with rationale at both `Image.LANCZOS` uses
- Rationale: Pillow exposes `LANCZOS` at runtime but stubs omit it

### Task 2.8 — pyproject.toml
- Deleted the `[[tool.mypy.overrides]]` block targeting `bot.services.*`

## Verification Results

- `uv run mypy bot` — **Success: no issues found in 65 source files**
- `uv run pytest tests/test_mypy_config.py` — **5 passed**
- `uv run pytest` — **1376 passed, 3 skipped, 0 warnings**

## Warning Fixes (post-verify)

### W1 — Ruff E501 line-length
- `bot/services/economy_service.py:274` — broke `get_leaderboard` signature across lines (130 → ≤120 chars)
- `bot/services/ticket_service.py:558` — broke `_resolve_ticket_category` signature across lines (123 → ≤120 chars)
- `uv run ruff check` on both files: **All checks passed**

### W2 — Document extra greeting_service.py type:ignore suppressions
`greeting_service.py:120,170` each carry `# type: ignore[arg-type]` with inline rationale:
> "guild.get_channel returns broader union; text channel guaranteed by guild config"

These two suppressions are beyond the four originally planned in design.md
(logging_service ×2 `arg-type`, image_service ×2 `attr-defined`). They are
narrow and necessary: `guild.get_channel()` returns `abc.GuildChannel | None`
but the greeting config guarantees a text channel at runtime. The design's
four-ignore plan covered stub limitations only; these two cover the discord.py
API's broader return type, which is a distinct suppression category. No code
change required — the rationale is already in the inline comments; this note
completes the artifact trail.
