# Raspberry Pi SSD deployment and recovery

The existing design is a **user systemd service**, because mpv must use the same
PulseAudio/PipeWire session as the Bluetooth speaker. Use the existing Pi audio
user (`pi` on the verified production host). Do not introduce a second system-wide
Azan service. Production is Debian 12 ARM64 on `raspberrypi`, with `/dev/sda2` as
the SSD-backed root filesystem and Digital Azan installed under
`/home/pi/digital-azan`. See `verification.md` for completed checks and remaining
hardware/browser verification.

## 1. Inspect the actual Pi

Run `bash deploy/verify-pi.sh` or individually:

```bash
uname -a
uname -m
cat /etc/os-release
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS,MODEL
findmnt
df -h
systemctl --failed
timedatectl
systemctl --user status digital-azan
pactl info
pactl list short sinks
```

Confirm the OS filesystem is SSD-backed, or identify the already-mounted SSD
directory. Do not format or repartition storage. For an external SSD, configure
its stable UUID mount through the OS before installation. The installer checks
mountpoint and filesystem identity and refuses to install onto a different
filesystem. Verify adequate space and usable audio output yourself.

## 2. Prepare the same audio user

On Raspberry Pi OS with Python 3.11+:

```bash
sudo apt update
sudo apt install python3-venv rsync mpv ffmpeg curl pulseaudio-utils
sudo loginctl enable-linger "$USER"
sudo timedatectl set-timezone Asia/Kolkata
sudo timedatectl set-ntp true
timedatectl
```

Keep the existing PipeWire/WirePlumber and Bluetooth configuration; do not replace
the audio stack merely to install this app. Lingering creates the user manager
after reboot without login. On a minimal image, install the distribution's
PipeWire/PulseAudio compatibility and Bluetooth packages if absent.

Verify `System clock synchronized: yes` before deployment. The installer requires
NTP synchronization. Health checks inspect it periodically without implementing
NTP in Python. No application can recover accurate religious times from a wildly
incorrect system clock.

## 3. Stage and install

Run from a source checkout outside the chosen installation directory. Existing
source code, shared database, audio, settings and Ramadan profiles are retained.
The first installation reads the old user service's WorkingDirectory, preserves
its YAML location/method/audio configuration, copies recordings to shared
collections, and imports the legacy trigger file after stopping the old service.
Inspect `systemctl --user show digital-azan -p WorkingDirectory` beforehand,
especially if the former SD-card directory is no longer mounted. Copy recovered
legacy state into the old checkout before installation if necessary.

If inspection confirmed that `/` is the SSD root filesystem:

```bash
AZAN_INSTALL_ROOT="$HOME/digital-azan" AZAN_SSD_MOUNT=/ AZAN_WEB_PORT=8090 bash deploy/install.sh
```

If the SSD is mounted elsewhere, substitute its **verified** actual path:

```bash
AZAN_INSTALL_ROOT=/mnt/ssd/digital-azan AZAN_SSD_MOUNT=/mnt/ssd bash deploy/install.sh
```

`/mnt/ssd` is only an example. The directory must be writable by the audio user.
Ordinary absolute paths without spaces are required by the systemd templates.
Do not use the checkout itself as the installation root.

For OCR, first install `tesseract-ocr poppler-utils`, then add
`AZAN_INSTALL_OCR=1` to the install command on every release.

Installation stages code/dependencies while the old service runs, then stops it,
checks for unmanaged old scheduler processes, copies legacy state, backs up the
existing SQLite database **without migrating it**, runs migrations and switches
the `current` symlink. It installs/enables `digital-azan.service` and
`azan-backup.timer`, starts the service and polls `/health` for up to 90 seconds.
No `rsync --delete` is used. Code releases never contain production runtime data.

If a post-stop migration or health check fails, inspect the error and logs. The
script deliberately reports failure and retains releases/backups rather than
silently restoring old data that could lose playback claims. A first migration
from the legacy JSON scheduler should be treated as a forward migration; do not
restart the legacy code after the new controller has begun playing prayers.

At boot, the service's `ExecStartPre=mountpoint` check refuses to run until the
specified SSD is mounted, retrying every 10 seconds. The existing user-service
audio session is preserved. `KillMode=control-group` prevents orphaned mpv players
on restart; the application additionally holds an OS lock on its data directory.

## 4. Normal operation

```bash
systemctl --user start digital-azan
systemctl --user stop digital-azan
systemctl --user restart digital-azan
systemctl --user status digital-azan --no-pager
journalctl --user -u digital-azan -f
curl -sS http://127.0.0.1:8090/health
hostname
hostname -I
```

The verified production UI is `http://raspberrypi.local:8090`, or
`http://192.168.1.35:8090` on the current LAN. Port 8090 avoids the existing Caddy
listener on 8080. Set `AZAN_WEB_PORT` on first installation; the installer stores
it in `shared/environment` so later releases retain it.
Change port/host in `shared/config.yaml` or `shared/environment` and restart.
Health returns HTTP 503 for degraded conditions (including console simulation),
with details in its JSON; `/api/status` remains usable for troubleshooting.
Detected PulseAudio sinks are useful evidence, but do not prove sound was audible.

After installation, reboot the Pi deliberately when convenient, then verify from
another device that the UI returns, settings/rotation/history persist, the
schedule/countdown are correct, and only one user service is running. Check SSD,
NTP and audio again. This reboot check has not been performed in the development
environment.

## 5. Add or troubleshoot recordings

Copy supported recordings into the persistent `shared/audio/normal` or
`shared/audio/fajr` folder. Never put ordinary Azan in the Fajr collection. They
are rediscovered within a minute. Health reports empty/invalid collections.

Read-only audio diagnostics:

```bash
pactl info
pactl list short sinks
bluetoothctl devices
systemctl --user status pipewire pipewire-pulse wireplumber
journalctl --user -u digital-azan -n 100 --no-pager
```

To intentionally hear a test at a suitable moment, as the same service user:

```bash
mpv --no-config --no-video --ao=pulse --volume=25 /absolute/path/to/recording.wav
```

This manual player test is separate from scheduled history and must not be run
while automatic playback is active. It verifies the selected audio session and
speaker; unit tests never do this.

If the previously paired speaker lost its configuration after SSD migration,
use `bluetoothctl` to scan, pair, trust and connect the actual device. Keep or
restore its verified device address in `shared/environment`:

```text
AZAN_BLUETOOTH_MAC=3C:1A:CD:7D:9C:3D
AZAN_BLUETOOTH_RETRY_SECONDS=15
```

When that value is present, the installer enables
`azan-bluetooth-autoconnect.service`. It reconnects the existing trusted bond and
selects the matching PipeWire sink after boot or a transient drop. It never pairs,
trusts or guesses a device. mpv continues to use PulseAudio/PipeWire.

Deployment also installs a WirePlumber user override when the Bluetooth MAC is
configured. It disables logind arbitration for the lingering, headless audio
session, allowing WirePlumber to expose the A2DP sink before an interactive login.
The speaker profile is constrained to the broadly supported SBC A2DP codec to
avoid unstable optional-codec negotiation on Raspberry Pi OS BlueZ 5.66. The
existing BlueZ pairing and trust records are left untouched.

For a controlled playback well outside the 10-minute prayer safety window, open
Settings → Audio collections and select **Test normal Azan** or **Test Fajr Azan**.
The test uses the saved Azan volume, does not advance round-robin rotation, and can
be ended with **Stop Azan** in the playback banner. Start/stop/completion is written
to the event audit trail without creating a prayer occurrence.

## 6. Backups and restore

SQLite's online backup API creates a consistent backup including settings,
history, occurrence claims, rotation, snooze windows and Ramadan profiles. Daily
backups are written at approximately 03:00 with a small randomized delay.

```bash
systemctl --user start azan-backup.service
systemctl --user list-timers azan-backup.timer
journalctl --user -u azan-backup.service -n 20
```

Manual backup (adjust root if needed):

```bash
cd "$HOME/digital-azan/current"
AZAN_DATA_DIR="$HOME/digital-azan/shared/data" .venv/bin/python -m scripts.manage backup "$HOME/azan-backup.sqlite3"
```

Copy backups plus `shared/config.yaml` and `shared/environment` to another disk
periodically; keep environment files private. Back up audio separately when the
collection changes. Automatic backups do not copy audio, and have no automatic
retention deletion; monitor available space and archive/prune old copies using
your normal file-management process.

For disaster recovery, **stop the service and keep a copy of the current damaged
database plus its WAL/SHM files**. Verify the chosen backup with
`sqlite3 backup.sqlite3 'PRAGMA integrity_check;'` (install the sqlite3 CLI if
needed). Restore into a **new empty data directory**, set `AZAN_DATA_DIR` in
`shared/environment` to that directory, copy matching cache if available, and
retain the old directory intact. Start the restored service only after considering
today's already-sounded occurrences: an older backup may lack their claims.

The safest restoration during a day is to wait beyond the last potentially
already-sounded occurrence's 90-second grace window before starting, or restore
while no prayer is within its grace window. The scheduler records older pending
occurrences as missed instead of replaying them. Never overwrite a live SQLite
database, discard a live WAL, or auto-restore an old snapshot during rollback.

## 7. Code rollback

After a successful previous installation, the installer records the prior release.

```bash
AZAN_INSTALL_ROOT="$HOME/digital-azan" bash deploy/rollback.sh
systemctl --user status digital-azan
curl -sS http://127.0.0.1:8090/health
```

Rollback stops the service, checks schema compatibility with previous code, and
switches the code symlink using the **current** database. It refuses newer schemas
that the previous code cannot understand. Use a forward fix if schema rollback is
incompatible; never regain compatibility by erasing occurrence history.

## 8. GitHub Actions

No previous workflow files were found in the repository/history. The supplied
replacement is explicit and private-network friendly:

- `ci.yml`: pushes to main, pull requests and manual runs; Python 3.11/3.12 tests,
  lint, DOM tests, JavaScript/shell syntax and console simulation on GitHub-hosted
  runners.
- `deploy.yml`: a successful completed `Test` workflow caused by a push to `main`
  unlocks installation on a dedicated self-hosted Pi runner labelled
  `self-hosted`, `Linux`, `ARM64`, `azan`. A manual dispatch on `main` runs its own
  hosted validation first. Pull requests never run the deployment job.
- Configure repository environment `raspberry-pi`. For unattended production
  deployment, do not add an approval gate to that environment. Optional repository
  variables are `AZAN_INSTALL_ROOT`, `AZAN_SSD_MOUNT`, and `AZAN_WEB_PORT`; verified
  defaults are `/home/pi/digital-azan`, `/`, and `8090`.
- Protect `main`, require the `test (3.11)` and `test (3.12)` checks with strict
  branch freshness, block force pushes/deletion, and require resolved review
  conversations. Restrict the `raspberry-pi` environment to protected branches.
- Install/run that runner as the **same audio user** and preserve user systemd
  access. The script sets its XDG runtime/D-Bus session paths when absent.
- Optional OCR deployment: set `AZAN_INSTALL_OCR=1` in the runner environment or
  add the corresponding workflow environment variable.
- Do not run untrusted pull requests on this Pi runner. Keep runners patched and
  network access private. No SSH key is required by this supplied flow; an existing
  external SSH deployment can instead invoke the same installer after copying code.
- Workflow concurrency (`raspberry-pi-production`, without cancellation) prevents
  overlapping production jobs, and an on-disk deployment lock also protects
  manual runs.

The production flow is push to `main` → required `Test` checks → ARM64 runner → stage
release and dependencies → preserve/backup shared data → stop the old service →
migrate → atomically switch code → start → health verification. A failed hosted
job cannot schedule deployment, and installer or health failure exits the
deployment job nonzero. Use `deploy/rollback.sh` to restore the recorded previous
known-good code against the current durable database; it refuses an incompatible
schema and never replaces production data with an older backup.
