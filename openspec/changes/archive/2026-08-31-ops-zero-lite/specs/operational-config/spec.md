# Delta for operational-config

## ADDED Requirements

### Requirement: Docker log rotation documentation

The system MUST document bounded Docker JSON-file log rotation for both native Docker (`/etc/docker/daemon.json`: `log-driver=json-file`, `max-size=10m`, `max-file=5` ≈60 MB) and Pterodactyl panel queue (panel currently unbounded per #4711). Docs path `docs/ops/rotation.md` MUST include copy-paste `daemon.json` snippet, Pterodactyl egg/stack note, verification steps (`docker inspect --format`, log size check), and rollback (remove rotation keys + `systemctl reload docker`). Secrets MUST NOT be logged (existing token-never-logged requirement preserved).

#### Scenario: Docs contain rotation snippet

- GIVEN `docs/ops/rotation.md` is rendered
- WHEN inspected
- THEN it contains a valid `daemon.json` JSON block with `max-size` and `max-file`

#### Scenario: Pterodactyl unbounded flagged

- GIVEN docs are reviewed
- WHEN reading the Pterodactyl section
- THEN it calls out that panel queue is unbounded by default and requires host-level rotation

#### Scenario: Rollback is documented

- GIVEN rotation is applied
- WHEN operator follows rollback section
- THEN steps remove rotation keys and reload docker without data loss
