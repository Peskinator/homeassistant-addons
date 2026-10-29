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

## PrivadoVPN for this app only

Premium PrivadoVPN supports manual OpenVPN profiles. Download one from your PrivadoVPN
dashboard and put it at `/addon_configs/<repository>_slskd/vpn/privado.ovpn`. Choose an
IPv4 UDP or TCP profile with one remote endpoint. Enter its manual OpenVPN username and
password in `vpn_username` and `vpn_password`, set `vpn_enabled: true`, then start the app.
The OpenVPN login is separate from your Soulseek login. Keep the profile and passwords
in app configuration; never put them in the public repository or paste them in logs.

The tunnel and firewall live inside slskd's own container network. They do not change HA,
Plex, SoulSync, the Windows PC or other apps' routes. NET_ADMIN and `/dev/net/tun` are used
only for this container's tunnel. With VPN enabled, missing configuration or a failed VPN
prevents slskd from starting. Actual IPv4 and IPv6 firewall rules allow public traffic
only through `tun0`; DNS uses that tunnel too. Web/API replies remain available on the
private HA/LAN network. A fatal OpenVPN exit stops slskd. The peer port on the host does
not bypass the VPN firewall; VPN-side incoming connectivity depends on your provider.

This mode is deliberately off by default for existing installations. Turn it on before
entering Soulseek credentials if you want to connect only through a VPN. The tests verify
traffic blocking before/after simulated tunnel loss, but your real VPN exit IP and a
disconnect test must also be verified after entering your private VPN configuration.

VPN startup now checks that the tunnel's public IP differs from the home connection,
stops OpenVPN to verify public IPv4/IPv6 access is blocked for the slskd account,
then reconnects and verifies the exit again before starting Soulseek. The result is
written to private app configuration `vpn/status.json`; the home public IP is never
written to that file. If verification fails, slskd remains stopped.

`vpn_lan_subnets` identifies browser/client LAN networks whose web replies should return
through HA's original gateway (default `192.168.0.0/16`). This prevents VPN default
routes from breaking local web access. It does not permit arbitrary non-VPN outbound
traffic: the firewall still permits only established port-5030 replies to private LAN
addresses. If your LAN uses a different range, set it explicitly, avoiding VPN subnet overlap.
