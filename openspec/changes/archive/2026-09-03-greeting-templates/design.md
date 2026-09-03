# Design: greeting-templates

## Technical Approach

`TEMPLATE_REGISTRY` in `greeting_renderer.py` (brand tokens only) + `select_template(config,kind)` (`welcome/goodbye_template_id`→`theme_id`→`default`, unknown→default). Dual-param `render(template_id,theme_id)` preserves `gaming_neon` byte-identity via unmodified `_render_neon_overlay`. Dual-write `themeId` one cycle. `StringSelect` pickers via `t()` with persistent `custom_id`s. Stacked ~1,065/1,500.

## Architecture Decisions

| Decision | Options | Tradeoff | Choice |
|----------|---------|----------|--------|
| Registry | dict/callable vs dataclass vs DB | Dict loses labels; DB needs ops | **Module `TEMPLATE_REGISTRY: dict[str,Template]` in `greeting_renderer.py`** — `Template(id,label_key,description_key,overlay_fn)`; single source. |
| Alias | Break `theme_id` vs dual-param | Break = churn | **Dual-param `render(...,template_id=None,theme_id=None)`**, `resolved=(template_id or theme_id or "default")`; `gaming_neon`→unmodified `_render_neon_overlay` 75-99 + `GaussianBlur(8)`+`ACCENT_A/B`. |
| New templates | New hex/fonts/size vs fixed canvas+tokens | New tokens violate no-token; size ripples to rank | **Fixed 934×282 via `_card_base()`**. `sunset_wave`: `_render_sunset_overlay` using `WARNING+ERROR` low-alpha diagonal+`PANEL_OVERLAY`. `minimal_light`: `_render_minimal_overlay` single `ACCENT` hairline + `CARD_BG_*/MUTED_TEXT`. No new fonts. |
| Selection | Inline vs helper vs cog | Inline dup; cog breaks layers | **`select_template(config,kind)` in `greeting_service.py`**; `dispatch_greeting` + `_handle_test` (welcome 340-351, goodbye 261-272) forward `template_id=resolved,theme_id=resolved` via `asyncio.to_thread` (guard `test_greeting_service_thread:28`). |
| Model+DB | New cols only vs drop legacy vs dual-write | Drop breaks rollback | **`GreetingConfig` adds 2 fields**; `from_db_row` new→`themeId`→None; `to_db_dict` writes both new cols + `themeId=(welcome or goodbye or theme_id)` (welcome wins tie; kind setter mirrors its kind). Extend `_GREETING_CONFIG_COLUMNS`. |
| Picker UX | Buttons vs `StringSelect` in modules | Buttons need extra view | **`StringSelect` in `components()`** — `setup:welcome:select_template` / `setup:goodbye:select_template` (persistent, rerouted via `MODULES`), 4 opts from registry + `t()`, `set_*_template_id()` → `save_config` + `cache.invalidate(cache_key)` + CDC; gate `greeting.manage` only; `render_async` shows resolved label. |
| i18n | Hardcoded vs keys | Hardcoded fails coverage | **16 keys** in `bot/locales/{es,en}.json`; renderer `t()`-free. |
| Slicing | Single PR vs 3 chained | Single >400 risk | **S1 no-DDL byte-identity, S2 persistence 030+fallback, S3 pickers+i18n** — unknown→default keeps master green. |

## Data Flow

```
Select(setup:welcome|goodbye:select_template) —can_member(greeting.manage)→
 set_*_template_id → save_config(dual-write) → Supabase —CDC→ TTLCache invalidate →
 dispatch/_handle_test → select_template → asyncio.to_thread(render_fn,template_id,theme_id) →
 TEMPLATE_REGISTRY[resolved].overlay_fn(img) → PNG → channel.send
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `bot/services/greeting_renderer.py` | Modify | `Template`+registry 4, `_render_sunset/minimal` (brand only), dual-param `render`; keep `75-99` |
| `bot/services/greeting_service.py` | Modify | `select_template()`; `dispatch_greeting` via `to_thread` |
| `bot/models/greeting_config.py` | Modify | 2 fields; fallback chain; dual-write `themeId` |
| `bot/core/db/greeting_db.py` | Modify | Extend `_GREETING_CONFIG_COLUMNS` |
| `supabase/migrations/030_greeting_templates.sql` | Create | `ADD COLUMN IF NOT EXISTS` + `COALESCE` |
| `bot/views/setup_modules/welcome.py` | Modify | `StringSelect` 4 via `t()`, `handle`, `set_*`, `render_async`, `_handle_test` |
| `bot/views/setup_modules/goodbye.py` | Modify | Mirror welcome |
| `bot/locales/{es,en}.json` | Modify | 16 keys |
| `tests/test_greeting_template_registry.py` | Create | 4 keys, unknown→default, byte-identity, t()-free |
| `tests/test_*` | Modify | Extend service/config/thread/setup/migrations |

## Interfaces / Contracts

```python
@dataclass(frozen=True)
class Template:
    id: str; label_key: str; description_key: str
    overlay_fn: Callable[[Image.Image], None] | None

TEMPLATE_REGISTRY: dict[str,Template]  # gaming_neon → _render_neon_overlay
class GreetingRenderer(Protocol):
    def render(self, *, username: str, avatar_url: str|None, guild_name: str, member_count: int,
               card_type: str, greeting_title: str, member_count_text: str,
               guild_icon_url: str|None=None, template_id: str|None=None, theme_id: str|None=None) -> io.BytesIO: ...
def select_template(config: GreetingConfig, kind: Literal["welcome","goodbye"]) -> str: ...
# GreetingConfig: welcome_template_id/goodbye_template_id: str|None
```

Picker ids `setup:welcome:select_template`, `setup:goodbye:select_template` (`timeout=None`). Permission `greeting.manage`.

**16 keys**: `setup.module.welcome.template_label/placeholder/select_title/select_description`, `setup.module.goodbye.template_label/placeholder/select_title/select_description`, `templates.greeting.default.label/description`, `templates.greeting.gaming_neon.label/description`, `templates.greeting.sunset_wave.label/description`, `templates.greeting.minimal_light.label/description`.

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | Registry 4, unknown→default, t()-free, no hex | `test_greeting_template_registry.py` NEW |
| Unit | gaming_neon byte-identical | Same inputs → equal bytes + GaussianBlur |
| Unit | `select_template` chain | Extend `test_greeting_service.py` |
| Unit | Config fallback+dual-write | Extend `test_greeting_config.py` |
| Unit | `to_thread(...,template_id,theme_id)` | Extend `test_greeting_service_thread.py` |
| Integration | Picker 4 opts, `render_async`, `set_*`→save+invalidate | Extend `test_setup_module_*` |
| Migration | 030 `IF NOT EXISTS`+`COALESCE` | Extend `test_migrations.py` |
| Guards | `brand_no_hex`, `i18n_key_coverage` | Existing |

Strict TDD; `uv run pytest`.

## Threat Matrix

N/A — no routing/shell/subprocess/VCS/executable/process integration.

## Migration / Rollout

`030` (latest `029` verified):
```sql
ALTER TABLE greeting_config ADD COLUMN IF NOT EXISTS "welcomeTemplateId" TEXT;
ALTER TABLE greeting_config ADD COLUMN IF NOT EXISTS "goodbyeTemplateId" TEXT;
UPDATE greeting_config SET "welcomeTemplateId"=COALESCE("welcomeTemplateId","themeId") WHERE "welcomeTemplateId" IS NULL;
UPDATE greeting_config SET "goodbyeTemplateId"=COALESCE("goodbyeTemplateId","themeId") WHERE "goodbyeTemplateId" IS NULL;
-- Rollback: DROP COLUMN IF EXISTS "welcomeTemplateId","goodbyeTemplateId"
```
Chained S1→S2→S3 each `pytest` + `ty/ruff/vulture` 0 + guards green.

## Source Verification / Drift Check

- Renderer `28-44`, `_render_neon_overlay` `75-99`, total `75-255`, Protocol `103-123` exact.
- Service `get_config` `72-98`→`63-88`; `dispatch` `109-245`→`132-245`+`resolve 109-130`.
- `shared_assets` 934×282; `brand.py` tokens present.
- `welcome`/`goodbye`/`setup_panel` seams verified.
- `021` precedent + `029` latest ⇒ `030` correct; engram unavailable, verified directly.

## Open Questions

- [ ] Tie-break welcome wins; kind setter mirrors own kind.
- [ ] Sunset contrast — adjust alpha only if legibility fails.

## Slice Boundaries

- **S1 (~385)**: registry+dual-param+stubs+`select_template`+preview; no DDL.
- **S2 (~270)**: `030`+model/db fallback+dual-write.
- **S3 (~410)**: `StringSelect` both modules+16 keys+`render_async`.
