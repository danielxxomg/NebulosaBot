# Design: Bot Docs Polish

## Technical Approach

Deliver one concise Spanish manual plus targeted Discord metadata polish. The manual is a reviewable artifact, while code changes stay limited to the avatar embed contract and actual description/parameter-help gaps found in the current decorators. The command tree in source—not the stale “28 commands / 7 cogs” count—defines documentation coverage, including public groups and subcommands.

## Architecture Decisions

### Documentation shape

| Option | Trade-off | Decision |
|---|---|---|
| One Spanish manual | Can become stale | Create `docs/MANUAL.md`; keep it short and point readers to `/help` for the live list. |
| Separate admin/user guides | More navigation and duplication | Use one manual with audience signposts and progressive disclosure. |

**Rationale**: A single, answer-first document reduces discovery cost for both audiences without inventing a new documentation system.

### Command audit scope

| Option | Trade-off | Decision |
|---|---|---|
| Edit every cog mechanically | Unnecessary churn | Change only non-conforming descriptions and missing parameter annotations. |
| Merge apparently similar commands | Risks breaking distinct workflows/permissions | Do not remove commands: the audit found no duplicate behavior. |

**Rationale**: Registration `default_permissions` and runtime `is_mod`/`is_admin` checks are separate layers; they are not safe “redundancies” to remove in a copy-polish change.

### Avatar rendering

| Option | Trade-off | Decision |
|---|---|---|
| Generate a rank-style file | Adds I/O and image-service coupling | Keep the existing embed response. |
| Thumbnail | Too small | Replace the one `set_thumbnail` call with `set_image(url=f"{avatar_url}?size=1024")`. |

**Rationale**: This meets the utility-command delta without changing the command’s selection or fallback behavior.

## Data Flow

```
Cog decorators ──→ Discord command tree (/sync or restart) ──→ command picker/help
      │
      └──→ source-verified inventory ──→ Spanish MANUAL.md ──→ admins and users

/avatar: selected member/default avatar URL ──→ embed.set_image ──→ ctx.send
```

## Manual Outline

```text
# NebulosaBot — Manual
> Qué hace el bot y para quién es.
## 1. Vista general
## 2. Inicio rápido
## 3. Configuración del servidor
## 4. Estado del bot y ayuda en vivo
## 5. Casos de uso para usuarios
## 6. Casos de uso para moderación y administración
## 7. Referencia completa de comandos
### Para todos | Moderación | Administración y configuración
## 8. Deuda conocida y límites
```

Each use-case section leads with the task, then its command. The reference uses scannable tables with invocation, optional parameters, audience/permission, and a plain-language result; it includes ticket groups and subcommands exactly once.

## Command Polish Inventory

| Cog | Audit result / planned change |
|---|---|
| Core | Already normalized; `/help` parameter is described. No edit. |
| Utility | Existing descriptions and `member` help conform; change only `/avatar` image rendering. |
| Sentinel | Add trailing periods to all nine command descriptions; existing parameter descriptions remain. |
| Tickets | Add periods to panel/category descriptions; add missing descriptions for `configure_fields`, `subticket`, `reopen`, `transfer`, `note`, and their public subcommands. Keep existing parameter help. |
| Stellar | Add trailing periods to `daily`, `coins`, `leaderboard`, and `rank`; retain parameter help. |
| Greetings | Add periods and descriptions for test commands, welcome/goodbye groups, and public subcommands; retain parameter help. |
| Ocio | Already normalized; no edit. |
| Setup | Add trailing period and `@app_commands.describe()` for `ticket_category`, `mod_role`, `log_channel`, and `language`. |

All new descriptions use concise imperative English with a final period; runtime i18n strings remain unchanged.

## File Changes

| File | Action | Description |
|---|---|---|
| `docs/MANUAL.md` | Create | Spanish manual using the outline and source-verified reference tables. |
| `bot/cogs/utility.py` | Modify | Render `/avatar` with a 1024px `set_image` URL. |
| `bot/cogs/sentinel.py`, `tickets.py`, `stellar.py`, `greetings.py`, `setup.py` | Modify | Apply only inventory-listed descriptions and annotations. |
| `tests/test_utility_cog.py` | Modify | Move avatar assertions from `thumbnail` to `image` and assert the sized URL. |

## Interfaces / Contracts

```python
# Existing command contract; no new models or services.
embed.set_image(url=f"{avatar_url}?size=1024")

@app_commands.describe(
    ticket_category="Category for ticket channels",
    mod_role="Optional moderator role",
    log_channel="Optional moderation log channel",
    language="Optional server language",
)
```

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit (TDD) | Self, target, and fallback `/avatar` paths produce `embed.image.url` with `?size=1024`. | First change the three existing assertions (RED), make the one-line implementation (GREEN), then run `uv run pytest tests/test_utility_cog.py` and `uv run pytest`. |
| Metadata review | Description/annotation inventory. | Review decorators against this table; strings have no execution behavior, so no brittle string tests. |
| Manual review | Spanish clarity, required hierarchy, and full source-derived command coverage. | Review Markdown tables/headings; `/help` remains the runtime source of truth. |

## Migration / Rollout

No migration required. Deploy/restart the bot, then sync the tree (`/sync`) so Discord receives updated metadata; manually spot-check `/avatar` in Discord. Roll back with one revert.

## Open Questions

- [ ] Reconcile the delta spec’s pre-existing “28 commands / 7 cogs” wording with the current eight-cog, grouped-command source inventory before archive; it is not an implementation blocker.
