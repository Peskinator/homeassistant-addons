#!/bin/bash
# This runs only inside the slskd app's private network namespace.
set -euo pipefail
VPN_IP="$1"; VPN_PORT="$2"; VPN_PROTOCOL="$3"
[[ "$VPN_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ && "$VPN_PORT" =~ ^[0-9]+$ && "$VPN_PROTOCOL" =~ ^(udp|tcp)$ ]]
for tool in iptables ip6tables; do
    "$tool" -w -P OUTPUT DROP
    "$tool" -w -P INPUT DROP
    "$tool" -w -P FORWARD DROP
    "$tool" -w -F OUTPUT
    "$tool" -w -F INPUT
    "$tool" -w -A INPUT -i lo -j ACCEPT
    "$tool" -w -A OUTPUT -o lo -j ACCEPT
    "$tool" -w -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    # Public traffic can leave only through the VPN tunnel. Do not allow
    # established outbound flows on eth0: that could bypass the kill switch.
    "$tool" -w -A OUTPUT -o tun0 -j ACCEPT
    "$tool" -w -A INPUT -i tun0 -j ACCEPT
done
# Only the root-owned OpenVPN process can reach the VPN endpoint directly.
iptables -w -A OUTPUT -d "$VPN_IP" -p "$VPN_PROTOCOL" --dport "$VPN_PORT" -m owner --uid-owner 0 -j ACCEPT
# Allow authenticated web/API access from HA and the LAN, including IPv6.
for subnet in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16; do
    iptables -w -A INPUT -s "$subnet" -p tcp --dport 5030 -j ACCEPT
    iptables -w -A OUTPUT -d "$subnet" -p tcp --sport 5030 -m conntrack --ctstate ESTABLISHED -j ACCEPT
done
for subnet in fc00::/7 fe80::/10; do
    ip6tables -w -A INPUT -s "$subnet" -p tcp --dport 5030 -j ACCEPT
    ip6tables -w -A OUTPUT -d "$subnet" -p tcp --sport 5030 -m conntrack --ctstate ESTABLISHED -j ACCEPT
done
