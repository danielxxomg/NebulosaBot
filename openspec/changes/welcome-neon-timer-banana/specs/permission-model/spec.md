# Delta for Permission Model

Cycle 2 of 3. Tightens one permission guard and reaffirms the `is_mod` dual-path
contract. The `/delete_category` command's guard is changed from `is_mod()` to
`is_admin()` (category deletion is a destructive admin action, not a mod
action). The `is_mod` decorator path and `is_mod_check` inline path MUST remain
unchanged in decision logic (the existing characterization contract). Cycle 3
(voice/moderation, ScheduledAction, has_perm) is OUT OF SCOPE.

## ADDED Requirements

### Requirement: delete_category requires administrator

The `/delete_category` command MUST be restricted to administrators via the
`@is_admin()` guard (replacing the current `@is_mod()` decorator on the
command at `bot/cogs/tickets.py:262`). Category deletion is a destructive
admin-only action; a moderator without the Administrator permission MUST be
denied. The command MUST keep its existing `@app_commands.default_permissions(administrator=True)`
hint and ephemeral responses. Strict TDD: a RED test exercising the mod-denied
branch MUST be added before the guard is changed, and the existing admin-
allowed and category-not-found/open-tickets behaviors MUST remain unchanged.
The `delete_category` *service* path (`bot/cogs/ticket_admin_flow.py:142`)
MUST continue to enforce guild-scoped access (the `row.get("guildId") != gid`
check); only the *command* guard changes from `is_mod` to `is_admin`.

#### Scenario: Administrator deletes a category

- GIVEN an administrator invokes `/delete_category` on a category with no open tickets
- WHEN the command executes
- THEN the category is removed and a confirmation is shown ephemerally

#### Scenario: Moderator denied

- GIVEN a moderator (mod role, no Administrator permission) invokes `/delete_category`
- WHEN the `@is_admin()` guard evaluates
- THEN access is denied and no category is removed

#### Scenario: RED test precedes the guard change

- GIVEN the guard is still `is_mod()`
- WHEN the new mod-denied test is run before the guard change
- THEN the test FAILS (proving it tests the new behavior); after the guard changes to `is_admin()`, the mod is denied and the test passes

#### Scenario: Service guild-scope check unchanged

- GIVEN the `delete_category` service path after the guard change
- WHEN a cross-guild category id is supplied
- THEN the existing `row.get("guildId") != gid` deny still fires and no foreign-guild category is deleted

## MODIFIED Requirements

### Requirement: `is_mod` dual-path characterization

The system MUST preserve the existing `is_mod` decorator path and `is_mod_check` inline path without changing permission decisions. Characterization coverage MUST account for 24 `@is_mod()` decorator applications (16 in `tickets.py` and 8 in `sentinel.py`) and every inline `is_mod_check` call, including persistent and ephemeral ticket view callbacks. The `unclaim` command intentionally has no `@is_mod()` decorator and is gated by an inline `is_mod_check` (claimer-or-mod) — it is not counted as a decorator. The `/delete_category` command's guard is changed to `@is_admin()` in Cycle 2, reducing the `@is_mod()` decorator count by one (24 → 23); the characterization MUST be updated to reflect this and the `is_admin()` guard MUST be characterized separately. The behavior MUST remain a single decision point in `bot/utils/checks.py`.
(Previously: characterization counted 24 `@is_mod()` decorator applications; Cycle 2 moves `delete_category` to `@is_admin()`, so the `@is_mod()` count drops to 23.)

#### Scenario: Both hybrid paths remain registered

- GIVEN a command is decorated with `@is_mod()`
- WHEN its checks are inspected
- THEN both prefix and slash predicates are registered

#### Scenario: Inline view checks remain fail-closed

- GIVEN a ticket view callback runs without a guild, role, or valid moderator context
- WHEN `is_mod_check` is evaluated
- THEN it denies without weakening the existing permission behavior

#### Scenario: Caller characterization passes after delete_category move

- GIVEN the 23 `@is_mod()` decorator applications (delete_category now `@is_admin()`) and all inline call sites are exercised
- WHEN the Cycle 2 permission test suite runs
- THEN all existing administrator, moderator, regular-user, and DM outcomes remain unchanged and the new `delete_category` mod-denied outcome passes

## Scope boundary

This delta changes only the `/delete_category` guard to `is_admin()` and
updates the `is_mod` characterization count. All other permission checks are
UNCHANGED. Cycle 3 (voice/moderation, ScheduledAction, has_perm) is OUT OF
SCOPE.
