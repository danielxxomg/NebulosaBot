# Ticket Service Specification

## Purpose

Define ticket lifecycle management: creation, claim, close, and automatic closure after inactivity.

## Requirements

### Requirement: Ticket creation

The system MUST create a new ticket channel with a sequential ticket number per guild.

#### Scenario: Successful creation

- GIVEN a guild with ticket category configured
- WHEN a user opens a ticket
- THEN a channel is created under the ticket category and a Ticket row is inserted with status `open`

#### Scenario: Sequential numbering

- GIVEN the highest existing ticket number in the guild is 12
- WHEN a new ticket is created
- THEN the new ticket number is 13

#### Scenario: Race condition retry

- GIVEN two tickets are created simultaneously and both read ticket number 13
- WHEN the first insert succeeds
- THEN the second attempt MUST retry with ticket number 14 within 3 attempts

### Requirement: Ticket claim

The system MUST allow staff to claim an open ticket.

#### Scenario: Staff claims ticket

- GIVEN an open ticket
- WHEN a staff member clicks the claim button
- THEN the ticket status becomes `claimed` and `claimedBy` is set to the staff user ID

#### Scenario: Already claimed

- GIVEN a ticket already claimed by another staff member
- WHEN a staff member clicks claim
- THEN the action is rejected and the existing claim is preserved

### Requirement: Ticket close

The system MUST close a ticket, generate a transcript, and delete the channel.

#### Scenario: Close with transcript

- GIVEN an open ticket with messages
- WHEN the close action is triggered
- THEN a transcript is generated, uploaded to the log channel, the Ticket row status becomes `closed`, and the channel is deleted

#### Scenario: Close unclaimed ticket

- GIVEN an unclaimed open ticket
- WHEN close is triggered
- THEN the ticket is closed normally and `claimedBy` remains null

### Requirement: Auto-close stale tickets

The system MUST automatically close tickets that have been inactive for 48 hours.

#### Scenario: Stale ticket

- GIVEN a ticket with `lastActivity` older than 48 hours
- WHEN the hourly auto-close task runs
- THEN the ticket is closed silently without warning and the channel is deleted

#### Scenario: Active ticket

- GIVEN a ticket with `lastActivity` within 48 hours
- WHEN the hourly auto-close task runs
- THEN the ticket remains open
