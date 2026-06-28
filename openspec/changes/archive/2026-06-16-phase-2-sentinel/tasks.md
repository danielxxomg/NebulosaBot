# Tasks: Phase 2 — Sentinel (Moderation)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~650 (4 new + 2 modified files) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Foundation) → PR 2 (Commands + Wiring) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Foundation: time parser, DB methods, InfractionService + tests | PR 1 | base: feature/phase-2-sentinel; ~330 lines; standalone testable |
| 2 | SentinelCog (9 commands), mod logging, bot wiring | PR 2 | base: PR 1 branch; ~270 lines; depends on PR 1 |

## Phase 1: Foundation — Time Parser

- [x] 1.1 Create `bot/utils/time.py` with `parse_duration(text: str) -> int`. Regex pattern `(\d+)([dhms])`, unit map `{d:86400, h:3600, m:60, s:1}`. Returns 3600 (1h) for invalid/empty input.
- [x] 1.2 Add unit tests for `parse_duration` in `tests/test_time.py`: valid single-unit ("1h"→3600, "30m"→1800, "2d"→172800), compound ("1h30m"→5400), invalid ("30", "1x", "").

## Phase 2: Foundation — Database Methods

- [x] 2.1 Add `insert_infraction`, `get_infractions`, `get_active_warnings`, `deactivate_infraction` to `bot/core/database.py` following existing `_unwrap()` pattern.
- [x] 2.2 Add `get_member`, `update_member_warnings` to `bot/core/database.py`. All methods filter by `guild_id`.

## Phase 3: Foundation — InfractionService

- [x] 3.1 Create `bot/services/infraction_service.py` with `EscalationAction` dataclass and `InfractionService` class. Constructor takes `Database` instance.
- [x] 3.2 Implement `warn()` — insert infraction, increment `Member.warnings` via `update_member_warnings(+1)`, check escalation.
- [x] 3.3 Implement `unwarn()`, `get_modlogs()` — the former deactivates last active WARN and decrements warnings by 1.
- [x] 3.4 Implement `check_escalation()` — `count == 3` returns `EscalationAction("MUTE", 3600, 3)`, `count == 5` returns `EscalationAction("KICK", 0, 5)`, else `None`.

## Phase 4: Foundation — Service Tests

- [x] 4.1 Create `tests/test_infraction_service.py`. Mock `Database` methods. Test `warn` persists and increments warnings.
- [x] 4.2 Test `check_escalation`: count 2→None, 3→MUTE, 4→None, 5→KICK (spec: `count == threshold`).
- [x] 4.3 Test `unwarn`: returns infraction and decrements warnings; returns `None` when no active warns.

## Phase 5: SentinelCog — Moderation Commands

- [x] 5.1 Create `bot/cogs/sentinel.py` with `SentinelCog(commands.Cog)`. Add `_log_action()` helper: build embed with moderator/target/action/reason, send to `logChannelId` if `logEnabled`; skip silently if disabled or no channel.
- [x] 5.2 Add `/warn` and `/unwarn` hybrid commands with `@is_mod()`. Warn calls `InfractionService.warn()` + `check_escalation()` (auto-mute at 3, auto-kick at 5). Unwarn calls `unwarn()`.
- [x] 5.3 Add `/mute` and `/unmute` hybrid commands with `@is_mod()`. Mute uses `member.timeout(duration)` defaulting to 3600s via `parse_duration()`. Unmute uses `member.timeout(None)`.
- [x] 5.4 Add `/kick` (`@is_mod()`) and `/ban` (`@is_admin()`) hybrid commands. Both create infractions. Ban accepts optional `delete_days` (0–7, default 0).
- [x] 5.5 Add `/lock` and `/unlock` hybrid commands with `@is_mod()`. Optional `channel` arg defaults to `ctx.channel`. Toggle `send_messages` on `guild.default_role`.
- [x] 5.6 Add `/modlogs` hybrid command with `@is_mod()`. Paginated embeds (5/page) with optional `type` and `after` filters.

## Phase 6: Wiring

- [x] 6.1 In `bot/bot.py`: add `infraction_service` attribute to `NebulosaBot.__slots__` and `setup_hook()`. Instantiate `InfractionService(db=self.db)`.
- [x] 6.2 In `bot/bot.py`: add `await self.load_extension("bot.cogs.sentinel")` after CoreCog load.
