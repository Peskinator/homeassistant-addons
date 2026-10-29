# Changelog

## 0.26.2-4

- Use an HA OS-compatible VPN endpoint rule without the optional xt_owner kernel module.
- Verify a changed VPN exit IP and perform a live disconnect/reconnect test before starting Soulseek.
- Write private VPN verification status without recording the home public IP.

## 0.26.2-3

- Add optional app-only PrivadoVPN OpenVPN routing with an IPv4/IPv6 kill switch.
- Keep slskd stopped until VPN credentials, profile and tunnel route are ready.

## 0.26.2-2

- Allow authenticated SoulSync API connections over both HA app-network IPv4 and IPv6.

## 0.26.2-1

- Package stable slskd with persistent private state, API key, web password and JWT key.
- Match SoulSync's non-root account and shared download folder.
- Share only explicitly selected directories; keep media mounted read-only.
- Check stable upstream releases daily and test persistence before publishing updates.
