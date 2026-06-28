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
