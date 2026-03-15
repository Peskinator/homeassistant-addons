# SFTPGo Home Assistant Add-on

This add-on wraps the official `drakkan/sftpgo` image with a small Home Assistant specific layer:

- persistent storage is mapped to `/srv/sftpgo`
- Home Assistant `media` is mounted at `/media`
- Home Assistant `share` is mounted at `/share`
- the SFTPGo database is stored at `/srv/sftpgo/state/sftpgo.db`
- generated SSH host keys are stored under `/srv/sftpgo/state`
- uploaded files live under `/srv/sftpgo/data`

## Exposed ports

- `80/tcp`: ACME HTTP-01 challenge
- `2022/tcp`: SFTP
- `8080/tcp`: admin and web UI
- `10080/tcp`: WebDAV
- `10443/tcp`: WebDAV over HTTPS
- `11443/tcp`: admin and web UI over HTTPS

## Persistence

This add-on maps Home Assistant's add-on data directory directly to `/srv/sftpgo`, so upgrades do not wipe users, configuration data, or uploaded files.

TLS certificates obtained by SFTPGo ACME are stored under `/srv/sftpgo/state/certs`.

## HTTPS WebDAV

To use SFTPGo-managed Let's Encrypt certificates for WebDAV:

1. Point your WebDAV hostname to your public IP using DNS only
2. Forward public port `80` to this add-on for the ACME HTTP-01 challenge
3. In SFTPGo WebAdmin, configure ACME for your hostname and select WebDAV as a target protocol
4. Configure WebDAV HTTPS to listen on port `10443`
5. Forward public port `10443` to this add-on for remote HTTPS WebDAV access

The same ACME-managed certificate can also be used for the SFTPGo web client and admin UI on port `11443`.

## Updating

To move to a newer upstream SFTPGo release:

1. Update `version` in `config.yaml`
2. Update `BUILD_SFTPGO_VERSION` in `Dockerfile`
