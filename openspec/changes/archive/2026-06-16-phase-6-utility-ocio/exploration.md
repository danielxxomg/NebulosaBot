## Exploration: Phase 6 — Utility + Ocio Cogs

### Current State

The bot has five cogs loaded in `setup_hook()`: CoreCog, SentinelCog, TicketsCog, StellarCog, GreetingsCog. Two listeners: XPListener, AuditListener. All infrastructure (DB, cache, services, embeds, context) is operational.

Key patterns established:
- Cogs use `class XxxCog(commands.Cog, name="Xxx")` with `__slots__`, `__init__(self, bot)`, and `async def setup(bot)`.
- Hybrid commands via `@commands.hybrid_command()`.
- Embeds use helpers from `bot/utils/embeds.py` (`info_embed`, `success_embed`, `error_embed`, `warning_embed`) or raw `discord.Embed` with `COLOR_INFO` for custom layouts.
- Context: some cogs use `NebulosaContext` (core), others use `commands.Context` directly (stellar, greetings). Both work.
- Avatar resolution: `_resolve_avatar_url()` helper pattern in greetings.py using `member.display_avatar.url`.
- Image generation: `asyncio.to_thread()` for Pillow operations.
- Tests: pytest + pytest-asyncio, `MagicMock(spec=...)` for Discord objects, `AsyncMock` for async services.

Assets directory contains only `assets/fonts/Inter-Regular.ttf`. No images directory exists yet.

### Affected Areas

- `bot/cogs/utility.py` — **NEW** — UtilityCog with /avatar, /serverinfo, /userinfo
- `bot/cogs/ocio.py` — **NEW** — OcioCog with /dados, /banana
- `bot/bot.py` — Add `load_extension()` calls for both new cogs in `setup_hook()`
- `assets/images/banana.png` — **NEW** — Static banana image for /banana command
- `tests/test_utility_cog.py` — **NEW** — Tests for avatar, serverinfo, userinfo
- `tests/test_ocio_cog.py` — **NEW** — Tests for dados, banana

### Approaches

#### 1. Two separate cogs (UtilityCog + OcioCog)

Each cog in its own file, loaded separately in `setup_hook()`.

- **Pros**: Clean separation of concerns (utility vs fun). Follows existing pattern of one-cog-per-file. Easy to unload/reload independently. Each cog stays small and focused.
- **Cons**: Two new files, two new `load_extension()` calls. Slightly more boilerplate.
- **Effort**: Low

#### 2. Single combined cog (FunCog or MiscCog)

Both utility and fun commands in one file.

- **Pros**: Fewer files, one `load_extension()` call.
- **Cons**: Mixes concerns. Violates the single-responsibility pattern established by other cogs. Harder to maintain as commands grow.
- **Effort**: Low

#### 3. UtilityCog as service-backed, OcioCog standalone

UtilityCog delegates to a UtilityService for serverinfo/userinfo formatting. OcioCog stays in-cog.

- **Pros**: Consistent with service pattern used by StellarCog/GreetingsCog.
- **Cons**: Overkill — these commands have zero business logic. No DB, no cache, no external API. A service layer would be pure ceremony with no testable value.
- **Effort**: Medium (unnecessary complexity)

### Recommendation

**Approach 1: Two separate cogs** — UtilityCog and OcioCog.

Rationale:
- Follows the established one-cog-per-module pattern (Core, Sentinel, Tickets, Stellar, Greetings).
- Both cogs are simple — no service layer needed. All logic stays in the cog (embed construction, random generation).
- Estimated ~250-350 lines total across both cogs + tests. Well within the 400-line review budget.
- The `/banana` command needs a static image asset (`assets/images/banana.png`). The `assets/images/` directory must be created.

### Command Implementation Details

#### /avatar `[member]`
- Parameter: `member: discord.Member | None = None` (defaults to `ctx.author`)
- Avatar URL: `target.display_avatar.url` (animated-aware, works for custom and default)
- Fallback: `target.default_avatar.url` if `display_avatar` is somehow unavailable
- Embed: `info_embed()` with thumbnail set to avatar URL, plus a "Open in browser" link
- No defer needed — pure Discord API data, no I/O

#### /serverinfo
- No parameters — uses `ctx.guild`
- Fields: name, owner (`guild.owner`), member_count, text/voice channel counts, role count, boost level, created_at
- Thumbnail: `guild.icon.url` if available
- Embed: raw `discord.Embed` with `COLOR_INFO` for custom field layout
- No defer needed

#### /userinfo `[member]`
- Parameter: `member: discord.Member | None = None` (defaults to `ctx.author`)
- Fields: name, discriminator/ID, roles (comma-separated, excluding @everyone), top role color, joined_at, created_at, bot status
- Thumbnail: `target.display_avatar.url`
- Embed: raw `discord.Embed` with `COLOR_INFO`
- No defer needed

#### /dados `[sides]`
- Parameter: `sides: int = 6` (app_commands.Range[2, 1000] for validation)
- Logic: `random.randint(1, sides)`
- Embed: `info_embed()` with dice emoji and result
- No defer needed

#### /banana
- No parameters
- Logic: `random.randint(2, 30)` for measurement in cm
- Image: `discord.File("assets/images/banana.png")` attached to embed
- Embed: `info_embed()` with measurement, image set via `embed.set_image(url="attachment://banana.png")`
- No defer needed — file is local, no network I/O

### Testing Strategy

Both cogs are pure embed construction — no service calls, no DB, no cache. Tests mock Discord objects and verify embed content:

- **UtilityCog tests**: Mock `ctx.guild`, `ctx.author`, optional `member`. Verify embed fields, thumbnail URLs, field values.
- **OcioCog tests**: Mock `ctx.send`. Verify embed description contains dice result in valid range. Verify banana embed has file attachment and measurement in 2-30 range.
- Follow existing pattern from `test_stellar_cog.py`: `MagicMock(spec=commands.Context)`, `MagicMock(spec=discord.Member)`, etc.

### Risks

- **Banana image asset**: No image exists yet. Must source or create `assets/images/banana.png`. If no suitable image is available, the command could fall back to a text-only response or an emoji-based response.
- **Guild-only commands**: `/serverinfo` requires `ctx.guild` to be non-None. Must handle DM context gracefully (error embed or early return).
- **Large role lists**: Servers with 100+ roles could produce very long role strings in `/userinfo`. Should truncate with a "and X more" suffix.

### Ready for Proposal

**Yes.** The scope is well-defined, the patterns are established, and the implementation is straightforward. The orchestrator can proceed to `sdd-propose` for the `phase-6-utility-ocio` change.

Key info for the proposal:
- Two new cog files, no new services
- One new asset directory + one image file
- Two new test files
- One modification to `bot.py` (two `load_extension()` lines)
- Estimated total: ~300 lines of new code + tests
