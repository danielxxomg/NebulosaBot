# Transcript Service Specification

## Purpose

Define self-contained HTML transcript generation from ticket channel history.

## Requirements

### Requirement: HTML generation

The system MUST generate a self-contained HTML file from channel message history.

#### Scenario: Generate transcript

- GIVEN a ticket channel with messages, attachments, and embeds
- WHEN the ticket is closed
- THEN an HTML file containing the full message history is produced with inline CSS

#### Scenario: Cap message count

- GIVEN a channel with more than 5000 messages
- WHEN the transcript is generated
- THEN only the most recent 5000 messages are included

### Requirement: Transcript upload

The system MUST upload the generated transcript to the configured log channel.

#### Scenario: Successful upload

- GIVEN a generated HTML transcript and a configured log channel
- WHEN the transcript upload runs
- THEN the file is sent to the log channel and the returned URL is stored in `transcriptUrl`

#### Scenario: Log channel missing

- GIVEN no log channel configured
- WHEN a transcript upload is attempted
- THEN the close flow still completes and the transcript URL remains null

### Requirement: Transcript content

The system SHOULD include message author, timestamp, content, attachments, and embeds in the transcript.

#### Scenario: Rich content

- GIVEN messages with images and embeds
- WHEN the transcript is generated
- THEN attachment links and embed fields are rendered in the HTML

### Requirement: Triple-path transcript delivery

On ticket close, the generated HTML transcript MUST be delivered through three independent paths: (1) sent as an HTML file DM to the ticket creator, (2) uploaded to the PRIVATE Storage bucket with a 30-day TTL aligned to the data-retention purge, and (3) posted to the configured log channel (existing behavior). Paths MUST be best-effort and independent: failure of any single path MUST NOT abort the close flow or block the remaining paths. The persisted `transcriptUrl` MUST reference the durable Storage copy (not the expiring Discord CDN attachment URL).

#### Scenario: Creator receives DM copy

- GIVEN a ticket closes with messages
- WHEN triple-path delivery runs
- THEN the creator receives the HTML transcript by DM

#### Scenario: Private Storage copy with 30d TTL

- GIVEN a transcript is generated
- WHEN the Storage upload runs
- THEN the object is written to the PRIVATE bucket (not publicly readable) carrying metadata that expires it after 30 days

#### Scenario: Log channel still receives the file

- GIVEN a configured log channel
- WHEN delivery completes
- THEN the log channel receives the transcript file exactly as before

#### Scenario: Creator DMs closed does not break others

- GIVEN the creator has DMs disabled
- WHEN triple-path delivery runs
- THEN the DM path fails gracefully (logged), and both the Storage copy and the log-channel post still succeed

#### Scenario: Storage TTL aligns with retention purge

- GIVEN Storage objects carry 30-day expiry metadata and the retention job purges expired objects
- WHEN 30 days elapse after close
- THEN the Storage copy is removed by the same retention schedule — no orphaned transcripts outlive the window

### Requirement: Log-channel-missing behavior preserved

When no log channel is configured, the close flow MUST still complete; the Storage copy and creator DM remain the delivered paths and the log post is skipped without error.

#### Scenario: No log channel skips only that path

- GIVEN no log channel configured
- WHEN a ticket closes
- THEN close succeeds, DM + Storage copies are attempted, and no error surfaces from the skipped log post

<!-- BEGIN DELTA: ops-zero-lite (transcript-service) -->
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

<!-- END DELTA: ops-zero-lite (transcript-service) -->
