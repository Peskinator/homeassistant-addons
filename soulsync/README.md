# SoulSync Home Assistant App

Music requests, discovery, playlists, downloads and library management from
[SoulSync](https://github.com/Nezreka/SoulSync), packaged for Home Assistant.

## Install and connect

1. Refresh the Home Assistant App Store and install **SoulSync** from
   `https://github.com/Peskinator/homeassistant-addons`.
2. Start the app, then select **Open Web UI** (default port **8008**).
3. Complete SoulSync's setup and connect Plex, Prowlarr and your download clients.
   Use their reachable LAN URLs; `localhost` inside SoulSync means this app.
4. Point a Plex music library at the **same physical music folder** described below.

SoulSync is not bundled with slskd, a torrent client or a Usenet client. Connect
the services you already run. Enable ports 8888/8889 in the app's Network panel
only when the Spotify/Tidal callback flow needs them. If you change the host
callback port, configure the provider redirect URL accordingly.

## Persistent storage

| Data | SoulSync sees | Persistent location |
| --- | --- | --- |
| Settings and provider token files | `/app/config` | private app `/data/config` |
| SQLite databases, encryption key, session identity | `/app/data` | private app `/data/data` |
| Avatars, artwork, album staging and other storage | `/app/storage` | private app `/data/storage` |
| Logs, custom scripts and tool caches | `/app/logs`, `/app/scripts`, home/cache | private app `/data` |
| Shared music library | `/app/Transfer` | `/media/soulsync/music` |
| Separate profile libraries | `/app/libraries` | `/media/soulsync/libraries` |
| Incoming downloads | `/app/downloads` | `/share/soulsync/downloads` |
| Manual import inbox | `/app/Staging` | `/share/soulsync/inbox` |
| Podcasts, audiobooks, music videos, samples | matching `/app` folders | corresponding `/media/soulsync` folders |

The first three app options can relocate the media root, download folder and
inbox **before first use**. Changing one later does not migrate existing files:
move them separately and update your Plex/download-client paths as necessary.
Paths must be below `/media` or `/share`, and the three roots must not overlap.
PUID/PGID control the runtime account (default `1000:1000`); UMASK defaults to `002`.
No entire shared media/download tree is recursively re-owned.

**Do not use `/app/database` for data.** It contains SoulSync's Python code.
The wrapper intentionally removes upstream's anonymous Docker volumes and
attaches the paths above to HA's real persistent mounts. Updates/rebuilds keep
the same data. Configuration is seeded only on first use, never reset on boot.
Keep any additional paths configured inside SoulSync under `/data`, `/media`,
or `/share`; arbitrary container-only paths are disposable. Optional video
features should use folders under `/media/soulsync`, if enabled.

## Backups

Normal Home Assistant app backups include private `/data`. The app uses a
**cold backup**, so SQLite writers stop while its state is captured.
Music and inbox/download files in `/media` and `/share` need those folders
selected in your HA backup or another media backup. An app-only backup does
not contain the shared media collection. Uninstalling an app can delete its
private data: take a backup before uninstalling. Reinstall is not an update.

## Updates

The daily **Sync stable SoulSync releases** action checks official stable GitHub
releases and their versioned GHCR images. It pins the image's immutable digest,
increments this app's version, builds it, and runs the container replacement
and persistence checks **before committing the update to this repository**.
Prereleases, development tags and unversioned `latest` pushes are not followed.
Home Assistant sees the changed app version after its store refresh. Automatic
installation depends on your HA automatic-update setting.

The app follows this repo's build-on-install convention. Only `amd64` is
advertised until an ARM64 image has been validated.

## Access and uploads

This app opens directly on port 8008; it does not bypass SoulSync authentication.
Enable SoulSync login/Plex login before sharing access with friends. Browser
audio uploads in upstream SoulSync 3.6.0 are **administrator-only**.
Friends can place albums in a separately shared inbox; an administrator imports
them. The public repository and update workflows never receive your app data,
provider credentials, media, or Home Assistant credentials.
