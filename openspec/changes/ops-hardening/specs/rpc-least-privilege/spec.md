# RPC Least Privilege Specification

## Purpose

Restrict PostgREST-exposed RPC function access so that only `service_role` can invoke member mutation functions. `anon` and `authenticated` roles MUST NOT have EXECUTE grants on these functions.

## Requirements

### Requirement: RPC EXECUTE revoked from anon and authenticated

The system MUST revoke EXECUTE privilege on `increment_member_xp`, `increment_member_coins`, `increment_member_warnings`, and `set_member_daily` from the `anon` and `authenticated` roles. After the migration, only `service_role` retains EXECUTE access.

#### Scenario: service_role can call RPCs

- GIVEN the revoke migration has been applied
- WHEN a request authenticated as `service_role` calls `increment_member_xp(guild_id, user_id, 10)`
- THEN the function executes successfully and returns the updated value

#### Scenario: anon cannot call RPCs

- GIVEN the revoke migration has been applied
- WHEN a request authenticated as `anon` calls `increment_member_coins(guild_id, user_id, 50)` via PostgREST `/rest/v1/rpc/increment_member_coins`
- THEN PostgREST returns a permission denied error (HTTP 401 or 403)

#### Scenario: authenticated cannot call RPCs

- GIVEN the revoke migration has been applied
- WHEN a request authenticated as `authenticated` calls `increment_member_warnings(guild_id, user_id, 1)` via PostgREST
- THEN PostgREST returns a permission denied error

#### Scenario: Security advisor warnings resolved

- GIVEN the revoke migration has been applied
- WHEN the Supabase security advisor scans RPC grant scope
- THEN 0 warnings remain for these 4 functions (down from 8)

### Requirement: Zero bot code impact

The bot MUST continue to function without code changes after the RPC grant revocation. The bot uses `service_role` for all database operations, including RPC calls.

#### Scenario: Bot RPC calls unaffected

- GIVEN the bot is configured with `service_role` credentials
- WHEN the bot calls any of the 4 member RPC functions
- THEN the calls succeed identically to before the revocation

#### Scenario: No bot code diff

- GIVEN the revoke migration has been applied
- WHEN `git diff bot/` is inspected
- THEN the diff is empty — zero bot code changes
