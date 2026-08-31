# Log Rotation — Docker daemon.json

~60 MB cap (10 MB × 5 backups + active).

## daemon.json

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "5"
  }
}
```

Place at `/etc/docker/daemon.json` (merge with existing keys), then:

```bash
sudo systemctl reload docker
# or: sudo systemctl restart docker
docker inspect --format='{{json .HostConfig.LogConfig}}' <container>
```

Expected: `{"Type":"json-file","Config":{"max-file":"5","max-size":"10m"}}`

## Pterodactyl

Pterodactyl's Docker containers are **unbounded** by default (#4711). Apply the
daemon.json above on the host so every container inherits the cap.

## Secrets

Backup cron uses `SUPABASE_DB_URL` (pooler `:5432` form, Supabase session pooler) —
same fallback as `bot/services/live_catalog.py:101`. Never log it. Sentry uses
`SENTRY_DSN` (optional, env-gated).

## Rollback

Remove the `log-driver` / `log-opts` keys from `daemon.json` and reload:

```bash
sudo systemctl reload docker
```
