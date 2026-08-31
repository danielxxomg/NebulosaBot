# Delta for transcript-service

## ADDED Requirements

### Requirement: Non-blocking HTML assembly [PRESERVED]

The system MUST preserve non-blocking HTML assembly in `TranscriptService.generate()` (verified: `bot/services/transcript_service.py:134` dispatches `_build_html` via `asyncio.to_thread`; `_build_html` at `:353` is sync-pure). `generate()` MUST NOT block the event loop during HTML assembly. Regression guard: `tests/test_transcript_service.py:293 test_generate_offloads_build_html_to_thread` MUST stay green.

#### Scenario: Generate dispatches to worker thread

- GIVEN a ticket channel with messages (`bot/services/transcript_service.py:96 generate`)
- WHEN `generate` is awaited
- THEN `_build_html` executes inside `asyncio.to_thread` (loop not blocked)

#### Scenario: Sync _build_html stays testable

- GIVEN a list of `discord.Message` and localized strings
- WHEN `TranscriptService._build_html(messages, header_title, no_content_text)` is called synchronously
- THEN it returns HTML string without awaiting or I/O

#### Scenario: No blocking I/O in async path

- GIVEN `generate` under `PYTHONASYNCIODEBUG=1`
- WHEN transcript generation runs
- THEN no blocking-call warning surfaces and loop time stays bounded
