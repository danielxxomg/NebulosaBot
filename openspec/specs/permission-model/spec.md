# Permission Model Specification

## Purpose

Define permission checks for moderators and administrators.

## Requirements

### Requirement: Administrator check

The system MUST provide an `is_admin` check that returns true for guild administrators.

#### Scenario: Admin user

- GIVEN a user with the Administrator permission
- WHEN `is_admin` is evaluated
- THEN it returns true

#### Scenario: Non-admin user

- GIVEN a user without the Administrator permission
- WHEN `is_admin` is evaluated
- THEN it returns false

### Requirement: Moderator check

The system MUST provide an `is_mod` check that returns true for users with the configured moderator role or the Administrator permission.

#### Scenario: Mod role

- GIVEN a guild has configured a moderator role
- WHEN a user with that role invokes a guarded command
- THEN `is_mod` returns true

#### Scenario: Admin fallback

- GIVEN a guild has no moderator role configured
- WHEN an administrator invokes a guarded command
- THEN `is_mod` returns true

#### Scenario: Regular user

- GIVEN a user without the moderator role or Administrator permission
- WHEN `is_mod` is evaluated
- THEN it returns false

### Requirement: Unconfigured moderator role

The system SHOULD fall back to administrator-only access when no moderator role is configured.

#### Scenario: Missing mod role

- GIVEN no moderator role is set
- WHEN a non-administrator user invokes a moderator-guarded command
- THEN access is denied

### Requirement: Ban command requires administrator

The `/ban` command MUST be restricted to administrators via the `@is_admin()` guard.

#### Scenario: Admin invokes ban

- GIVEN a user has the Administrator permission
- WHEN they invoke `/ban`
- THEN the command executes

#### Scenario: Moderator invokes ban

- GIVEN a user has the moderator role but not the Administrator permission
- WHEN they invoke `/ban`
- THEN access is denied
