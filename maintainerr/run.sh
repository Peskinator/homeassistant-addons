#!/usr/bin/env sh
set -eu

DATA_DIR="/opt/data"

mkdir -p "$DATA_DIR" "$DATA_DIR/logs"

# Home Assistant mounts can arrive owned by root. Maintainerr runs as node
# upstream, so fix the mounted data path before dropping privileges.
chown -R node:node "$DATA_DIR"

exec su-exec node /opt/app/start.sh
