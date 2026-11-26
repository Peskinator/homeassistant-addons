#!/usr/bin/env sh
set -eu

# Supervisor bind-mounts /data, which can contain root-owned state from older images.
# Keep Supervisor's options file and symlinks under their existing ownership.
find /data -xdev -uid 0 \( -type d -o -type f \) ! -path /data/options.json \
    -exec chown -h 1000:1000 {} +

# One non-root Uvicorn process serves both address families and runs the scheduler.
exec setpriv --reuid=1000 --regid=1000 --clear-groups /app/.venv/bin/python /dual_stack.py
