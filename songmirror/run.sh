#!/usr/bin/env sh
set -eu

# homeassistant.local can resolve to either IP family. Keep both listeners in
# one Uvicorn process so scheduled work is never duplicated.
exec uv run --no-sync python /dual_stack.py
