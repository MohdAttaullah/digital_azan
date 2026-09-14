# Verification record — 14 September 2026

## Verified locally

Environment: Windows, project virtual environment, Python 3.12.7. Automated
playback used fake players or explicitly isolated console mode; no physical Azan
was sounded. The production/default state directory was not used for smoke tests.

| Check | Exact command / method | Result |
| --- | --- | --- |
| Backend, scheduler, audio, persistence, migration, Ramadan, API, deployment seeding | `.venv/Scripts/python.exe -m pytest -q --basetemp=artifacts/pytest-final --tb=short` | **64 passed** |
| DOM interaction tests | `npm.cmd test` | **6 passed** |
| Python lint | `.venv/Scripts/python.exe -m ruff check app scripts tests` | Pass |
| Dependency consistency | `.venv/Scripts/python.exe -m pip check` | No broken requirements |
| Python compilation | `.venv/Scripts/python.exe -m compileall -q app scripts` | Pass |
| JavaScript syntax | `node --check app/static/app.js` | Pass |
| Installer syntax | Git Bash `bash -n deploy/install.sh` | Pass |
| Rollback syntax | Git Bash `bash -n deploy/rollback.sh` | Pass |
| Pi diagnostics script syntax | Git Bash `bash -n deploy/verify-pi.sh` | Pass |
| Workflow YAML | Loaded both workflow files with PyYAML BaseLoader; checked `on`/`jobs` | Pass; not remote Actions execution |
| Whitespace validation | `git diff --check` | Pass |
| Safe simulation | `.venv/Scripts/python.exe -m scripts.manage simulate` with workspace TEMP/TMP | One simulated Fajr PLAYED, four pending; temporary data only |
| ARM64 dependency distribution | `python -m pip download -r requirements.txt --dest artifacts/arm64-wheels --only-binary=:all: --platform manylinux2014_aarch64 --python-version 311 --implementation cp --abi cp311` | All 15 runtime distributions resolved/downloaded; not an ARM execution test |
| Live provider contract | `AZAN_DATA_DIR=artifacts/local-smoke python -m scripts.verify_provider 2026-09-14` | Monthly/daily endpoints matched all five prayer times |

The first pytest attempts could not access the sandbox's default temporary
directory. Tests were rerun successfully using a new workspace artifact directory.
The final results above are actual completed runs after implementation fixes.

## Live local process integration

Launched `python -m app` with these environment overrides:

```text
AZAN_DATA_DIR=D:\Projects\digital-azan\artifacts\local-smoke
AZAN_AUDIO_MODE=console
AZAN_HOST=127.0.0.1
AZAN_PORT=8080
```

Verified against the running Waitress server:

- `/` and `/static/app.js` returned HTTP 200.
- `/api/status` returned five local-day prayers and 35 days of persisted schedule.
- Live POSTs set volume to 25%, enabled 15-minute snooze and resumed it.
- After terminating/restarting the process, volume remained 25%, snooze remained
  resumed, five prayers/35-day coverage loaded, and the scheduler heartbeat returned.
- A simultaneous second `python -m app` process failed with
  `Another Azan controller owns this data directory` before starting its server.
- Console-mode health correctly reported degraded/unverified physical audio rather
  than falsely reporting production readiness.
- The isolated smoke-test server was stopped after verification.

Live provider comparison used Hyderabad/India, method 1, school 0 and
Asia/Kolkata. On 2026-09-14 both endpoints returned:

```text
Fajr 04:51 · Dhuhr 12:12 · Asr 15:34 · Maghrib 18:19 · Isha 19:32
```

This verifies endpoint consistency for the checked date, not an independent
religious validation of the selected calculation method or local Masjid timetable.

## Covered behavior

The tests cover transactional duplicate prevention, concurrent ticks, grace
boundaries, restart after completion/claim, stop and failed playback, watchdog,
midnight/next-day scheduling, disabled prayers, single-date skip, snooze/resume
including expired snooze across downtime, independent persisted audio rotation,
added/removed/corrupt files, empty Fajr collection, software-volume process
arguments, MPD restoration, migrations and consistent backups, legacy trigger
import, method/location-specific offline cache, Ramadan precedence/fallback,
retroactive corrections, import validation/mapping, revision-bound activation,
upload draft safety, control authentication/cross-origin/host protection, and
first-install preservation of existing configuration/audio.

The DOM tests execute the shipped HTML/JavaScript with jsdom and mock API
responses. They exercise countdown/timezone rendering, snooze/resume/stop,
volume/toggles/skip, history/settings, CSV draft mapping and visible errors/text
escaping. They do not render pixels or reproduce browser layout engines.

## Not verified / external requirements

- **No Raspberry Pi was accessed.** SSH host/user, installed OS/architecture,
  actual SSD mount, existing service state, LAN URL, speaker and runtime credentials
  were unavailable. No deployment or reboot was performed.
- No audible hardware output, Bluetooth reconnection, mpv decoding against the
  production sound device, or Linux user-session lifecycle was tested.
- Browser tools reported no available browser, including the in-app browser.
  Visual desktop/mobile/tablet QA remains outstanding. Responsive CSS is
  implemented; DOM tests are not visual verification.
- OCR adapter/upload safety is tested with a stub. Real Tesseract/Poppler/Pillow
  extraction and confidence accuracy on a Masjid photo/PDF remain unverified.
  The adapter conservatively recognizes ISO Gregorian date candidates; other date
  formats/scripts/complex tables need manual correction.
- GitHub Actions files are prepared and syntax checked, but no remote workflow
  was run. A dedicated ARM64 Pi runner, environment variables and any environment
  approval rules must be configured in the repository.
- No frontend production build exists or is needed: assets are served directly.
  Python 3.11 CI and actual ARM64 execution remain unverified locally.
- No UI audio preview, PWA installation or live playback-volume adjustment was
  implemented. Volume changes reliably apply to subsequent playback.
- Offline operation is limited to known cached/persisted dates. Long outages
  beyond schedule coverage produce visible warnings, not fabricated schedules.
- Physical completion across power loss cannot be guaranteed. Durable claims
  provide at-most-once automatic starts and interrupted outcomes remain explicit.

No Git commit, push, history rewrite or remote deployment was performed.
