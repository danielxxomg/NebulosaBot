# Guild Config Pages Specification

## Purpose

Provide dashboard pages and Server Actions to read and update core guild configuration.

## Requirements

### Requirement: Read guild configuration

The system MUST read the current guild configuration from Supabase and render it in a form.

#### Scenario: Config page load

- GIVEN a logged-in admin of guild X
- WHEN they open `/dashboard/guilds/X/config`
- THEN the form displays the current prefix, language, mod role, log channel, ticket category, and log toggle

#### Scenario: Missing config defaults

- GIVEN guild X has no configuration record
- WHEN the config page loads
- THEN the page shows default values (`nb!`, `es`, empty/null fields)

### Requirement: Update guild configuration

The system MUST provide a Server Action that validates admin permission, updates the guild record, and notifies the bot webhook.

#### Scenario: Valid update

- GIVEN a logged-in admin of guild X
- WHEN they submit the config form with prefix `!` and language `en`
- THEN the `guild` table is updated and the bot receives a sync notification

#### Scenario: Unauthorized update attempt

- GIVEN a logged-in user who is not admin of guild Y
- WHEN they invoke the update Server Action for guild Y
- THEN the action returns an authorization error and no DB write occurs

### Requirement: Form validation

The system MUST validate submitted values before writing to Supabase.

#### Scenario: Prefix too long

- GIVEN a user submits prefix `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- WHEN validation runs
- THEN the action rejects the value with a field-level error

#### Scenario: Invalid language code

- GIVEN a user submits language `xx`
- WHEN validation runs
- THEN the action rejects the value with a field-level error

#### Scenario: Malformed channel ID

- GIVEN a user submits `logChannelId` that is not a numeric Discord snowflake
- WHEN validation runs
- THEN the action rejects the value with a field-level error

### Requirement: Webhook fallback

The system MUST persist config changes even when the bot webhook is unreachable; cache invalidation falls back to the existing TTL.

#### Scenario: Bot offline during update

- GIVEN the bot webhook returns a network error
- WHEN a valid config update is submitted
- THEN the Supabase row is still updated and the user sees a success warning about delayed propagation

### Requirement: Page revalidation

The system SHOULD revalidate the config page after a successful update so subsequent loads reflect the latest data.

#### Scenario: Refresh after save

- GIVEN a user successfully updates the prefix
- WHEN the page reloads
- THEN the form shows the updated prefix
