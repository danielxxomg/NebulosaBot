# Delta for Close Confirmation

## ADDED Requirements

### Requirement: Visibility reconciliation — ephemeral dialog, durable outcome

The close-confirmation interaction surface MUST remain fully ephemeral: the prompt, Cancel feedback, timeout feedback, and unauthorized-click rejection are each visible only to the interacting user. Only the durable close record (transcript and log routing outside the closing channel) is governed by permanence standards; this capability introduces NO permanence change to the dialog itself. Dismissal of the ephemeral message SHALL still be treated as cancel.

#### Scenario: Dialog surface stays ephemeral

- GIVEN the close confirmation flow runs
- WHEN prompt, cancel, timeout, or rejection events occur
- THEN every one of those responses is ephemeral

#### Scenario: Durable record is independent of the dialog

- GIVEN a confirmed close completed
- WHEN the durable close record is produced
- THEN its visibility follows the transcript/logging standards, not the dialog's ephemerality
