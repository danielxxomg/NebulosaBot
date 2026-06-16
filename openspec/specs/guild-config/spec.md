# Guild Configuration Specification

## Purpose

Define guild settings storage, cache-first reads, and default creation on join.

## Requirements

### Requirement: Default values

The system MUST create guild records with default prefix `nb!` and language `es`.

#### Scenario: New guild defaults

- GIVEN the bot joins a guild with no existing record
- WHEN the default configuration is created
- THEN prefix is `nb!`, language is `es`, and active is true

### Requirement: Cache-first reads

The system MUST read guild configuration from cache first and fall back to the database.

#### Scenario: Cache hit

- GIVEN the configuration is cached
- WHEN a command requests the guild prefix
- THEN the value is returned from cache

#### Scenario: Cache miss

- GIVEN the configuration is not cached
- WHEN a command requests the guild prefix
- THEN the value is loaded from the database and stored in cache

### Requirement: CRUD

The system MUST support create, read, update, and delete of guild configuration.

#### Scenario: Update prefix

- GIVEN an existing guild configuration
- WHEN an administrator updates the prefix to `!`
- THEN subsequent reads return `!`

#### Scenario: Soft delete

- GIVEN an active guild configuration
- WHEN the configuration is deleted
- THEN active is set to false

### Requirement: Default on join

The system MUST create a default guild configuration when the bot joins a new guild.

#### Scenario: Guild join

- GIVEN the bot is added to a guild not present in the database
- WHEN the guild join event fires
- THEN a new Guild record is inserted with default values
