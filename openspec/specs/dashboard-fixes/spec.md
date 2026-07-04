# Dashboard Runtime Fixes Specification

## Purpose

Document testable expected behavior for five production-confirmed dashboard fixes: middleware runtime switch, favicon matcher correction, loading skeleton boundary, error boundary, and auth guard regression safety.

## Requirements

### Requirement: Favicon requests bypass middleware

The middleware matcher MUST exempt `favicon.png` and `favicon.ico` from auth redirects so that static asset requests return 200 instead of 307 redirects.

#### Scenario: favicon.png served without redirect

- GIVEN the middleware matcher configuration
- WHEN a request hits `/favicon.png`
- THEN the response is 200 (asset served) and NOT a 307 redirect to `/login`

#### Scenario: favicon.ico still exempt

- GIVEN the middleware matcher configuration
- WHEN a request hits `/favicon.ico`
- THEN the response is 200 (asset served) and NOT a 307 redirect to `/login`

### Requirement: No Edge Runtime process.version warning

The middleware MUST compile under Node.js runtime so that `next build` emits no `process.version` Edge Runtime compatibility warning.

#### Scenario: Clean build output

- GIVEN the dashboard project with `export const runtime = 'nodejs'` in `middleware.ts`
- WHEN `next build` is executed
- THEN the build output contains no warning matching `process.version` or `Node.js API is used`

### Requirement: Loading boundary renders skeleton

The authenticated layout MUST display a Skeleton loading state while server data is in flight, preventing blank screens during page transitions.

#### Scenario: Skeleton shown during page load

- GIVEN an authenticated user navigating to a guild page
- WHEN the server component data fetch is in flight (loading state active)
- THEN `loading.tsx` renders a Skeleton layout matching the sidebar + content structure

#### Scenario: No blank screen on slow fetch

- GIVEN an authenticated user with a slow network connection
- WHEN navigating between guild pages
- THEN the user sees a Skeleton placeholder instead of a blank white screen

### Requirement: Error boundary catches server errors

The authenticated layout MUST catch server component errors and render a recovery UI instead of an unhandled crash or white screen.

#### Scenario: Error card with reset button

- GIVEN the authenticated layout
- WHEN a server component throws an error
- THEN `error.tsx` renders an error Card displaying the error message with a `reset()` button

#### Scenario: Reset retries the failed render

- GIVEN the error boundary is displaying an error Card
- WHEN the user clicks the reset button
- THEN the component retries rendering (calls `reset()`)

### Requirement: Middleware auth guard preserved after runtime switch

The middleware MUST still redirect unauthenticated requests to `/login` after switching from Edge to Node.js runtime, with no behavioral regression.

#### Scenario: Unauthenticated request redirected

- GIVEN an unauthenticated user
- WHEN they request any protected `/dashboard/*` route
- THEN they are redirected to `/login` (307)

#### Scenario: Authenticated request passes through

- GIVEN a user with a valid Supabase session
- WHEN they request any `/dashboard/*` route
- THEN the route renders normally without redirect
