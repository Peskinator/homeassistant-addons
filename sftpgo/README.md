# SFTPGo Home Assistant Add-on

This add-on wraps the official `drakkan/sftpgo` image with a small Home Assistant specific layer:

- persistent storage is mapped to `/srv/sftpgo`
- Home Assistant `media` is mounted at `/media`
- Home Assistant `share` is mounted at `/share`
- the SFTPGo database is stored at `/srv/sftpgo/state/sftpgo.db`
- generated SSH host keys are stored under `/srv/sftpgo/state`
- uploaded files live under `/srv/sftpgo/data`

## Exposed ports

- `2022/tcp`: SFTP
- `8080/tcp`: admin and web UI
- `10080/tcp`: WebDAV

## Persistence

This add-on maps Home Assistant's add-on data directory directly to `/srv/sftpgo`, so upgrades do not wipe users, configuration data, or uploaded files.

## Updating

To move to a newer upstream SFTPGo release:

1. Update `version` in `config.yaml`
2. Update `BUILD_SFTPGO_VERSION` in `Dockerfile`
