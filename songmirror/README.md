# SongMirror Home Assistant App

SongMirror synchronizes playlists across music providers and archives playlist
metadata. It uses the upstream image, pinned to an immutable digest by this
repository's daily updater.

## Persistent data

SongMirror keeps its account connections, caches, sync definitions, and
scheduled playlist archives in `/data`. Home Assistant persists this directory
and includes it in normal app backups.

In SongMirror, configure scheduled archives at **Settings → Playlist archive**.
Snapshots are stored at `/data/playlist_backups/` and never enter this public
repository.

## Updates

The `sync-songmirror-upstream` GitHub Action checks the upstream `latest`
manifest daily. When its immutable digest changes, it pins that digest, bumps
the app patch version, builds the wrapper to validate it, and publishes the
change. With Home Assistant automatic updates enabled, the new app version is
then installed without manual intervention.

Because SongMirror does not currently publish GitHub releases, this policy
tracks the upstream `latest` image after a successful wrapper build.
