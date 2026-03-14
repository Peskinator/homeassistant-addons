#!/usr/bin/env sh
set -eu

DATA_ROOT="/srv/sftpgo"
STATE_DIR="${DATA_ROOT}/state"
FILES_DIR="${DATA_ROOT}/data"
BACKUPS_DIR="${DATA_ROOT}/backups"
ENV_DIR="${STATE_DIR}/env.d"

mkdir -p "$STATE_DIR" "$FILES_DIR" "$BACKUPS_DIR" "$ENV_DIR"

# The Home Assistant data mount can arrive owned by root. Fix only the
# top-level paths we manage, not the full user file tree.
chown sftpgo:sftpgo "$DATA_ROOT" "$STATE_DIR" "$FILES_DIR" "$BACKUPS_DIR" "$ENV_DIR"

export SFTPGO_DATA_PROVIDER__DRIVER="sqlite"
export SFTPGO_DATA_PROVIDER__NAME="/srv/sftpgo/state/sftpgo.db"
export SFTPGO_SFTPD__BINDINGS__0__PORT="2022"
export SFTPGO_HTTPD__BINDINGS__0__PORT="8080"
export SFTPGO_LOG_FILE_PATH=""
export SFTPGO_CONFIG_DIR="/srv/sftpgo/state"

exec gosu sftpgo sftpgo serve
