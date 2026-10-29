#!/bin/bash
set -euo pipefail
umask 077
PROFILE=/config/vpn/privado.ovpn
OPTIONS=/data/options.json
install -d -m 700 /config/vpn
printf '{"ready":false,"phase":"starting"}\n' > /config/vpn/status.json
[[ -f "$PROFILE" ]] || { echo 'VPN enabled: add the PrivadoVPN OpenVPN profile to app config vpn/privado.ovpn. slskd remains stopped.' >&2; exit 1; }
jq -e '(.vpn_username | length)>0 and (.vpn_password | length)>0 and ([.vpn_username,.vpn_password] | all(test("[\r\n]")|not))' "$OPTIONS" >/dev/null || { echo 'VPN enabled: enter the manual OpenVPN credentials in HA. slskd remains stopped.' >&2; exit 1; }
[[ -c /dev/net/tun ]] || { echo 'VPN requires /dev/net/tun; slskd remains stopped.' >&2; exit 1; }
sed 's/\r$//' "$PROFILE" > /run/ha-privado.source
PROFILE=/run/ha-privado.source
# A Privado-generated profile normally contains one remote. Multiple remote
# profiles are refused so the firewall allowlist always matches the endpoint.
mapfile -t REMOTES < <(awk '$1=="remote" {print $2" "$3}' "$PROFILE")
[[ "${#REMOTES[@]}" == 1 ]] || { echo 'Use a PrivadoVPN profile with exactly one remote endpoint.' >&2; exit 1; }
read -r VPN_HOST VPN_PORT <<< "${REMOTES[0]}"
VPN_PORT="${VPN_PORT:-1194}"
VPN_PROTOCOL="$(awk '$1=="proto"{print $2;exit}' "$PROFILE")"
case "$VPN_PROTOCOL" in udp|udp4|'') VPN_PROTOCOL=udp;; tcp|tcp-client|tcp4|tcp4-client) VPN_PROTOCOL=tcp;; *) echo 'Use an IPv4 OpenVPN UDP or TCP profile.' >&2; exit 1;; esac
[[ "$VPN_PORT" =~ ^[0-9]+$ && "$VPN_HOST" =~ ^[a-zA-Z0-9._-]+$ ]] || exit 1
VPN_IP="$(getent ahostsv4 "$VPN_HOST" | awk '!found {print $1; found=1}')"
[[ -n "$VPN_IP" ]] || { echo 'Cannot resolve the PrivadoVPN endpoint; slskd remains stopped.' >&2; exit 1; }
# Keep browser replies on the original LAN path after redirect-gateway adds
# its tunnel routes. The firewall still allows only established web replies.
read -r ORIGINAL_GATEWAY ORIGINAL_INTERFACE < <(ip -4 route show default | awk '$1=="default" {print $3" "$5;exit}')
/bin/bash /ha-vpn-lan-routes.sh "$OPTIONS" "$ORIGINAL_GATEWAY" "$ORIGINAL_INTERFACE"
# Compare addresses in memory only; never record the home public IP.
HOME_TRACE="$(wget -4 -qO- -T 10 -t 1 https://1.1.1.1/cdn-cgi/trace)" || { echo 'Cannot obtain the baseline address; slskd remains stopped.' >&2; exit 1; }
HOME_IP="$(printf '%s\n' "$HOME_TRACE" | awk -F= '$1=="ip"{print $2}')"
[[ "$HOME_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || exit 1
unset HOME_TRACE
# Resolve only the VPN endpoint before enabling the firewall. Soulseek has
# not started. All subsequent DNS, peer and server traffic must use tun0.
/bin/bash /ha-vpn-firewall.sh "$VPN_IP" "$VPN_PORT" "$VPN_PROTOCOL"
# Ignore executable/logging directives from a downloaded VPN profile. The
# fixed CLI options below control authentication, routing and script access.
awk '
  $1 ~ /^(remote|proto|auth-user-pass|daemon|log|log-append|syslog|up|down|route-up|route-pre-down|ipchange|plugin|script-security|management|management-client|config|cd|chroot|user|group)$/ {next}
  {print}
' "$PROFILE" > /run/ha-privado.ovpn
jq -r '.vpn_username,.vpn_password' "$OPTIONS" > /run/ha-privado.auth
chmod 600 /run/ha-privado.ovpn /run/ha-privado.auth
VPN_PID=''; APP_PID=''
cleanup() {
    trap - EXIT INT TERM
    [[ -z "$APP_PID" ]] || kill -TERM "$APP_PID" 2>/dev/null || true
    [[ -z "$VPN_PID" ]] || kill -TERM "$VPN_PID" 2>/dev/null || true
    [[ -z "$APP_PID" ]] || wait "$APP_PID" 2>/dev/null || true
    [[ -z "$VPN_PID" ]] || wait "$VPN_PID" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' INT TERM
OPENVPN_PROTO=udp4
[[ "$VPN_PROTOCOL" != tcp ]] || OPENVPN_PROTO=tcp4-client
connect_vpn() {
    openvpn --config /run/ha-privado.ovpn --remote "$VPN_IP" "$VPN_PORT" --proto "$OPENVPN_PROTO" \
        --dev tun0 --auth-user-pass /run/ha-privado.auth --auth-nocache --script-security 1 \
        --redirect-gateway def1 --ping 10 --ping-restart 30 --verb 1 &
    VPN_PID=$!
    for ((attempt=0; attempt<90; attempt++)); do
        kill -0 "$VPN_PID" 2>/dev/null || { echo 'OpenVPN stopped; slskd was not started.' >&2; return 1; }
        if ip -4 address show dev tun0 2>/dev/null | grep -q 'inet ' && ip -4 route get 1.1.1.1 | grep -q 'dev tun0'; then
            return 0
        fi
        sleep 1
    done
    echo 'VPN was not ready in 90 seconds; slskd was not started.' >&2
    return 1
}
check_exit() {
    local trace
    trace="$(gosu "$PUID:$PGID" wget -4 -qO- -T 10 -t 1 https://1.1.1.1/cdn-cgi/trace)" || return 1
    EXIT_IP="$(printf '%s\n' "$trace" | awk -F= '$1=="ip"{print $2}')"
    EXIT_COUNTRY="$(printf '%s\n' "$trace" | awk -F= '$1=="loc"{print $2}')"
    [[ "$EXIT_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ && "$EXIT_IP" != "$HOME_IP" ]]
}
connect_vpn
check_exit || { echo 'VPN exit address could not be verified; slskd remains stopped.' >&2; exit 1; }
# Perform a live disconnect check before Soulseek ever starts. The same
# non-root account must be unable to reach the internet with OpenVPN stopped.
kill -TERM "$VPN_PID"
wait "$VPN_PID" || true
VPN_PID=''
if gosu "$PUID:$PGID" wget -4 -qO /dev/null -T 3 -t 1 https://1.1.1.1/cdn-cgi/trace; then
    echo 'IPv4 kill-switch verification failed; slskd remains stopped.' >&2
    exit 1
fi
if gosu "$PUID:$PGID" wget -6 -qO /dev/null -T 3 -t 1 'https://[2606:4700:4700::1111]/cdn-cgi/trace'; then
    echo 'IPv6 kill-switch verification failed; slskd remains stopped.' >&2
    exit 1
fi
connect_vpn
check_exit || { echo 'VPN reconnection could not be verified; slskd remains stopped.' >&2; exit 1; }
# Use a public resolver through the tunnel, rather than Docker's host resolver.
printf 'nameserver 9.9.9.9\noptions timeout:2 attempts:2\n' > /etc/resolv.conf
export EXIT_IP EXIT_COUNTRY
jq -n '{ready:true,phase:"verified",exit_ip:env.EXIT_IP,exit_country:env.EXIT_COUNTRY,
        home_ip_different:true,live_disconnect_ipv4_blocked:true,live_disconnect_ipv6_blocked:true,
        checked_at:(now|todate)}' > /config/vpn/status.json.tmp
mv /config/vpn/status.json.tmp /config/vpn/status.json
unset HOME_IP EXIT_IP EXIT_COUNTRY
echo 'Live VPN exit and IPv4/IPv6 disconnect checks passed; VPN reconnected.'
echo 'VPN route is ready; starting slskd behind the IPv4/IPv6 kill switch.'
/entrypoint.sh "$@" &
APP_PID=$!
# A fatal VPN process exit also stops the app. Reconnection inside OpenVPN
# remains protected because non-tunnel public traffic is always blocked.
wait -n "$VPN_PID" "$APP_PID"
