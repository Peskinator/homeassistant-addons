# Maintainerr Home Assistant Add-on

This add-on wraps the official `ghcr.io/maintainerr/maintainerr` image and keeps Maintainerr's real upstream data directory persistent.

## Exposed port

- `6246/tcp`: Maintainerr web UI

## Persistence

Current Maintainerr stores its database and logs under `/opt/data`.

This add-on maps Home Assistant's add-on data directory directly to `/opt/data`, which keeps:

- `maintainerr.sqlite`
- `logs/`

across restarts and updates.

## Optional mounts

The add-on also mounts:

- `/media`
- `/share`

## Updating

To move to a newer upstream Maintainerr release:

1. Update `version` in `config.yaml`
