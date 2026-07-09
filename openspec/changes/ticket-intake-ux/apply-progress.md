# Apply Progress: ticket-intake-ux

**Change**: `ticket-intake-ux`
**Mode**: Strict TDD
**Commits**:
- `517f744` — model + migration 013 (subject/description)
- `9d4ab07` — modal, pin, embed, i18n, service threading
- `8ea158f` — remediation (tests + ruff/mypy)
- follow-up — test ruff cleanups

## Implementation Progress

All 23 tasks complete. Full suite: 1053+ passed.

## TDD Cycle Evidence (all phases)

| Task | Layer | RED | GREEN | Notes |
|------|-------|-----|-------|-------|
| 1.1 subject/description model tests | Unit | ✅ | ✅ | `tests/test_ticket_model.py` — 8 cases |
| 1.2 Ticket dataclass fields | Unit | — | ✅ | After RED model tests |
| 1.3 from_db_row mapping | Unit | — | ✅ | Null + present |
| 1.4 to_db_dict serialization | Unit | — | ✅ | |
| 1.5 migration 013 | Structural | ✅ | ✅ | File exists; applied live Supabase |
| 1.6 model suite | Unit | — | ✅ | 20/20 |
| 2.1 service metadata RED | Unit | ✅ | ✅ | create_ticket + create_ticket_channel |
| 2.2 create_ticket params | Unit | — | ✅ | |
| 2.3 create_ticket_channel params | Unit | — | ✅ | Forwarding test in remediation |
| 2.4 insert_ticket kwargs | Unit | — | ✅ | |
| 2.5 service+DB suite | Unit | — | ✅ | 178+ |
| 3.1 embed/i18n RED | Unit | ✅ | ✅ | `test_tickets_i18n.py` |
| 3.2 build_ticket_embed subject | Unit | — | ✅ | Title + details field + fallback |
| 3.3 locales en/es | Unit | — | ✅ | Modal + embed keys |
| 3.4 i18n suite | Unit | — | ✅ | 45+ |
| 4.1 modal flow RED | Integration | ✅ | ✅ | `test_tickets_cog.py` |
| 4.2 TicketIntakeModal | Integration | — | ✅ | Title required, desc optional |
| 4.3 CategorySelect send_modal | Integration | — | ✅ | First response = modal |
| 4.4 pin welcome | Integration | — | ✅ | + pin-failure resilience |
| 4.5 _create_ticket_after_modal helper | Integration | — | ✅ | |
| 4.6 cog suite | Integration | — | ✅ | 131+ |
| 5.1 full pytest | Full | — | ✅ | 1053 passed, 3 skipped |
| 5.2 success criteria | Full | — | ✅ | Spec scenarios covered |

## Corrective Remediation Evidence (`8ea158f`)

| Gap | Fix |
|-----|-----|
| create_ticket_channel metadata | `test_create_ticket_channel_forwards_subject_and_description` |
| title-only → description=None | `test_modal_submit_title_only_description_persists_none` |
| modal title category | `test_modal_title_includes_category_name` |
| pin HTTPException | `test_pin_failure_does_not_abort_ticket_creation` |
| ruff/mypy on source | split import; TextInput annotations; on_error *args |

## Live Ops

- Migration `013_ticket_intake_metadata` applied on Supabase `vozkcckiybebhcclrasa`
- Columns `ticket.subject`, `ticket.description` nullable

## Status

Ready for archive after verify PASS / PASS WITH WARNINGS.
