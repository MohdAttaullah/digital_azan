# Digital Azan Controller

A local prayer-audio appliance for Raspberry Pi, with a responsive dashboard, durable history, meeting controls and reviewed Ramadan timetables. Python handles scheduling even when every browser is closed. Native **user systemd + mpv/PulseAudio** deployment is preserved.

**Verification status:** backend/API/migration tests and DOM interaction tests run locally. Raspberry Pi deployment, SSD mounts, Bluetooth output, reboot behavior and remote GitHub Actions execution still require a connected Pi. This repository does not claim those hardware checks have passed.

## Run locally

Python 3.11+ is required. From the repository root:

```bash
python -m venv .venv
# Linux / Pi:
source .venv/bin/activate
# Windows PowerShell instead:
# .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app
```

Open **http://localhost:8080**. On another trusted LAN device use **http://<pi-hostname>.local:8080** or the Pi's LAN IP. The default bind is `0.0.0.0`; do not port-forward it to the internet. Host and port are configurable.

For silent local development, set console mode before launching:

```powershell
$env:AZAN_AUDIO_MODE = 'console'
$env:AZAN_DATA_DIR = 'D:\Projects\digital-azan\artifacts\development'
$env:AZAN_HOST = '127.0.0.1'
python -m app
```

On Linux use `AZAN_AUDIO_MODE=console AZAN_DATA_DIR=/tmp/azan-development python -m app`. Console mode is visibly reported as simulation in health. Any simulated history is kept in the selected development database; never point a simulation at production data.

`python -m scripts.run_scheduler_local` remains an entrypoint for the new single controller. Its old `--test-azan` behavior is retired; use the isolated simulation command below or an intentional mpv hardware test.

## Daily use

- **Today:** next enabled occurrence, server-synchronized local clock/countdown, five prayer rows, timing sources, exact status counts, timestamps and recording names.
- **Snooze:** 15/30/60 minutes or a selected local time within the next 24 hours. An occurrence due inside that interval becomes `SUPPRESSED`, even if the service restarts after snooze expires. It is never deferred to the end of the meeting. Snooze does not stop audio already playing; use Stop.
- **Stop Azan:** terminates the current player and records `STOPPED_BY_USER`. An already completed recording remains `PLAYED` if completion wins the race.
- **Skip this Azan:** only that upcoming occurrence changes to `SKIPPED`.
- **Prayer toggles:** persist across days/reboots. Enabling a prayer after its disabled occurrence has passed does not replay it.
- **Volume:** 0–100%, saved in SQLite. Uses mpv's software mixer, leaving the system master volume alone. Changes apply to the **next** playback; live volume adjustment is not implemented.
- **History:** select a date to see actual playback and other outcomes. Only `PLAYED` counts as played. No historical sound completion is invented for the old JSON flags.
- **Settings:** editable control token for the browser tab, detected audio collections, and read-only location/calculation/runtime configuration and health. Persistent volume/toggles are on Today. Location, timezone, method and folder paths remain in YAML to keep critical configuration explicit.

The browser polls every 10 seconds; clock/countdown update locally every second. The server remains the timing authority. A stale connection is shown explicitly.

## Architecture and scheduling

```text
One user systemd service / one Python process
  Controller ---- SQLite (versioned migrations, WAL, FULL synchronization)
    |-- 2-second scheduler: transactional claim -> nonblocking playback -> completion
    |-- calendar/health worker: provider/cache, audio discovery, host probes
    |-- AzanPlayer: mpv process + MPD stop/resume
    |-- RamadanService: drafts, validation, comparisons, activation
    `-- Flask + Waitress -> static HTML/CSS/JavaScript -> LAN browsers
```

No Docker, Redis, Node server or frontend build is needed. Node/jsdom is only a development test dependency.

Occurrence identity is **local date + prayer**. A timetable edit cannot create a second occurrence for an already claimed prayer. SQLite write transactions plus a controller lock serialize automatic starts, skip/snooze/stop and timetable changes. An OS file lock rejects a second controller using the same data directory. Do not run a second installation against a different database with the same physical speaker.

A durable `PLAYING` claim and rotation update commit **before** mpv starts. Successful exit becomes `PLAYED`; errors become `FAILED`. Claims found at restart become `FAILED` with completion unknown, and are never automatically retried. This deliberately guarantees at-most-once automatic starts, rather than falsely guaranteeing audible completion across power loss. systemd's `KillMode=control-group` kills old mpv children before a restart.

The existing configurable **90-second grace period** is preserved. Beyond it, pending occurrences become `MISSED_DOWNTIME`, not late playback. Already terminal occurrences never return to pending. Only future pending/disabled occurrences change when a profile is activated/deactivated; a correction into the past is recorded as missed. A 15-minute playback watchdog prevents a stuck decoder from blocking all later prayers.

All automatic timestamps are UTC ISO-8601 with offsets. Local dates/times use the configured IANA timezone. A nonexistent DST wall time is rejected; an ambiguous repeated time uses the first occurrence. Asia/Kolkata has neither ambiguity.

## Prayer-time source

The existing source remains **Aladhan**, **Hyderabad, India**, **method 1 (Karachi)** and provider-default **school 0**. No change to madhab/calculation method is inferred from local practices. Set `location.school: 1` only if intentionally choosing Hanafi Asr calculation.

The provider now uses the date-specific monthly `calendarByCity` endpoint with explicit timezone and the same calculation parameters. It caches full months, keyed by location, method, school and timezone, and materializes **35 days** of occurrences. The calendar worker refreshes at local midnight and hourly, retrying failures every five minutes. Network requests never run on the time-critical scheduler thread.

Cached matching dates and persisted occurrences work offline. A network outage beyond cached coverage can prevent new schedules; health reports this rather than reusing another day's timings. Matching legacy daily cache files can be read as a fallback. Cache cleanup does not delete history.

Provider documentation: [Aladhan API](https://aladhan.com/prayer-times-api), [calculation methods](https://aladhan.com/calculation-methods).

## Recordings and rotation

Bundled `assets/audio/azan.wav` and `assets/audio/azan_fajr.wav` remain the defaults for an existing YAML configuration. Production installation copies original configured recordings into persistent collections:

```text
shared/audio/normal/  # Dhuhr, Asr, Maghrib, Isha
shared/audio/fajr/    # Fajr only
```

Configure `audio.collections.normal` and `audio.collections.fajr` in YAML. An explicitly configured empty Fajr directory is a visible configuration error; it **never** falls back to normal Azan.

Names are naturally sorted (`azan_1`, `azan_2`, `azan_10`). The last selected filename is persisted separately for each collection. Rotation advances on a claimed playback attempt, including a failed start. Added/removed files are handled without resetting all positions. New recordings are discovered within a minute. WAV files are checked for valid PCM headers/length; compressed formats are checked with ffprobe. Decoder failures still become terminal failed occurrences. Supported formats: WAV, MP3, OGG, FLAC and M4A.

Install mpv on both Pi and Windows for physical playback. Windows winsound was replaced because it could not provide this controller's volume and process lifecycle controls. Pi playback retains `--ao=pulse`. MPD is stopped only if it was playing, and resumed after completion/stop; failure to coordinate it is logged. [mpv volume documentation](https://mpv.io/manual/stable/) describes the application software mixer.

No audio-preview button is exposed in the UI. Intentional hardware testing is documented in the deployment guide.

## Ramadan timetables

Open **Ramadan timings**. Create a name/source, then enter rows manually or import CSV:

```csv
date,fajr,maghrib
2027-03-05,05:21,18:34
2027-03-06,05:20,18:35
```

1. Use Gregorian `YYYY-MM-DD` and 24-hour `HH:MM`.
2. Confirm CSV column meanings. A column called Sehri is not silently mapped to Fajr.
3. Correct the editable table. Missing one prayer falls back to standard timing; missing both is invalid. Duplicate/impossible dates, malformed times, afternoon Fajr and morning Maghrib are rejected. Missing days/nonsequential ranges are warned about.
4. **Save draft & preview** compares normal versus override times and minute differences. Differences over 30 minutes are flagged. If the standard provider is unavailable, the preview labels the comparison unknown; review against the source card carefully.
5. Check the explicit review box, then **Confirm & activate**. The API requires a preview of the current revision; changing the draft invalidates prior approval.

Only one profile is active globally, providing unambiguous precedence. Activating another deactivates the previous one. Only specified dates and Fajr/Maghrib values override calculation. Dhuhr/Asr/Isha stay standard. Outside those dates normal calculation resumes automatically. Deactivate before editing or deleting an active profile; deletion requires confirmation.

The existing Darul Uloom Ziya-e-Mustafa 2026 timetable is imported once with its prior enabled state. Its 12-hour Maghrib values are explicitly normalized to evening (for example, `6:29` becomes `18:29`). Legacy flags do not certify that audio actually finished.

### Optional photo/PDF OCR

On the Pi:

```bash
sudo apt install tesseract-ocr poppler-utils
python -m pip install -r requirements-ocr.txt
```

For staged deployment set `AZAN_INSTALL_OCR=1` each time. These are optional dependencies; CSV/manual entry always works without OCR.

The local adapter accepts JPEG/PNG/PDF up to 8 MB, limits decoded images to 20 megapixels and PDF processing to three pages, and runs tools with timeouts. Extraction returns text, word-confidence summaries, ISO date candidates and time columns. The user explicitly maps time columns, copies them to the editable draft, corrects values and goes through preview/activation. Extraction **never** creates an active profile.

Non-ISO dates, unfamiliar scripts, complex tables and ambiguous religious headings require manual correction. No year/date/time is invented. Real Masjid-card OCR accuracy has not been verified here; no sample card or Pi OCR runtime was available.

## Data, configuration and secrets

Development defaults to `state/azan.sqlite3`. Deployment uses:

| Content | Installed path relative to installation root |
| --- | --- |
| History, occurrences, volume, enablement, snooze intervals, rotation, profiles, overrides, audit events | `shared/data/azan.sqlite3` |
| Aladhan month cache | `shared/data/cache/` |
| SQLite backups | `shared/data/backups/` |
| Recordings | `shared/audio/normal/`, `shared/audio/fajr/` |
| Configuration | `shared/config.yaml` |
| Environment and optional control token | `shared/environment` |
| Code and dependencies | `releases/<release>/`, selected by `current` symlink |
| Runtime logs | user systemd journal |

`AZAN_DATA_DIR` overrides the data directory; `AZAN_CONFIG` selects YAML. Relative YAML paths resolve against the repository/release root. `.env.example` lists environment options; `.env` is **not automatically loaded**. systemd reads `shared/environment` directly.

Migrations in `app/migrations/` run transactionally and are tracked by SQLite `user_version`. Existing JSON trigger claims are imported once, original files are retained, and corrupt legacy trigger state fails startup rather than risking duplicate playback. Back up before resolving corrupt state. The old `app/state.py`, `app/cache.py` and cleanup helper are no longer on the runtime path.

Requests validate input, constrain uploads to generated temporary paths and escape text in the UI. Mutations require a custom same-origin header, reject cross-site requests and can require `AZAN_CONTROL_TOKEN`. Set a long random token in `shared/environment` and enter it in Settings; it stays in tab session storage. Read-only status remains available on the trusted LAN. For access beyond the LAN, use VPN or an authenticated HTTPS proxy and a token. No shell execution or arbitrary file access API exists.

Host validation accepts private IP addresses, localhost and the machine hostname/`.local` name. Set `AZAN_ALLOWED_HOSTS` to an explicit comma-separated list for custom proxy names; this prevents arbitrary public hostnames from controlling a device through DNS rebinding.

## Tests and safe simulation

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check app scripts tests
npm ci --ignore-scripts
npm test
node --check app/static/app.js
for script in deploy/*.sh; do bash -n "$script"; done
python -m scripts.manage simulate
python -m scripts.manage schedule 2027-03-05
```

Tests use injected time, temporary SQLite databases and fake players; no test sounds Azan. `simulate` uses a temporary database and console audio. `schedule` prints the standard provider schedule for a chosen date; it never plays audio. jsdom tests check DOM behavior, not actual browser rendering.

In a restricted Windows sandbox use an existing workspace `artifacts` directory and a **new** `--basetemp=artifacts/pytest-run-N` path if the default temporary directory is unavailable.

## Raspberry Pi, backups and CI/CD

See [deployment and recovery](docs/deployment.md) for SSD verification, installation, systemd commands, backups/restoration, Bluetooth diagnostics and GitHub runner setup. See [original architecture and implementation decisions](docs/implementation-plan.md) and [verification results](docs/verification.md).

The old repository contained no checked-in CI/CD pipeline in the available history. New GitHub workflows test pull requests/pushes on hosted runners and provide an explicit manual deployment to a dedicated ARM64 Pi runner. No remote push or workflow execution is performed by merely editing this repository.
