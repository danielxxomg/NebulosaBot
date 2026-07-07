# Delta for Sentinel Commands

## MODIFIED Requirements

### Requirement: Modlogs command

The `/modlogs` command MUST list infractions paginated at 5 per page with optional filters for type and date. Responses MUST be ephemeral. The command MUST be restricted via `@app_commands.default_permissions(moderate_members=True)`.

(Previously: Responses were permanent, no default_permissions)

#### Scenario: List modlogs

- GIVEN a guild has 6 infractions
- WHEN a moderator invokes `/modlogs` page 1
- THEN the first 5 infractions are returned ephemerally

## ADDED Requirements

### Requirement: Moderator permission hint

All moderation action commands (warn, unwarn, mute, unmute, kick, lock, unlock) MUST include `@app_commands.default_permissions(moderate_members=True)` so Discord displays a permission hint to users without the permission.

#### Scenario: Permission hint displayed

- GIVEN a user without Moderate Members permission
- WHEN they view the slash command list
- THEN moderation commands show a permission indicator in the Discord UI

### Requirement: Administrator permission hint on ban

The `/ban` command MUST include `@app_commands.default_permissions(ban_members=True)` so Discord displays a permission hint.

#### Scenario: Ban permission hint

- GIVEN a user without Ban Members permission
- WHEN they view the slash command list
- THEN `/ban` shows a permission indicator in the Discord UI
