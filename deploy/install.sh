#!/usr/bin/env bash
# Run as the existing audio-session user, never root. No runtime data is deleted.
set -euo pipefail
umask 077
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
AZAN_ROOT=${AZAN_INSTALL_ROOT:-"$HOME/digital-azan"}
SSD_MOUNT=${AZAN_SSD_MOUNT:?Set AZAN_SSD_MOUNT to the verified SSD mount (use / for SSD root boot)}
WEB_PORT=${AZAN_WEB_PORT:-}
[[ $EUID -ne 0 ]] || { echo 'Run as the Pi audio user, not root.'; exit 1; }
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
[[ "$AZAN_ROOT" = /* && "$SSD_MOUNT" = /* ]] || { echo 'Use absolute paths.'; exit 1; }
# Restrict template substitutions to ordinary absolute paths; spaces are intentionally unsupported.
[[ "$AZAN_ROOT" =~ ^/[A-Za-z0-9_./-]+$ ]] || exit 1
[[ "$SSD_MOUNT" == / || "$SSD_MOUNT" =~ ^/[A-Za-z0-9_./-]+$ ]] || exit 1
AZAN_ROOT=$(realpath -m -- "$AZAN_ROOT")
if [[ -z "$WEB_PORT" && -f "$AZAN_ROOT/shared/environment" ]]; then
  WEB_PORT=$(sed -n 's/^AZAN_PORT=//p' "$AZAN_ROOT/shared/environment" | tail -n 1)
fi
WEB_PORT=${WEB_PORT:-8080}
[[ "$WEB_PORT" =~ ^[0-9]+$ ]] && (( WEB_PORT >= 1 && WEB_PORT <= 65535 )) || { echo 'AZAN_WEB_PORT must be an integer from 1 to 65535.'; exit 1; }
case "$AZAN_ROOT/" in "$SOURCE/"*) echo 'Choose an install root outside the source checkout.'; exit 1 ;; esac
SSD_MOUNT=$(realpath -e -- "$SSD_MOUNT")
mountpoint -q -- "$SSD_MOUNT" || { echo 'Expected SSD is not mounted.'; exit 1; }
case "$AZAN_ROOT/" in "$SSD_MOUNT/"* ) ;; *) [[ "$SSD_MOUNT" == / ]] || { echo 'Install root must be on the specified SSD.'; exit 1; } ;; esac
for tool in python3 rsync mpv ffprobe curl systemctl; do command -v "$tool" >/dev/null || { echo "Missing dependency: $tool"; exit 1; }; done
[[ $(timedatectl show -p NTPSynchronized --value) == yes ]] || { echo 'Synchronize the Pi clock before deployment (sudo timedatectl set-ntp true).'; exit 1; }
[[ $(loginctl show-user "$USER" -p Linger --value) == yes ]] || { echo "Enable boot startup first: sudo loginctl enable-linger $USER"; exit 1; }
if systemctl is-active --quiet digital-azan.service; then
  echo 'A system-wide digital-azan service is active. Stop/disable it before using the existing user-service design.'
  exit 1
fi
LEGACY_ROOT=$(systemctl --user show digital-azan.service -p WorkingDirectory --value 2>/dev/null || true)
[[ -d "$LEGACY_ROOT" ]] || LEGACY_ROOT="$SOURCE"
mkdir -p -- "$AZAN_ROOT/releases" "$AZAN_ROOT/shared/data/backups" "$AZAN_ROOT/shared/audio/normal" "$AZAN_ROOT/shared/audio/fajr"
[[ $(findmnt -n -o MAJ:MIN -T "$AZAN_ROOT") == $(findmnt -n -o MAJ:MIN -T "$SSD_MOUNT") ]] || { echo 'Install root resolves to a different filesystem.'; exit 1; }
exec 9>"$AZAN_ROOT/shared/deploy.lock"
flock -n 9 || { echo 'Another deployment is in progress.'; exit 1; }
RELEASE="$AZAN_ROOT/releases/$(date -u +%Y%m%dT%H%M%SZ)-${GITHUB_SHA:-local}"
[[ ! -e "$RELEASE" ]] || { echo 'Release already exists; retry with a new timestamp.'; exit 1; }
mkdir -- "$RELEASE"
rsync -a --exclude=.git --exclude=.venv --exclude=node_modules --exclude=state --exclude=app/cache --exclude=artifacts --exclude=__pycache__ --exclude=.pytest_cache --exclude=.ruff_cache --exclude=.env "$SOURCE/" "$RELEASE/"
python3 -m venv "$RELEASE/.venv"
"$RELEASE/.venv/bin/python" -m pip install -r "$RELEASE/requirements.txt"
if [[ ${AZAN_INSTALL_OCR:-0} == 1 ]]; then
  "$RELEASE/.venv/bin/python" -m pip install -r "$RELEASE/requirements-ocr.txt"
fi
if [[ ! -f "$AZAN_ROOT/shared/config.yaml" ]]; then
  (cd -- "$RELEASE" && "$RELEASE/.venv/bin/python" -m scripts.seed_install "$LEGACY_ROOT" "$AZAN_ROOT")
fi
if [[ ! -f "$AZAN_ROOT/shared/environment" ]]; then
  printf 'AZAN_CONFIG=%s/shared/config.yaml\nAZAN_DATA_DIR=%s/shared/data\nAZAN_PORT=%s\n' "$AZAN_ROOT" "$AZAN_ROOT" "$WEB_PORT" > "$AZAN_ROOT/shared/environment"
fi
# Keep original trigger state/cache on first migration; copy only after old service is stopped below.
systemctl --user stop digital-azan.service || true
if pgrep -u "$USER" -f '[p]ython.*(scripts.run_scheduler_local| -m app)' >/dev/null; then
  echo 'An unmanaged Azan process remains. Stop it before deployment.'
  exit 1
fi
if [[ -f "$LEGACY_ROOT/state/scheduler_state.json" ]]; then
  # Refresh the migration input on retries; the database importer itself is one-time.
  cp -- "$LEGACY_ROOT/state/scheduler_state.json" "$AZAN_ROOT/shared/data/scheduler_state.json"
fi
mkdir -p -- "$AZAN_ROOT/shared/data/cache"
if [[ -d "$LEGACY_ROOT/app/cache" ]]; then rsync -a --ignore-existing "$LEGACY_ROOT/app/cache/" "$AZAN_ROOT/shared/data/cache/"; fi
export AZAN_CONFIG="$AZAN_ROOT/shared/config.yaml" AZAN_DATA_DIR="$AZAN_ROOT/shared/data" AZAN_PORT="$WEB_PORT"
cd -- "$RELEASE"
if [[ -f "$AZAN_DATA_DIR/azan.sqlite3" ]]; then
  "$RELEASE/.venv/bin/python" -m scripts.manage backup "$AZAN_DATA_DIR/backups/pre-deploy-$(date -u +%Y%m%dT%H%M%SZ).sqlite3"
fi
"$RELEASE/.venv/bin/python" -m scripts.manage migrate
PREVIOUS=$(readlink -f -- "$AZAN_ROOT/current" || true)
mkdir -p -- "$HOME/.config/systemd/user"
sed -e "s|@ROOT@|$AZAN_ROOT|g" -e "s|@MOUNT@|$SSD_MOUNT|g" "$RELEASE/deploy/digital-azan.service.in" > "$HOME/.config/systemd/user/digital-azan.service"
sed -e "s|@ROOT@|$AZAN_ROOT|g" "$RELEASE/deploy/azan-backup.service.in" > "$HOME/.config/systemd/user/azan-backup.service"
sed -e "s|@ROOT@|$AZAN_ROOT|g" "$RELEASE/deploy/azan-bluetooth-autoconnect.service.in" > "$HOME/.config/systemd/user/azan-bluetooth-autoconnect.service"
cp -- "$RELEASE/deploy/azan-backup.timer" "$HOME/.config/systemd/user/azan-backup.timer"
NEXT_LINK="$AZAN_ROOT/current.next.$(basename -- "$RELEASE")"
ln -s -- "$RELEASE" "$NEXT_LINK"
mv -Tf -- "$NEXT_LINK" "$AZAN_ROOT/current"
if [[ -n "$PREVIOUS" && -d "$PREVIOUS" ]]; then printf '%s\n' "$PREVIOUS" > "$AZAN_ROOT/shared/previous-release"; fi
systemctl --user daemon-reload
if grep -Eq '^AZAN_BLUETOOTH_MAC=([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$' "$AZAN_ROOT/shared/environment"; then
  systemctl --user enable azan-bluetooth-autoconnect.service
  systemctl --user restart azan-bluetooth-autoconnect.service
else
  systemctl --user disable --now azan-bluetooth-autoconnect.service 2>/dev/null || true
fi
systemctl --user enable --now digital-azan.service
systemctl --user enable --now azan-backup.timer
PORT=$("$RELEASE/.venv/bin/python" -c 'from app.config import load_config; print(load_config().port)')
for attempt in $(seq 1 45); do
  if curl --fail --silent "http://127.0.0.1:$PORT/health" > "$AZAN_ROOT/shared/last-health.json"; then
    echo "Deployment healthy. UI: http://$(hostname).local:$PORT"
    exit 0
  fi
  sleep 2
done
echo 'Health check failed. Inspect journalctl --user -u digital-azan -n 100 and /health.'
echo 'Runtime data and previous release are preserved. Use deploy/rollback.sh after inspecting the failure.'
exit 1
