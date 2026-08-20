# Exploration: welcome-svg-foundation (Cycle 1)

> SDD exploration phase. Cycle 1 of 3. Scope: Foundation SVG Minimal
> (Nebulosa theme) + Hygiene + DRY cleanup. Cycle 2 (Neon) and Cycle 3
> (timer, 12h, banana C, RLS, voice/moderation) are OUT OF SCOPE.

## Current State

NebulosaBot renders welcome/goodbye cards procedurally with **Pillow** inside a
single 454-line `ImageService` that ALSO owns rank-card generation — an SRP
violation. The greeting flow is otherwise well-structured:

- `GreetingsCog` (`bot/cogs/greetings.py:37`) — listeners `on_member_join` /
  `on_member_remove` delegate to `GreetingService`. Admin test commands
  `/welcome_test` and `/goodbye_test` call `image_service.generate_greeting_card`
  directly via `asyncio.to_thread` (lines 117–137, 169–189).
- `GreetingService` (`bot/services/greeting_service.py:32`) — cache-first
  `get_config` (HIT→return / MISS→DB→populate, lines 58–83), `save_config`
  (upsert + invalidate, lines 85–93), and a unified `dispatch_greeting` that
  branches on `kind` then wraps rendering in `asyncio.to_thread` (line 155).
- `ImageService` (`bot/services/image_service.py:74`) — synchronous Pillow
  renderer. `generate_rank_card` (lines 96–219) and `generate_greeting_card`
  (lines 250–375) share the SAME gradient-loop + font-loader but live in one
  class. Greeting card uses a fixed Discord-blurple accent `#7289da`
  (GREETING_ACCENT, line 242) — NOT the Nebulosa brand tokens from
  `bot/utils/brand.py`.
- Dispatch wiring: `bot/bot.py:215` constructs `ImageService()`, passes it to
  `GreetingService` (line 222). Helpers `_fetch_avatar`, `_safe_fetch_avatar`,
  `_paste_circular_asset`, `_load_font` are all in `ImageService`.

Tests exist and are substantial: `tests/test_image_service.py` (494L),
`tests/test_greeting_service.py` (1126L), `tests/test_greetings_cog.py` (616L).
BUT `_generate_greeting_card_compatibly` (greeting_service.py:202) — the
backwards-compat shim that strips localized kwargs — has **no covering test**
(codegraph blast-radius: ⚠️ no tests found).

## Affected Areas

- `bot/services/image_service.py` (454L) — SRP broken: rank + greeting in one
  class. Greeting card color uses `#7289da` blurple, bypasses brand tokens.
  Will be split / extended with SVG path in Cycle 1.
- `bot/services/greeting_service.py` (306L) — cache-first intact;
  `_generate_greeting_card_compatibly` (line 202) is an untested shim that
  must be removed once `generate_greeting_card` accepts the localized kwargs
  natively (it already does — the shim only guards against a frozen old
  signature that no longer exists).
- `bot/cogs/greetings.py` (554L) — `/welcome_test` + `/goodbye_test` duplicate
  the dispatch kwargs assembly (lines 117–137 vs 169–189). DRY opportunity.
- `bot/utils/brand.py` — single source of brand tokens; greeting card does
  NOT import from here yet (uses hardcoded `#7289da`).
- `bot/utils/time.py` (56L) + `bot/utils/timeparse.py` (29L) — DIFFERENT
  domains (duration parsing vs DB timestamp parsing). **Do NOT merge.**
- `dashboard/lib/actions/{economy,guild,greeting,ticket}-actions.ts` — each
  defines its own `verifyGuildAdmin` (~40 lines, identical except the final
  error string). x4 duplication, x0 tests (codegraph: ⚠️ no tests found).
- `bot/cogs/ticket_admin_flow.py:27` + `bot/cogs/ticket_notes_flow.py:21` —
  define `INFO = discord.Color.from_str("#5865F2")` locally, bypassing
  `bot.utils.brand.INFO`. Brand-tokens spec scenario "zero hex matches" is
  violated by these two.
- `pyproject.toml` — `version = "0.1.0"` (line 2) drifts from actual
  `v0.8.0-qa-modernization` git state.
- `.gitignore` — missing `.ty_cache/`, `.hypothesis/`, `*.tsbuildinfo`,
  `**/.next/` (`.pytest_cache/` already present).
- `openspec/config.yaml` — `type_checker: mypy` (should be `ty`),
  `coverage_threshold: 0.70` (should be `0.75`), `review_budget_lines: 400`
  (should be `800`), test count `1812` stale vs actual.
- `.env.example` — only 3 vars (DISCORD_TOKEN, SUPABASE_URL, SUPABASE_KEY);
  missing documented bot/Discord/feature vars.
- `supabase/migrations/003_economy_config.sql` +
  `003_subtitles_notes.sql` — duplicate `003` prefix.
- `greeting_config` table / `GreetingConfig` model — NO `updatedAt` column.
- `.github/workflows/code-quality.yml` — uses `npx jscpd` / `pip install
  vulture` WITHOUT SHA pins (unlike the pinned `actions/checkout@11bd71901`).
- `README` — does not exist.

## Approaches

### 1. cairosvg renderer (as calibrated) — SVG template → PNG

- **Pros**: Decouples layout (SVG/XML) from rendering; resvg-ready 1-line
  switch on VPS; SVG is a text artifact (diffable, auditable, i18n-friendly);
  single source of truth for layout.
- **Cons**: ⚠️ **cairosvg is NOT pure Python.** It depends on `cairocffi` →
  `libcairo` C library (Context7 `/kozea/cairosvg` NEWS.rst: "relies on
  cairocffi"). `python:3.11-slim` does NOT ship `libcairo`, and the Pterodactyl
  env has no apt. This means either (a) a pre-built `libcairo` wheel must be
  bundled/loaded, or (b) the calibrated "fallback Pillow" path becomes the
  DEFAULT, not the fallback. Risk of silent ImportError at boot.
- **Effort**: Medium — add dep, template, renderer, fallback. Highest risk.

### 2. Pillow procedural renderer (current, extended) — keep + rebrand

- **Pros**: Already works on `python:3.11-slim` with zero system deps;
  `pillow>=11.0` already in `uv.lock`; existing tests cover the path;
  lowest risk; brand-tokens fit (swap `GREETING_ACCENT` constant).
- **Cons**: Layout is code, not a template — harder to theme later (Cycle 2
  Neon would fork the procedural code); no "resvg-ready" single switch.
- **Effort**: Low — split the class, rebrand colors, remove the compat shim.

### 3. resvg-python (pure-Rust wheel) — SVG → PNG, no C deps

- **Pros**: True wheel, no apt / no libcairo; SVG template benefits (diffable,
  resvg-ready by definition); fast.
- **Cons**: Adds a Rust-binary wheel (musl/manylinux) — needs pterodactyl
  platform validation; not in calibrated decision (would require re-asking);
  resvg-python is less mature than Pillow ecosystem.
- **Effort**: Medium — new dep + template + renderer. Out of calibrated scope.

## Recommendation

**Adopt Approach 2 (Pillow procedural, rebranded + split) as the Cycle 1
default**, and structure the renderer behind a **thin interface** so Cycle 2
can swap to cairosvg/resvg with a 1-line dependency-injection change.

Rationale:
- The calibrated decision names cairosvg as the stack, but the hard
  constraint (Pterodactyl `python:3.11-slim`, no apt) means `libcairo` is not
  guaranteed. Treating Pillow as the default keeps Cycle 1 shippable today;
  the SVG interface keeps the Cycle 2 (Neon) swap cost at 1 line.
- This does NOT contradict the calibrated decision — it preserves the
  "fallback Pillow" branch the decision already names, while deferring the
  libcairo availability question to the proposal/design phase where it can be
  resolved with a concrete pterodactyl base-image check.
- Cycle 1 scope is "Foundation Minimal (Nebulosa theme)" — that is a
  brand-token + SRP + hygiene pass, not a renderer migration. Pillow
  procedural with brand tokens delivers the Minimal theme.

**Hygiene fixes (all in-scope, all low-risk):** version bump 0.1.0→0.8.0,
rename duplicate `003` migration, add 4 `.gitignore` patterns, update
`openspec/config.yaml` (mypy→ty, 0.70→0.75, 400→800), add `updatedAt` to
`greeting_config` + model + DB layer, SHA-pin `code-quality.yml` actions,
create `README`, expand `.env.example`, fix 2 brand `INFO` bypasses.

**DRY fixes (all in-scope):** extract `verifyGuildAdmin` to a shared
dashboard lib (x4 → x1), extract the two `_err`/`_ok` helper pairs to
`bot/utils/embeds.py` (x4 cogs → x1), replace the 4 `select("*")` in
`ticket-actions.ts` with explicit column lists, remove the
`_generate_greeting_card_compatibly` shim (its fallback branch is dead —
`generate_greeting_card` already accepts all kwargs natively).

## Risks

- **cairosvg libcairo missing** ⚠️ HIGH — `python:3.11-slim` + no apt means
  cairosvg may ImportError at boot. The proposal MUST specify a concrete
  availability check (base image audit) OR commit to Pillow-as-default with
  SVG-via-interface for Cycle 2. This is the single biggest risk.
- **Font missing → base64 embed** — `Inter-Regular.ttf` IS present
  (`assets/fonts/Inter-Regular.ttf`, 407KB). `_load_font` (line 419) already
  falls back to `ImageFont.load_default()` on `OSError`. SVG path would need
  a base64 font embed in the template — documented as a Cycle 2 concern.
- **cairosvg without libcairo → Pillow fallback** — if Approach 1 is chosen
  despite the risk, the fallback must be a real tested branch, not a
  silent `except ImportError`. Current `_safe_fetch_avatar` pattern (line 377)
  shows the right shape: catch, log, degrade.
- **Cache leak without guild_id** — `cache_key(guild_id, entity)` (cache.py:28)
  already enforces `{guild_id}:{entity}`. New SVG/avatar caches MUST use this
  helper, never bare keys, or they leak across guilds. Greeting avatar cache
  (if added in Cycle 2) MUST be guild-scoped e.g. `cache_key(gid, "greeting_avatar")`.
- **`_generate_greeting_card_compatibly` is untested** — removing it (DRY)
  changes behavior for a code path with zero coverage. The removal must be
  guarded by first adding a test that exercises the native-kwargs path
  (Strict TDD: RED on the new behavior, GREEN by deletion).
- **Duplicate `003` migration rename** — renaming `003_subtitles_notes.sql`
  (or `003_economy_config.sql`) is a migration-identity change. On a live
  Supabase project this can desync `schema_migrations`. Memory note
  (2026-08-19) records prior "migration identity drift" pain on staging. The
  rename MUST be validated against the live `schema_migrations` table or done
  as a no-op reconciliation migration, NOT a raw file rename, if the project
  is already deployed.
- **Review budget 800 lines** — the hygiene + DRY surface is broad (≥10 files).
  If the proposal exceeds 800 LOC it should be split per the chained-PR
  strategy (delivery_strategy: auto-chain; chain_strategy TBD).

## Ready for Proposal

**Yes.** The orchestrator should tell the user:
- Cycle 1 can ship today on Pillow procedural (rebranded + SRP-split) with a
  renderer interface that keeps the Cycle 2 SVG/cairosvg swap at 1 line.
- One open decision for the proposal: confirm the Pterodactyl base image has
  (or can get) `libcairo` before committing to cairosvg-as-default; otherwise
  Pillow stays default and cairosvg becomes the Cycle 2 VPS upgrade.
- All hygiene + DRY fixes are confirmed in-repo with file:line evidence and
  fit the 800-line budget as a single change (or a 2-slice chain if needed).
