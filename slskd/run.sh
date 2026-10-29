#!/bin/bash
set -euo pipefail
umask 077
for folder in /data /config /media /share; do
    mountpoint -q "$folder" || { echo "Missing persistent mount: $folder" >&2; exit 1; }
done
OPTIONS=/data/options.json
jq -e '(.puid >= 1) and (.pgid >= 1) and (.shared_dirs | type == "array")' "$OPTIONS" >/dev/null
export PUID="$(jq -r '.puid' "$OPTIONS")"
export PGID="$(jq -r '.pgid' "$OPTIONS")"
export SLSKD_UMASK=0002
export SLSKD_APP_DIR=/data
export SLSKD_CONFIG=/data/slskd.yml
export DOTNET_BUNDLE_EXTRACT_BASE_DIR=/data/cache/dotnet
export HOME=/data/home

path_under_mount() {
    local path="$1" resolved
    [[ "$path" == /* && "$path" != *';'* && "$path" != *$'\n'* ]] || return 1
    resolved="$(realpath -m -- "$path")"
    [[ "$resolved" == /media/* || "$resolved" == /share/* ]] || return 1
    [[ "$resolved" == "$path" ]] || return 1
}
DOWNLOADS="$(jq -r '.downloads_path' "$OPTIONS")"
INCOMPLETE="$(jq -r '.incomplete_path' "$OPTIONS")"
for path in "$DOWNLOADS" "$INCOMPLETE"; do
    path_under_mount "$path" && [[ "$path" == /share/* ]] || { echo 'Downloads must be below /share' >&2; exit 1; }
done
[[ "$DOWNLOADS/" != "$INCOMPLETE/"* && "$INCOMPLETE/" != "$DOWNLOADS/"* ]] || { echo 'Download folders must not overlap' >&2; exit 1; }
while IFS= read -r path; do
    path_under_mount "$path" || { echo 'Shared folders must be below /media or /share' >&2; exit 1; }
    [[ "$path/" != "$DOWNLOADS/"* && "$DOWNLOADS/" != "$path/"* && "$path/" != "$INCOMPLETE/"* && "$INCOMPLETE/" != "$path/"* ]] || { echo 'Shared folders must not contain downloads or incomplete files' >&2; exit 1; }
    if [[ "$path" == /share/* && ! -d "$path" ]]; then install -d -m 755 -- "$path"; fi
    [[ -d "$path" ]] || { echo 'Create the selected shared folder before starting slskd' >&2; exit 1; }
done < <(jq -r '.shared_dirs[]' "$OPTIONS")

# Directory nodes only: never walk or change an existing media collection.
chown "$PUID:$PGID" "$SLSKD_APP_DIR"
install -d -o "$PUID" -g "$PGID" -m 700 "$DOTNET_BUNDLE_EXTRACT_BASE_DIR" "$HOME"
install -d -o "$PUID" -g "$PGID" -m 775 "$DOWNLOADS" "$INCOMPLETE"
# HA restores may create private state as root. Repair only private app trees;
# never recursively change shared downloads or the media mount.
while IFS= read -r -d '' private; do
    if [[ "$(stat -c '%u:%g' "$private")" != "$PUID:$PGID" ]]; then
        chown -R -P "$PUID:$PGID" "$private"
    fi
done < <(find /data -mindepth 1 -maxdepth 1 -type d -print0)
if [[ ! -e /config/connection.json ]]; then
    key="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
    password="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
    jwt="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
    # Standard input keeps generated credentials out of process arguments/logs.
    printf '%s\n%s\n%s\n' "$key" "$password" "$jwt" | jq -Rn '[inputs] | {api_key:.[0],web_password:.[1],jwt_key:.[2]}' > /config/connection.json.tmp
    chmod 600 /config/connection.json.tmp
    mv /config/connection.json.tmp /config/connection.json
    unset key password jwt
fi
jq -e '(.api_key|length)>=16 and (.web_password|length)>=16 and (.jwt_key|length)>=16' /config/connection.json >/dev/null
# JSON is valid YAML. Managed options are regenerated, credentials are not.
jq -n --slurpfile options "$OPTIONS" --slurpfile credentials /config/connection.json '
  $options[0] as $o | $credentials[0] as $c |
  {flags:{no_connect:($o.soulseek_username=="" or $o.soulseek_password==""),no_version_check:true},
   remote_configuration:false,remote_file_management:false,
   soulseek:{username:(if $o.soulseek_username=="" then "configure_in_home_assistant" else $o.soulseek_username end),
             password:(if $o.soulseek_password=="" then "configure_in_home_assistant" else $o.soulseek_password end),listen_port:50300},
   directories:{downloads:$o.downloads_path,incomplete:$o.incomplete_path},
   shares:{directories:$o.shared_dirs},
   transfers:{download:{destination:{permissions:{mode:"664"}}}},
   web:{port:5030,https:{disabled:true},authentication:{disabled:false,username:$o.web_username,
        password:(if $o.web_password=="" then $c.web_password else $o.web_password end),
        jwt:{key:$c.jwt_key},api_keys:{soulsync:{key:$c.api_key,role:"ReadWrite",cidr:"172.30.32.0/23,127.0.0.0/8,::1/128"}}}}}
' > /data/slskd.yml.tmp
chown "$PUID:$PGID" /data/slskd.yml.tmp
chmod 600 /data/slskd.yml.tmp
mv /data/slskd.yml.tmp "$SLSKD_CONFIG"
if [[ "$(jq -r '.soulseek_username' "$OPTIONS")" == "" || "$(jq -r '.soulseek_password' "$OPTIONS")" == "" ]]; then
    echo 'slskd is ready. Enter Soulseek credentials in the Home Assistant app Configuration tab, then restart.'
fi
echo "Persistent slskd state: /data; downloads: $DOWNLOADS; runtime: $PUID:$PGID"
exec /entrypoint.sh "$@"
