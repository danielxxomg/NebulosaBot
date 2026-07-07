# Design: Runtime Bugfixes

## Technical Approach

Apply five narrow fixes under strict TDD. C3 is corrected from the failed design: realtime-py 2.31.0 delivers postgres callbacks as `{data, ids}` (`realtime/types.py:105-107`), and dispatch checks `payload["data"]["type"]` (`types.py:140-146`). Therefore `bot/core/realtime.py` must normalize `data = payload.get("data", {})` before reading `type`, `table`, `record`, or `old_record`. C4 is corrected from the failed design: channel close does not call `subscribe()` callbacks; `ChannelCloseMessage` calls `channel.on_close()` with no payload (`channel.py:547-554`). WebSocket close code/reason are available only in `AsyncRealtimeClient._on_connect_error(e)` (`client.py:212-217`).

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| C1 FK cleanup | Add `migrations/006_drop_user_table.sql` dropping all 4 FKs then `DROP TABLE IF EXISTS "user"`. | Keep table or only drop `member.userId` FK. | Bot never writes `user`; all 4 User FKs can break runtime writes. |
| C2 received counter | Add `_received_count`, increment first in `_handle_cdc`; watchdog reads it. | Reuse `_event_count`. | Keeps processed invalidation count separate from received CDC count. |
| C3 payload normalization | Add `_normalize_cdc_payload(payload, table_hint)` returning `data`, `table`, `record`. | Keep top-level reads; table hint as primary. | Root cause is wrong nesting. `table_hint` remains secondary robustness only. |
| C4 close logging | Wrap client `_on_connect_error(e)` for bot-level WebSocket close code/reason logging; wrap `channel.on_close()` only to record `CLOSED` state with code/reason unavailable; health check escalates repeated unhealthy cycles. | Test `_on_subscribe("CLOSED")`; rely only on SDK logger. | Installed SDK has no clean public close hook; this follows actual dispatch and avoids pretending `subscribe()` receives closes. |
| S1 asset | Move root WebP `banana.png` to `assets/images/banana.webp`. | Keep misleading `.png`. | Path and extension match actual WebP content and spec. |

## Data Flow

```text
on_postgres_changes(table=T, callback=lambda p, T=T: _cdc_callback(p, T))
  -> _handle_cdc(payload, table_hint=T)
       -> _received_count += 1
       -> data = payload.get("data", {})
       -> table = data.get("table") or table_hint
       -> record = data["old_record"] when data["type"] == "DELETE" else data["record"]
       -> guild_id mapping / ticket_note resolver
       -> self-echo? skip : invalidate_guild(guild_id); _event_count += 1

WebSocket ConnectionClosedError -> wrapped client._on_connect_error(e)
  -> bot log code/reason -> SDK reconnects -> health check logs recovery/escalation
```

## File Changes

| File | Action | Description |
|---|---|---|
| `migrations/006_drop_user_table.sql` | Create | Idempotently drop `member`, `infraction`, `ticket` FKs to `"user"`, then drop table. |
| `bot/core/realtime.py` | Modify | Add received/unhealthy counters, payload normalization, table-hint callback routing, actual close/reconnect logging. |
| `tests/test_realtime.py` | Modify | Add failing tests for nested SDK payloads, received counter, close wrapper, health escalation. |
| `bot/cogs/ocio.py` | Modify | Use `assets/images/banana.webp` and `banana.webp` attachment URL/name. |
| `tests/test_ocio_cog.py` | Modify | Assert WebP path and attachment name. |
| `banana.png` | Move | Rename root WebP to `assets/images/banana.webp`. |

## Interfaces / Contracts

```python
_received_count: int
_unhealthy_cycles: int
REALTIME_UNHEALTHY_ERROR_CYCLES: int = 3

def _record_for_event(data: dict) -> dict: ...
def _normalize_cdc_payload(payload: dict, table_hint: str | None = None) -> tuple[str | None, dict]: ...
def _cdc_callback(self, payload: dict, table_hint: str | None = None) -> None: ...
async def _handle_cdc(self, payload: dict, table_hint: str | None = None) -> None: ...
def _wire_close_logging(self) -> None: ...
```

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | C3 actual SDK payload | Use `{ "data": {"type":"UPDATE","table":"guild","record":{"id":"G1"},"old_record":{}}, "ids":[1] }`; assert invalidation. |
| Unit | C3 fallback | Same payload with missing `data.table`, pass `table_hint="guild"`; assert invalidation; no top-level `record` reads. |
| Unit | C2 watchdog | Send skipped/unresolvable payload; assert `_received_count` increments and watchdog uses it. |
| Unit | C4 close/reconnect | Fake client `_on_connect_error` wrapper with object exposing `code`/`reason`; assert bot log and delegated reconnect. Wrap `channel.on_close()` to set `CLOSED`; health cycles escalate WARNING→ERROR and reset on `SUBSCRIBED`. |
| Unit | S1 | Patch path existence; assert `discord.File(..., filename="banana.webp")` and `attachment://banana.webp`. |
| Static | C1 migration | Assert SQL contains all 4 `DROP CONSTRAINT IF EXISTS` clauses and `DROP TABLE IF EXISTS "user"`. |

## Migration / Rollout

Run migration 006 after backup, then verify `to_regclass('public.user') IS NULL` and no constraints reference `"user"`. Code rollout is backward compatible; top-level CDC tests may remain only as legacy compatibility if implemented behind normalization.

## Open Questions

- [ ] Non-blocking: installed SDK exposes no public close hook; wrapping private `_on_connect_error` should be revisited if realtime-py adds one.
