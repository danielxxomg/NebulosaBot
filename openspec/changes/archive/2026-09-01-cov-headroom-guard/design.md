# Design: cov-headroom-guard

## Technical Approach

Tests-only slice lifting 80.53%→≥80.8% via the two lowest files: `bot/bot.py` (77.6%, 82 misses) and `bot/cogs/core.py` (54.8%, 127 misses). Two modules (~190 ln) reuse `tests/conftest.py` fixtures and real `t()` locales; no prod code touched. Fixes `sys.modules` hygiene in `test_bot_probe.py`. Assertions check `embed`/`call_args`/logs, never `does not raise`. Satisfies `proposal.md` (150–250 ln, mocked branches, seed 42) and `test-suite-governance` (KEEP & parametrization untouched, ledger in commit body).

## Architecture Decisions

| Decision | Options | Tradeoff | Choice |
|----------|---------|----------|--------|
| File topology | Extend existing vs 2 new modules | Extend clutters suites & risks order flake | **2 new modules** (`test_bot_branch_coverage.py`, `test_core_branch_coverage.py`) + 4-line hygiene patch to `test_bot_probe.py`; isolated revert via `git revert`. |
| Fixtures | New fixtures vs reuse `conftest.py` | New fixtures = hidden coupling | **Reuse** `cache`, `mock_db`, `make_ctx`/`make_interaction`/`make_member`, `_isolate_i18n_state`; only local `_make_bot()` helper. |
| cairosvg probe | `patch.dict(sys.modules)` vs `__import__` only | `sys.modules` mutates global import table, flakes under `pytest-randomly` | **Patch `builtins.__import__` only** (raise `ImportError` for `cairosvg`); assert `isinstance(...PillowGreetingRenderer)` + WARNING. |
| Retention seam | Real `config.toml` vs mocked `find_spec` + fake module | Real file = filesystem coupling | **Mock `importlib.util.find_spec` + fake `bot.operational_config` via `types.ModuleType`** patched at `bot.bot.importlib.util.find_spec`; DB via `bot.db._client = AsyncMock()` with `table().upsert().execute()` / `rpc().execute()` as `AsyncMock`. No `sys.modules` mutation. |
| Error/handler seam | Real `Interaction` vs `MagicMock(spec=…)` | Real needs gateway | **`MagicMock(spec=discord.Interaction)`** with `AsyncMock` response/followup, real `t()` locales. |

## Data Flow

```
pytest --randomly-seed=42 → _isolate_i18n_state → test → patch target → bot/core code → assert(embed / call_args / log)
                              └──── real TTLCache / t() / MagicMock Discord ────┘
```

No new runtime path; no background loop (DB-sourced durability N/A).

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `tests/test_bot_branch_coverage.py` | Create | `_setup_retention` (config present/absent, `retention_enabled=False`→4 cron unschedules), `_start_realtime` degraded, `get_context`, `on_app/command_error` (MissingPermissions/CheckFailure/Cooldown+crash), `_validate_single_panel` (missing channel/msg, redeploy, Forbidden). ~110 ln |
| `tests/test_core_branch_coverage.py` | Create | `_is_interaction`, `_guild_id_from_source`, `_resolve_prefix`, `_InteractionCtx.send/defer`, `_send_via`, `ping/status/help` shim vs slash, `_build_cog_help_embed` hidden filter & group expansion. ~85 ln |
| `tests/test_bot_probe.py` | Modify | Remove `patch.dict(sys.modules, {"cairosvg":None})` / `sys.modules.pop`; keep `patch("builtins.__import__")` only. -4 ln |
| `tests/conftest.py`, `bot/bot.py`, `bot/cogs/core.py`, `openspec/specs/*` | Keep | Reuse or untouched. |

## Interfaces / Contracts

No new prod interfaces. Helper:

```python
def _make_bot() -> NebulosaBot:
    return NebulosaBot(config=BotConfig(discord_token="t", supabase_url="https://x.supabase.co", supabase_key="k"),
                       intents=discord.Intents.default())
# patch targets: "bot.bot.Database", "bot.bot.RealtimeCacheSubscriber",
# "bot.bot.importlib.util.find_spec", "bot.bot.deploy_ticket_panel",
# "bot.bot.CrashReportService", "bot.bot.logger"
```

i18n keys via real `bot/locales/{es,en}.json`; no new keys.

## Testing Strategy

| Target | Assertion (anti-tautology) | Seam |
|--------|---------------------------|------|
| `_setup_retention` | `table().upsert` with `key`/`days`; `retention_enabled=False`→4× `cron_unschedule`; `find_spec→None`→defaults | Mock `find_spec` + fake `OperationalConfig` |
| `_start_realtime` | `cache is None` early return; `start()` raises → logged, `_realtime_subscriber is None` | Patch `start` raising |
| `get_context` | `ctx._guild_config == GuildConfig`; error → `None` + `logger.exception` | Real `get_context` + `AsyncMock` service |
| `on_app/command_error` | `MissingPermissions`/`CheckFailure`/`Cooldown` embeds; generic → `logger.error(exc_info=…)` + `CrashReportService.record` + `unexpected_*`; `is_done=True`→`followup.send` | `MagicMock(spec=Interaction)`; check `embed`/`ephemeral` |
| `_validate_single_panel` | Guild absent→warn; `channel None`→`update_guild_panel(None,None)`; `NotFound`→redeploy; stripped→redeploy; `Forbidden`/`HTTPException`→warn | `patch.object(type(bot),"guilds")` + `components` tree |
| `core` helpers | `_is_interaction`/`_guild_id_from_source` booleans; `_resolve_prefix=[]`; `_InteractionCtx.send/defer`; `_send_via`; `ping/status/help` embed fields + `EmbedPaginator` | `MagicMock(spec=Interaction)` vs `make_ctx` |

Hygiene: never `sys.modules`; `io.BytesIO` for file-likes (N/A here but enforced); `MagicMock` never as `PathLike`; all tests use `pytest.mark.asyncio` and pass under `seed 42` + random order via `_isolate_i18n_state`.

## Source Verification / Drift Check

- `cairosvg` probe claimed `bot/bot.py:216,224` → verified `bot/bot.py:216` `_cairosvg_available=True`, `224` `logger.info("cairosvg available…")` ✓ exact.
- `_setup_retention` claimed `306–385` → verified `296–385` (`def` at 296) drift +10 ln start, end exact.
- `on_app/command_error` claimed `498–654` → verified `474–568` + `570–664` (two handlers merged in proposal) drift is window merge only.
- `_validate_single_panel` claimed `726–821` → verified `759–838` (+33 ln offset, same body).
- `core` helpers claimed `32,36–42,72–105` → verified `30,35–42,62–106` within 2 ln; `_send_via` `231–399` → `229–245` + `251–399` ✓.
- `conftest._isolate_i18n_state` `71–88`, `make_member/make_ctx` `339–463`, locales `common.error.*`/`core.*`/`ocio.cooldown.*` all present ✓.
- `coverage --show-missing` confirms same gaps: `bot.py` 216,224,306,323–324,337–338,361–385 etc.; `core.py` 32,36–42,72–105,231–245 etc. — no missing census target.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. Tests-only with mocked Discord/Supabase.

## Migration / Rollout

No migration. One lean PR (150–250 ln) to `master`; revert is `git revert <sha>`. Gates: `uv run pytest --cov --cov-fail-under=80 --randomly-seed=42 -q` + random seed green, `ty`/`ruff`/`vulture` 0, cov ≥80.8%, KEEP green, no prod diff. Ledger in commit body (`files: A→B`, `lines: X→Y`, `collected: N→M`, `cov: 80.53%→Z%`, seed 42).

## Open Questions

- [ ] Keep `test_bot_probe.py` hygiene patch in this slice or split to a zero-risk hygiene commit? (Low risk either way.)

