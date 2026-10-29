# slskd Home Assistant App

[slskd](https://github.com/slskd/slskd) connects SoulSync to the Soulseek network.

1. Install this app and enter your Soulseek username/password in its Configuration tab.
   Soulseek creates an unused username on first successful login. Use a separate account
   if another Soulseek client is already logged in with your usual account.
2. Set a Web UI password in that same tab, then start the app. Open Web UI uses port 5030.
3. Choose only folders you intend to share in `shared_dirs`. The default is the dedicated
   `/share/slskd/shared` folder. To use a folder on `/media`, create it first through Samba.
   Media is mounted read-only; slskd cannot modify your existing music library.
4. Connect SoulSync to `http://<app-hostname>:5030`. The generated API key is in
   `/addon_configs/<repository>_slskd/connection.json`, accessible through Samba.
   It is restricted to HA's app network and localhost and permits read/write API calls.

## Downloads and permissions

Completed downloads go to `/share/soulsync/downloads`, the same physical folder as
SoulSync's `/app/downloads` with the default SoulSync app options. Incomplete files use
the separate `/share/soulsync/incomplete` folder. Both services should use the same
PUID/PGID (default 1000:1000). The startup script changes only these directory nodes,
never recursively changes the shared media collection. Configure the final music library
inside SoulSync; slskd does not write directly into that library.

Only `shared_dirs` are published to other Soulseek users. Download and incomplete
folders cannot overlap shared folders. An empty dedicated folder shares no music until
you deliberately add files to it.

## Persistence and backups

Databases, search/transfer history, logs and runtime settings live in private `/data`.
Generated API, web password and session-signing key live in persistent app `/config`.
`connection.json` is created once and survives restarts, rebuilds and app updates. A blank
Web UI password option uses its generated password; set your own password in HA for convenience.
Blank Soulseek credentials keep the network connection disabled while setup is unfinished.
Never commit `connection.json` or runtime settings to a source repository.

App backups use cold mode and include private app state and app configuration. Shared
downloads and music require separate `/share` and `/media` backup selection. Updating
preserves state; uninstalling can remove it. Moving a configured folder does not move files.

## Network and updates

Only forward peer TCP port 50300 on your router to the HA machine if you want incoming
Soulseek connections. Web port 5030 is for your LAN; it has its own authentication.
The daily workflow follows official stable releases and pinned versioned GHCR images,
then builds and tests replacement/backup persistence before bumping the HA app version.
Only amd64 is advertised until other architectures have been tested.
