#!/usr/bin/env bash
set -euo pipefail
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
AZAN_ROOT=${AZAN_INSTALL_ROOT:-"$HOME/digital-azan"}
AZAN_ROOT=$(realpath -e -- "$AZAN_ROOT")
exec 9>"$AZAN_ROOT/shared/deploy.lock"
flock -n 9 || { echo 'Another deployment is in progress.'; exit 1; }
PREVIOUS=$(cat -- "$AZAN_ROOT/shared/previous-release")
PREVIOUS=$(realpath -e -- "$PREVIOUS")
case "$PREVIOUS/" in "$AZAN_ROOT/releases/"*) ;; *) echo 'Invalid previous release path'; exit 1 ;; esac
[[ -x "$PREVIOUS/.venv/bin/python" ]] || exit 1
systemctl --user stop digital-azan.service
export AZAN_CONFIG="$AZAN_ROOT/shared/config.yaml" AZAN_DATA_DIR="$AZAN_ROOT/shared/data"
cd -- "$PREVIOUS"
# Refuses incompatible newer database schemas. Never auto-restores an old backup:
# doing so could discard playback claims and replay an already sounded Azan.
"$PREVIOUS/.venv/bin/python" -m scripts.manage migrate
ln -s -- "$PREVIOUS" "$AZAN_ROOT/current.next"
mv -Tf -- "$AZAN_ROOT/current.next" "$AZAN_ROOT/current"
systemctl --user start digital-azan.service
systemctl --user try-restart azan-bluetooth-autoconnect.service || true
echo 'Previous code started using the current durable database. Check /health and logs.'
