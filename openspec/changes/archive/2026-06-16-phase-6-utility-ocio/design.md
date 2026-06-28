# Design: Phase 6 — Utility + Ocio Cogs

## Technical Approach

Two standalone cogs — `UtilityCog` and `OcioCog` — with no service layer. All logic stays in-cog: embed construction via existing helpers and `random.randint()` for dice/banana. Follows the established one-cog-per-file pattern (Core, Sentinel, Tickets, Stellar, Greetings). Both cogs use `commands.Context` directly (not `NebulosaContext`) since they need no guild config access.

## Architecture Decisions

| Decision | Options | Tradeoff | Choice |
|----------|---------|----------|--------|
| Cog structure | Two cogs vs single combined | Separation of concerns vs fewer files | Two cogs — matches existing pattern |
| Service layer | Service-backed vs in-cog | Consistency vs unnecessary ceremony | In-cog — zero DB/cache/API calls |
| Context type | `NebulosaContext` vs `commands.Context` | Guild config access vs simplicity | `commands.Context` — no config needed |
| Embed strategy | `info_embed()` vs raw `discord.Embed` | Helpers for simple / raw for multi-field | Mixed — `info_embed()` for dados/banana/avatar, raw `discord.Embed(COLOR_INFO)` for serverinfo/userinfo multi-field layouts |
| Banana asset | Static file vs generated | Simplicity vs dynamic | Static `assets/images/banana.png` — no Pillow needed |
| Dice range | `Range[2, 100]` vs `Range[2, 1000]` | Proposal says 100, exploration says 1000 | `Range[2, 1000]` — exploration is more recent, broader fun |

## Data Flow

```
User command (slash or prefix)
    │
    ▼
┌─────────────────┐     ┌──────────────────┐
│  UtilityCog     │     │  OcioCog         │
│  /avatar        │     │  /dados          │
│  /serverinfo    │     │  /banana         │
│  /userinfo      │     │                  │
└───────┬─────────┘     └────────┬─────────┘
        │                        │
        ▼                        ▼
  discord.Embed            discord.Embed
  (info/raw)               + discord.File (banana)
        │                        │
        └──────── ctx.send ──────┘
```

No external I/O. No service calls. No database. Pure embed construction + `random.randint()`.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `bot/cogs/utility.py` | Create | UtilityCog — `/avatar`, `/serverinfo`, `/userinfo` hybrid commands |
| `bot/cogs/ocio.py` | Create | OcioCog — `/dados`, `/banana` hybrid commands |
| `assets/images/banana.png` | Create | Static banana image for `/banana` command |
| `bot/bot.py` | Modify | Add two `load_extension()` calls in `setup_hook()` after GreetingsCog |
| `tests/test_utility_cog.py` | Create | Unit tests for avatar, serverinfo, userinfo |
| `tests/test_ocio_cog.py` | Create | Unit tests for dados, banana |

## Interfaces / Contracts

### UtilityCog

```python
class UtilityCog(commands.Cog, name="Utility"):
    __slots__ = ("bot",)

    @commands.hybrid_command(name="avatar", description="Show a member's avatar.")
    async def avatar(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        # Defaults to ctx.author. Embed with thumbnail = display_avatar.url.

    @commands.hybrid_command(name="serverinfo", description="Show server information.")
    async def serverinfo(self, ctx: commands.Context) -> None:
        # Error embed if ctx.guild is None (DM). Raw Embed with fields: name, owner, member_count, channels, roles, boost, created_at.

    @commands.hybrid_command(name="userinfo", description="Show user information.")
    async def userinfo(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        # Defaults to ctx.author. Roles truncated at 20 with "and N more" suffix.
```

### OcioCog

```python
class OcioCog(commands.Cog, name="Ocio"):
    __slots__ = ("bot",)

    @commands.hybrid_command(name="dados", description="Roll a dice.")
    @app_commands.describe(sides="Number of sides (2-1000)")
    async def dados(self, ctx: commands.Context, sides: app_commands.Range[int, 2, 1000] = 6) -> None:
        # random.randint(1, sides). info_embed with result.

    @commands.hybrid_command(name="banana", description="Measure something in bananas.")
    async def banana(self, ctx: commands.Context) -> None:
        # random.randint(2, 30) cm. info_embed + discord.File("assets/images/banana.png").
```

### bot.py modification

```python
# After GreetingsCog load in setup_hook():
await self.load_extension("bot.cogs.utility")
logger.info("Cog loaded: UtilityCog")

await self.load_extension("bot.cogs.ocio")
logger.info("Cog loaded: OcioCog")
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `/avatar` self + target | Mock `ctx.author`, verify embed thumbnail URL matches `display_avatar.url` |
| Unit | `/serverinfo` guild + DM | Mock `ctx.guild` with fields; mock `ctx.guild = None` for DM error path |
| Unit | `/userinfo` role truncation | Mock member with 25+ roles, verify "and N more" suffix at 20 |
| Unit | `/dados` range validation | Call with sides=6, sides=20, sides=1000; verify result in `[1, sides]` |
| Unit | `/banana` attachment | Verify `discord.File` attached, measurement in `[2, 30]` |
| Unit | Error paths | DM context for `/serverinfo`, missing banana file |

Pattern: follow `test_stellar_cog.py` — `MagicMock(spec=commands.Context)`, `MagicMock(spec=discord.Member)`, `AsyncMock` for `ctx.send`, invoke via `cog.command.callback(cog, ctx, ...)`.

## Migration / Rollout

No migration required. No database changes, no config changes, no feature flags. Two new `load_extension()` lines in `setup_hook()` — reversible by removing them.

## Open Questions

- [ ] Banana image asset: needs to be sourced or created. If unavailable at implementation time, use a placeholder PNG.
