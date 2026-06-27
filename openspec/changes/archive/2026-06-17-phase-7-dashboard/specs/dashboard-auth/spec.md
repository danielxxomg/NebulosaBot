# Dashboard Authentication Specification

## Purpose

Authenticate dashboard users through Discord OAuth2, maintain sessions, and enforce guild-administrator authorization.

## Requirements

### Requirement: Discord OAuth2 login

The system MUST authenticate users via Supabase Auth with the Discord OAuth2 provider.

#### Scenario: User initiates login

- GIVEN an unauthenticated user on `/login`
- WHEN they click the Discord login button
- THEN they are redirected to Discord OAuth2 and returned to the dashboard on success

#### Scenario: User denies OAuth2 consent

- GIVEN an unauthenticated user on `/login`
- WHEN they deny Discord authorization
- THEN they remain on `/login` with an error message

### Requirement: Session middleware

The system MUST validate the Supabase session on every `/dashboard/*` route and redirect unauthenticated users to `/login`.

#### Scenario: Authenticated user accesses dashboard

- GIVEN a user with a valid Supabase session
- WHEN they request any `/dashboard/*` route
- THEN the route renders

#### Scenario: Expired session

- GIVEN a user whose session has expired
- WHEN they request `/dashboard`
- THEN they are redirected to `/login`

#### Scenario: Deep link without session

- GIVEN an unauthenticated user
- WHEN they request `/dashboard/guilds/123/config`
- THEN they are redirected to `/login` and, after login, returned to the original URL

### Requirement: Guild administrator authorization

The system MUST allow a user to manage only guilds where the user has the Discord `ADMINISTRATOR` permission and the bot is present in the `guild` table.

#### Scenario: Authorized guild

- GIVEN a logged-in user with `ADMINISTRATOR` permission in guild X
- AND guild X exists in the `guild` table with `active = true`
- WHEN the guild selector loads
- THEN guild X appears as selectable

#### Scenario: Non-admin guild hidden

- GIVEN a logged-in user without `ADMINISTRATOR` permission in guild Y
- WHEN the guild selector loads
- THEN guild Y is not shown

#### Scenario: Bot-not-present guild hidden

- GIVEN a logged-in user with `ADMINISTRATOR` permission in guild Z
- AND guild Z is absent from the `guild` table
- WHEN the guild selector loads
- THEN guild Z is not shown

### Requirement: Logout

The system SHOULD provide a logout action that clears the Supabase session and redirects to `/login`.

#### Scenario: User logs out

- GIVEN a logged-in user
- WHEN they trigger logout
- THEN the session is cleared and they land on `/login`
