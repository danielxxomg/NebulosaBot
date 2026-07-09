# Exploration: bot-docs-polish

## Current State

### Documentation Surface
- **No README.md** exists at project root.
- **No docs/ directory** exists.
- **No PRODUCT.md** exists.
- **openspec/** has 24+ domain specs and 7 archived changes — solid spec coverage but no user-facing docs.
- **AGENTS.md** exists (code review rules for contributors).
- **Diagramas/** has 4 Mermaid/PlantUML design diagrams (architecture-level, not user docs).
- **bot/locales/** has `en.json` and `es.json` — i18n for runtime responses.

### Command Inventory (28 hybrid commands across 7 cogs)

| Cog | Command | Description | Audience |
|-----|---------|-------------|----------|
| **Core** | `/ping` | Show WebSocket latency | User |
| | `/status` | DB/cache health | Mod |
| | `/help [module]` | Command listing | User |
| | `/sync` | Sync command tree | Admin |
| **Sentinel** | `/warn <member> [reason]` | Warn member | Mod |
| | `/unwarn <member>` | Remove warning | Mod |
| | `/mute <member> [duration] [reason]` | Timeout member | Mod |
| | `/unmute <member>` | Remove timeout | Mod |
| | `/kick <member> [reason]` | Kick member | Mod |
| | `/ban <member> [reason] [delete_days]` | Ban member | Admin |
| | `/lock [channel]` | Lock channel | Mod |
| | `/unlock [channel]` | Unlock channel | Mod |
| | `/modlogs <member> [type] [after]` | Moderation history | Mod |
| **Tickets** | `/ticket_panel [title] [desc]` | Deploy panel | Mod |
| | `/create_category <name> [emoji] [desc] [pos]` | Create category | Mod |
| | `/list_categories` | List categories | Mod |
| | `/delete_category <id>` | Delete category | Mod |
| | `/subticket create [parent_id]` | Create sub-ticket | Mod |
| | `/reopen [ref]` | Reopen ticket | Mod |
| | `/transfer <member>` | Transfer ticket | Mod |
| | `/note add\|list\|delete` | Ticket notes | Mod |
| **Stellar** | `/daily` | Claim daily coins | User |
| | `/coins [member]` | Check balance | User |
| | `/leaderboard [type]` | XP/coins board | User |
| | `/rank [member]` | Rank card image | User |
| **Greetings** | `/welcome config\|channel\|toggle\|message` | Welcome config | Admin |
| | `/goodbye config\|channel\|toggle\|message` | Goodbye config | Admin |
| | `/welcome_test` | Test welcome card | Admin |
| | `/goodbye_test` | Test goodbye card | Admin |
| **Utility** | `/avatar [member]` | Show avatar | User |
| | `/serverinfo` | Server info | User |
| | `/userinfo [member]` | User info | User |
| **Ocio** | `/dados [sides]` | Roll dice | User |
| | `/banana` | Banana measurement | User |
| **Setup** | `/setup <category> [mod_role] [log_channel] [lang]` | Guild config | Admin |

### Avatar Command — Current Behavior
`bot/cogs/utility.py` lines 41-62: uses `embed.set_thumbnail(url=avatar_url)`. Discord renders thumbnails at ~80×80 px by default — small. The image URL supports a `?size=` parameter (Discord CDN) up to 4096.

### Command Description Audit (slash descriptions)
Descriptions are **hardcoded English strings** in `@commands.hybrid_command(description=...)`. They are NOT localized — this is by design (noted in sentinel.py and stellar.py docstrings: "Slash command descriptions are Discord UI metadata, not runtime responses. They remain in English.").

Current descriptions vary in quality:
- **Good**: `"Show the bot's WebSocket latency."`, `"Show database and cache health."`, `"Claim your daily coin reward"`
- **Terse**: `"Warn a member"`, `"Show a member's avatar."`, `"Show server information."`
- **Missing trailing period**: `"Warn a member"`, `"Timeout a member"`, `"Kick a member from the server"`
- **No overlaps**: no duplicate commands found. All 28 commands have unique names and purposes.

## Affected Areas
- `bot/cogs/utility.py` — avatar image size change (`set_thumbnail` → `set_image` or URL size param)
- `bot/cogs/*.py` — command description polish (7 files, ~28 descriptions)
- New file: `docs/manual.md` or `PRODUCT.md` — the bot manual
- `bot/locales/en.json`, `bot/locales/es.json` — no changes needed (descriptions stay English)
- `openspec/specs/` — reference material for the manual

## Approaches

### 1. Single change: docs + avatar + descriptions
One proposal, one PR. The manual documents all three changes; avatar fix and description polish are bundled.

- Pros: Single review cycle, cohesive "polish" narrative
- Cons: Mixed concerns (docs artifact vs. code change), PR may exceed 400 lines if manual is long
- Effort: **Medium**

### 2. Split into two sub-changes
- **bot-docs-polish (a)**: Manual + command audit report (docs-only, no code changes)
- **bot-docs-polish (b)**: Avatar size fix + description polish (code changes, small PR)

- Pros: Clean separation of concerns, each PR stays small, manual can reference the polished descriptions
- Cons: Two cycles, orchestration overhead
- Effort: **Medium** (each sub-change is Low)

### 3. Three sub-changes
- Manual (docs-only)
- Avatar fix (tiny code PR)
- Description polish (code PR)

- Pros: Maximum granularity, each PR trivially small
- Cons: Overkill — description polish is ~28 string edits, not worth its own cycle
- Effort: **Low per piece, Medium total** (overhead)

## Recommendation

**Approach 1 (single change)** is the right call. The three deliverables are thematically unified ("bot polish") and the code changes are small (avatar: ~5 lines; descriptions: ~28 string edits). The manual is the heavyweight; it should be the primary artifact. The code changes can go in a single PR alongside or after.

**Avatar fix**: Change `embed.set_thumbnail(url=avatar_url)` to `embed.set_image(url=avatar_url)` in `bot/cogs/utility.py:61`. Optionally add `?size=1024` to the URL for guaranteed high-res. This is a 1-line change.

**Command audit deliverable**: A markdown report embedded in the manual (not a separate file). Covers: full command table, description quality notes, permission model summary, no redundant commands found.

**Manual structure** (recommended):
```
# NebulosaBot — Manual
## Quick Start (setup, first commands)
## Configuration (/setup, guild settings)
## Bot State (what runs where, services, cache)
## Commands
### For Everyone
### For Moderators
### For Administrators
## Ticket System
## Economy & Levels
## Welcome & Goodbye Cards
## Technical Debt & Known Limitations
```

## Risks
- **Manual staleness**: a manual goes stale as commands change. Mitigation: keep it concise, reference `/help` for live command listing.
- **Avatar size UX**: `set_image` renders at 300-400px wide in embeds — may be "too large" for some tastes. Test in Discord before committing.
- **Description changes = slash command re-sync**: editing `description=` in hybrid commands requires a tree sync (`/sync` or bot restart) for Discord to pick up the new descriptions. No code risk, just operational.

## Product Questions

1. **Manual format**: Should the manual live as a single `docs/manual.md` file in the repo, or as a `PRODUCT.md` at root, or somewhere else? The repo has no existing docs convention.
2. **Manual language**: The bot supports `es` and `en`. Should the manual be English-only (code artifacts convention per AGENTS.md) or bilingual?
3. **Avatar size**: `set_image` shows the avatar at ~300-400px wide (embed image). Is that the desired "larger", or do you want a dedicated image file (like `/rank` does)?
4. **Description polish scope**: Should we only normalize trailing periods and improve terse descriptions, or also add `@app_commands.describe()` annotations where missing?
5. **Manual audience**: Is this manual for bot admins (who deploy/configure) or end users (who use commands)? Or both?

## Ready for Proposal
**Yes** — once the product questions are answered, the proposal can scope the manual outline, avatar fix approach, and description audit checklist.
