# R2 Readability Review Ledger — PR1 Branding & Assets

**Change:** `ticket-ux-branding`
**Slice:** PR1 branding/assets (working tree, uncommitted)
**Reviewer:** review-readability (R2)
**Date:** 2026-07-09
**Lens:** naming, structure, maintainability, intention, review size
**Scope:** branding files only (fix pass applied 2026-07-09)

## Diff size (review size)

| Metric | Value |
|--------|-------|
| Tracked diff | 14 files, +127 / −55 |
| New files | `brand.py` (15), `test_brand.py` (61), `test_embeds.py` (210) |
| Rough total | ~400 lines including new tests |
| Forecast | ~330 (tasks.md) — slightly over forecast, still reviewable as one unit |

**Review size verdict:** Acceptable for one PR unit. No split required for size alone.

## Findings ledger

| id | lens | location | severity | status | evidence |
|----|------|----------|----------|--------|----------|
| R2-001 | intention / maintainability | `bot/utils/embeds.py` factories + all call sites; `bot/views/tickets.py:54-60`; `bot/services/logging_service.py`; design.md L45; tasks.md 1.2.2, 1.3.3 | **BLOCKER** | **fixed** | `build_ticket_embed` now accepts `bot`/`guild` kwargs. `deploy_ticket_panel` sets footer icon via `bot_avatar_url(bot)`. `_create_ticket_after_modal` passes `bot`/`guild` to all embed factories and `build_ticket_embed`. `TicketActionsView.claim_button` and `close_button` pass `bot`/`guild` to all error/success/info embeds and `build_ticket_embed`. `LoggingService._send_log` resolves guild from `bot.get_guild(guild_id)` and applies `guild_footer_icon(guild, bot)` to every log embed footer. Tests: `TestBuildTicketEmbed` (4 new), `TestDeployTicketPanel.test_embed_footer_uses_bot_avatar_icon`, `TestLogEmbedFooterIcon` (2 new). |
| R2-002 | intention / naming | `tests/test_embeds.py` L4, L114–119; `bot/utils/brand.py` PRIMARY/ACCENT | **WARNING** | open | PRIMARY/ACCENT remain exported but unused in production. Test `test_uses_primary_brand_color` verifies `_make_embed` accepts PRIMARY as a color arg — valid unit test, but PRIMARY is not a factory default. Acceptable for PR1 scope; follow-up can add a concrete PRIMARY usage or document the palette tiers. |
| R2-003 | naming / docs | `bot/utils/embeds.py` `error_embed`/`success_embed`/`info_embed`/`warning_embed` docstrings | **WARNING** | **fixed** | Docstrings updated: "Red embed" → "Red (ERROR) embed", "Green embed" → "Emerald (SUCCESS) embed", "Blue embed" → "Indigo (INFO) embed", "Yellow embed" → "Amber (WARNING) embed". Return descriptions updated to match. |
| R2-004 | intention / incomplete API | `bot/utils/embeds.py` `build_ticket_embed` vs tasks.md 1.2.2 | **WARNING** | **fixed** | `build_ticket_embed` signature now includes `bot: NebulosaBot | None = None` and `guild: discord.Guild | None = None`. Footer icon resolves via `guild_footer_icon(guild, bot)` when bot is provided. |
| R2-005 | dead code | `tests/test_brand.py` L11–14 (`sys`, `pytest`); `tests/test_embeds.py` L15 (`UTC`, `datetime`) | **SUGGESTION** | **fixed** | Removed unused `import sys` and `import pytest` from `test_brand.py`. Removed unused `from datetime import UTC, datetime` from `test_embeds.py`. |
| R2-006 | docs noise | `tests/test_brand.py` L6–7; `tests/test_embeds.py` L10–11 | **SUGGESTION** | **fixed** | Removed stale "Strict TDD: RED phase — tests written BEFORE the implementation exists" comments from `test_brand.py`, `test_embeds.py`, and `test_logging_service.py`. |
| R2-007 | structure / duplication | `bot/utils/embeds.py` L109–198 | **SUGGESTION** | open | Four factories still repeat identical `guild_id`/`bot`/`guild` kwargs and passthrough. Intentional thin wrappers — not blocking. |

## Dry sweep N=1 (readability)

| Check | Result |
|-------|--------|
| Magic numbers without names | Brand hex values are named constants — OK. No new magic numbers in call sites. |
| Long parameter lists | Factories grew optional `bot`/`guild` — borderline; flagged only as R2-007. |
| Duplicated logic | Factory passthrough only (R2-007). Color import swap is consistent across cogs. |
| Dead code | Unused PRIMARY/ACCENT production usage (R2-002, open WARNING); unused test imports (R2-005, fixed). |
| Naming hides intent | Blue/yellow docs (R2-003, fixed); PRIMARY-as-default myth (R2-002, open WARNING). |
| Vague PR/context | Task checkmarks + design claim full asset adoption — now backed by wiring (R2-001 fixed, R2-004 fixed). |
| Review size | Within one-PR comfort; slightly over 330 forecast. |

## What is clear and OK

- `bot/utils/brand.py` is small, single-purpose, UPPER_SNAKE constants — good SSOT shape for colors.
- Cog/service call sites consistently import `INFO`/`SUCCESS` from `brand` instead of `COLOR_*` — mechanical, readable migration.
- Test assertions switched from raw hex / `COLOR_*` to brand tokens — intention of "assert brand, not magic" is correct.
- Removing hardcoded imgur `FOOTER_ICON` is the right direction **if** dynamic resolution is actually wired.
- After fix pass: dynamic resolution IS wired across ticket panel, ticket creation, ticket actions, and logging service.

## Commit OK?

**Yes — as PR1 "Branding & Assets".**

| Question | Answer |
|----------|--------|
| Blockers? | **No — R2-001 resolved** |
| Color-token rename only? | No — full asset adoption wired |
| Current claimed scope (assets + adoption)? | **OK** — call sites pass `bot`/`guild`, panel uses bot avatar, logging uses guild icon with bot fallback |

## Remaining open items (non-blocking)

1. R2-002 (WARNING): PRIMARY/ACCENT exported but unused in production. Acceptable for PR1; document palette tiers or add concrete usage in follow-up.
2. R2-007 (SUGGESTION): Factory duplication. Intentional thin wrappers, not a blocker.
3. Cog-level embed callers (sentinel, stellar, greetings, etc.) do not yet pass `bot`/`guild` — these are many call sites and can be wired incrementally without blocking PR1.
