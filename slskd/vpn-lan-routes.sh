#!/bin/bash
set -euo pipefail
OPTIONS="$1"; GATEWAY="$2"; INTERFACE="$3"
[[ "$GATEWAY" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ && "$INTERFACE" =~ ^[a-zA-Z0-9_.:-]+$ ]]
while IFS= read -r subnet; do
    [[ "$subnet" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$ ]] || { echo 'Invalid LAN reply subnet.' >&2; exit 1; }
    ip -4 route replace "$subnet" via "$GATEWAY" dev "$INTERFACE"
done < <(jq -r '(.vpn_lan_subnets // ["192.168.0.0/16"])[]' "$OPTIONS")
