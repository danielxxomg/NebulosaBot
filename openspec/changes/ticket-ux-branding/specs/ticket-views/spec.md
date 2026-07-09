# Delta for Ticket Views

## MODIFIED Requirements

### Requirement: Ticket actions view

The system MUST provide a per-ticket action view with close and claim buttons. Claim button MUST be gated by `@is_mod()` (solo mod). Close button MUST be gated by author OR mod. Non-eligible users clicking a gated button SHALL receive an ephemeral rejection message. Button labels MUST be resolved dynamically via `t()` at interaction time using `interaction.guild_id`. Close button click MUST trigger an ephemeral `ConfirmCancelView` confirmation dialog before proceeding. Claim on an already-claimed ticket MUST trigger an ephemeral transfer confirmation dialog before calling `transfer_ticket()`.

(Previously: close triggered immediate close; claim on claimed ticket was rejected outright)

#### Scenario: Action view render

- GIVEN a newly created ticket channel
- WHEN the ticket is opened
- THEN an embed with close and claim buttons is sent in the channel

#### Scenario: Mod clicks claim

- GIVEN an open ticket with the action view
- WHEN a mod clicks claim
- THEN the ticket claim flow is triggered

#### Scenario: Non-mod clicks claim rejected

- GIVEN an open ticket with the action view
- WHEN a non-mod user clicks claim
- THEN an ephemeral rejection message is sent

#### Scenario: Author clicks close

- GIVEN a ticket authored by userA
- WHEN userA clicks close
- THEN an ephemeral Confirm/Cancel confirmation dialog is shown

#### Scenario: Mod clicks close on another's ticket

- GIVEN a ticket authored by userA
- WHEN a mod (not userA) clicks close
- THEN an ephemeral Confirm/Cancel confirmation dialog is shown

#### Scenario: Non-author non-mod clicks close rejected

- GIVEN a ticket authored by userA
- WHEN userB (not author, not mod) clicks close
- THEN an ephemeral rejection message is sent

#### Scenario: Close from action view

- GIVEN an open ticket channel with the action view
- WHEN a staff member clicks close and confirms
- THEN the ticket close flow is triggered with countdown

#### Scenario: Claim from action view

- GIVEN an open ticket channel with the action view
- WHEN a staff member clicks claim
- THEN the ticket claim flow is triggered

#### Scenario: Localized action labels after restart

- GIVEN a Spanish guild with an active ticket
- WHEN the bot restarts and a user clicks Claim
- THEN the claim button label is resolved via `t('tickets.actions.claim_button', guild_id)` at interaction time

#### Scenario: Claim on already-claimed ticket shows transfer confirm

- GIVEN a ticket claimed by userA
- WHEN userB (mod) clicks Claim
- THEN an ephemeral transfer confirmation dialog is shown with "Transfer ticket from userA to userB?"

#### Scenario: Transfer confirm proceeds

- GIVEN a claim-on-claimed transfer confirmation dialog
- WHEN the mod clicks Confirm
- THEN `transfer_ticket()` is called and the ticket is reassigned to userB
