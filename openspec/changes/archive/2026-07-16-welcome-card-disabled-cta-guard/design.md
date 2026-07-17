# Design: Guard Disabled Welcome Cards from CTA-Only Sends

## Technical Approach

Preserve the implemented CTA guard: `dispatch_welcome()` keeps its guard ordering, the card-enabled flow remains unchanged, and only the welcome call to `_send_text_only_if_message()` enables formatted-whitespace normalization. The amendment adds a bounded static-typing slice: seven pre-existing diagnostics in `greeting_service.py` and the imported `Command` diagnostic at `i18n.py:294`. These edits are annotations, safe channel narrowing, and accurate ignore cleanup only; they must not change control flow or payloads.

## Architecture Decisions

| Decision | Alternatives / tradeoff | Rationale |
|---|---|---|
| Isolate CTA suppression in `_send_text_only_if_message()` | Change `_compose_welcome_content()` or duplicate formatting. | Direct formatting skips `_resolve_welcome_cta()` while preserving card-enabled composition. |
| Keep `normalize_whitespace` welcome-only | Normalize goodbye too or split helpers. | The helper is shared; the private mode preserves existing goodbye behavior. |
| Narrow resolved `GuildChannel` to `Messageable` at existing send boundaries | Keep inaccurate ignores, broaden return types, or refactor dispatch. | Explicit narrowing satisfies mypy while keeping valid configured text-channel sends and payloads unchanged. |
| Fix exactly the eight diagnostics | Apply broad strict typing or suppress errors globally. | The approved scope is reviewable and avoids unrelated behavior or files. |

## Data Flow

```text
dispatch_welcome → config/enable/channel guards → card disabled
  → _send_text_only_if_message(normalize_whitespace=True)
  → _format_template → strip-only emptiness gate → Messageable.send(text)
```

The disabled-card branch never resolves onboarding CTA data. The card-enabled path remains `generate card → _compose_welcome_content → _resolve_welcome_cta → send`. Goodbye retains its existing helper mode.

## File Changes

| File | Action | Description |
|---|---|---|
| `bot/services/greeting_service.py` | Modify | Retain the CTA guard; add explicit annotations, safe `GuildChannel`/`Messageable` narrowing, and remove or correct inaccurate unused ignores. |
| `bot/core/i18n.py` | Modify | Add the missing generic argument to `app_commands.Command` at line 294; no command behavior changes. |
| `tests/test_greeting_service.py` | Existing guard tests | Keep the current guard regression safety net for silence, text-only delivery, CTA isolation, localization, and preserved card-enabled behavior; no unrelated tests are added. |

## Interfaces / Contracts

The existing helper contract remains:

```python
async def _send_text_only_if_message(
    channel: discord.abc.Messageable,
    message_template: str,
    member: discord.Member,
    *,
    onboarding_channel_id: str | None = None,
    normalize_whitespace: bool = False,
) -> None
```

`_resolve_guild_channel()` continues to represent `discord.abc.GuildChannel | None`; callers narrow it safely to `discord.abc.Messageable` before sending. `_check_localizations()` supplies the project’s client type as the `Command` generic argument. Neither contract changes runtime semantics.

## Testing Strategy

| Layer | What to Test | Evidence |
|---|---|---|
| Unit | Existing welcome guard scenarios and card-enabled/goodbye preservation | `uv run pytest tests/test_greeting_service.py -v --no-cov`; existing guard tests assert payloads, attachments, and CTA non-invocation. |
| Static | Exactly eight diagnostics, including imported i18n typing | `uv run mypy bot/services/greeting_service.py` (mypy follows the `i18n` import). |
| Full suite | No runtime regression from typing-only edits | `uv run pytest`. |

No integration or E2E coverage is needed: this is service-local and Discord sends are mocked.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.

## Migration / Rollout

No migration required. The guard is already automatic; the typing slice requires no configuration, feature flag, or notice.

## Risks and Rollback

- **Risk**: channel narrowing accidentally changes an invalid-channel edge case. **Mitigation**: preserve existing guard order and valid text-channel send path; verify focused tests and mypy.
- **Risk**: static edits expand beyond approval. **Mitigation**: allowlist only the two application files and existing guard tests; no broad type cleanup.
- **Rollback**: revert only the typing hunks in the two application files. Keep the existing CTA guard and its regression tests; no database or configuration rollback is required.

## Open Questions

None — scope, allowlist, verification commands, and rollback boundary are approved.
