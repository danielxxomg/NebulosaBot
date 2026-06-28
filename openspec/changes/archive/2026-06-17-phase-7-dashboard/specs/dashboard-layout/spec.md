# Dashboard Layout Specification

## Purpose

Provide the authenticated Next.js App Router shell: navigation, guild selection, and per-guild permission guards.

## Requirements

### Requirement: Authenticated route group

The system MUST wrap all dashboard pages (except `/login` and the auth callback) in an authentication guard.

#### Scenario: Authenticated navigation

- GIVEN a logged-in user
- WHEN they navigate to any dashboard route
- THEN the route renders inside the authenticated layout

#### Scenario: Public routes remain accessible

- GIVEN an unauthenticated user
- WHEN they visit `/login`
- THEN the login page renders without auth guard

### Requirement: Sidebar navigation

The system MUST render a sidebar with navigation links to the active guild's sections: overview, config, and any enabled modules.

#### Scenario: Guild-scoped links

- GIVEN a user has selected guild X
- WHEN the sidebar renders
- THEN links target `/dashboard/guilds/X/config` and `/dashboard/guilds/X/overview`

#### Scenario: Collapsed mobile sidebar

- GIVEN a user on a viewport narrower than 768 px
- WHEN the page loads
- THEN the sidebar is hidden by default and toggled via a menu button

### Requirement: Guild selector

The system MUST display only authorized guilds (admin + bot present) and persist the selected guild across navigation.

#### Scenario: Selector populated

- GIVEN a logged-in user authorized for guilds A and B
- WHEN the guild selector renders
- THEN it lists A and B only

#### Scenario: Selection persists

- GIVEN a user selects guild A
- WHEN they navigate to a different dashboard page
- THEN guild A remains selected

#### Scenario: No authorized guilds

- GIVEN a logged-in user with no authorized guilds
- WHEN the dashboard loads
- THEN an empty state prompts the user to invite the bot

### Requirement: Per-guild permission guard

The system MUST verify the current user is an administrator of the selected guild before rendering guild-scoped pages.

#### Scenario: Direct URL to authorized guild

- GIVEN a logged-in user is admin of guild X
- WHEN they request `/dashboard/guilds/X/config`
- THEN the config page renders

#### Scenario: Direct URL to unauthorized guild

- GIVEN a logged-in user is not admin of guild Y
- WHEN they request `/dashboard/guilds/Y/config`
- THEN they are redirected to `/dashboard` with an error message

### Requirement: Shell loading state

The system SHOULD show a skeleton placeholder while the session and authorized guild list load.

#### Scenario: Initial load

- GIVEN a user opens the dashboard
- WHEN session and guild data are pending
- THEN a skeleton layout is shown
