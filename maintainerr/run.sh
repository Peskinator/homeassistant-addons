#!/usr/bin/env sh
set -e

echo "[ha-addon] Starting Maintainerr (HA persistence wrapper)..."

PERSIST="/data"
SRC="/opt/data"

# Ensure base dirs exist
mkdir -p "$PERSIST" "$SRC"

# Prepare persistent DB and logs
mkdir -p "$PERSIST/logs"
touch "$PERSIST/maintainerr.sqlite" || true

# Fix permissions so the non-root app user can write to /data
if id node >/dev/null 2>&1; then
  chown -R node:node "$PERSIST" || true
fi

# Symlink upstream data paths to our persistent /data
ln -snf "$PERSIST/maintainerr.sqlite" "$SRC/maintainerr.sqlite"
ln -snf "$PERSIST/logs" "$SRC/logs"

echo "[ha-addon] Using $PERSIST for DB/logs (linked into $SRC)"

# Start the upstream supervisor in the foreground (PID 1 child)
exec /usr/bin/supervisord -n -c /etc/supervisord.conf
