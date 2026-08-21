# Delta for Sentinel Commands

Cycle 2 of 3. Extends the moderation target hierarchy guard: in addition to
the existing bot-hierarchy check (`bot_member.top_role <= target`), the
author's own role hierarchy MUST be checked — a mod whose `top_role <=
target.top_role` MUST be denied. This is a BEHAVIOR CHANGE to a tested path
(`bot/cogs/sentinel.py:102-117`), so Strict TDD applies: a RED test on the new
deny branch MUST be written first. The existing confirmation dialogs on
`/kick` and `/ban` are UNCHANGED. Cycle 3 (voice/moderation, ScheduledAction,
has_perm) is OUT OF SCOPE.

## ADDED Requirements

### Requirement: Author role hierarchy deny

The moderation target validation (`_validate_target`) MUST deny a mod action
when the author's `top_role <= target.top_role` (the author is not above the
target in the role hierarchy), in addition to the existing bot-hierarchy
check. The owner of the guild is exempt (the owner MAY act on any member). The
deny MUST send an ephemeral error embed (localized via `t()`) naming the
action and target, and MUST return `False` so no moderation mutation occurs.
This is a behavior change: mods who currently rely on bot-hierarchy-only MAY
now be denied when targeting someone at or above their own role. Strict TDD:
a RED test exercising the new author-hierarchy deny MUST be added before the
check is implemented, and the existing bot-hierarchy and owner-exemption
behaviors MUST remain unchanged.

#### Scenario: Mod denied when author role not above target

- GIVEN a mod author whose top role is equal to or below the target's top role
- WHEN the mod invokes a moderation action on that target
- THEN the author-hierarchy deny fires, an ephemeral error embed is sent, and no moderation mutation occurs

#### Scenario: Mod allowed when author role above target

- GIVEN a mod author whose top role is strictly above the target's top role
- WHEN the mod invokes a moderation action on that target
- THEN the author-hierarchy check passes and the action proceeds (subject to the bot-hierarchy check)

#### Scenario: Guild owner is exempt from author hierarchy

- GIVEN the guild owner invokes a moderation action on a member whose role is above the owner's nominal role
- WHEN `_validate_target` runs
- THEN the author-hierarchy check is bypassed (owner MAY act on any member) and the action proceeds subject to the bot-hierarchy check

#### Scenario: Existing bot-hierarchy deny unchanged

- GIVEN the bot's top role is at or below the target's top role and the target is not the owner
- WHEN `_validate_target` runs
- THEN the existing bot-hierarchy deny fires unchanged and no moderation mutation occurs

#### Scenario: RED test precedes the implementation

- GIVEN the author-hierarchy deny is not yet implemented
- WHEN the new test exercising the deny branch is run before implementation
- THEN the test FAILS (proving it tests the new behavior); after implementation it passes and the existing hierarchy tests remain green

## Scope boundary

This delta adds only the author-hierarchy deny. The bot-hierarchy check, the
`/kick`/`/ban` confirmation dialogs, and all other sentinel commands are
UNCHANGED. Cycle 3 (voice/moderation, ScheduledAction, has_perm) is OUT OF
SCOPE.
