# Delta for Transcript Service

## ADDED Requirements

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
