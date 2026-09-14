# Verification record — 14 September 2026

## Production Raspberry Pi and CI/CD verification

Production host: `pi@raspberrypi`, Debian 12 ARM64, SSD root `/dev/sda2` mounted
at `/`, timezone `Asia/Kolkata`, NTP synchronized. Digital Azan listens on 8090
because the existing Caddy deployment already owns 8080.

| Check | Evidence | Result |
| --- | --- | --- |
| Push-to-main CI | Protected `main` push `f7579d8`; Actions run `34871665570` | **PASS** |
| Required CI | `test (3.11)` and `test (3.12)` both succeeded | **PASS** |
| Gated automatic deployment | Successful `Test` completion created `workflow_run` deployment `34871721375` for the same SHA | **PASS** |
| Pi runner | `raspberrypi-digital-azan`, online, labels `self-hosted,Linux,ARM64,azan`, runner 2.337.0 | **PASS** |
| Release installation | Active immutable recovery release `20260914T170242Z-f7579d8…`; dependency install, migration and activation succeeded | **PASS** |
| Persistent data | SQLite, config, environment and both audio file inodes remained unchanged across deploy and rollback | **PASS** |
| Database backup/migration | Verified pre-deploy backup created before successful migration | **PASS** |
| Service restart | User service active after deployment with a new PID and zero automatic restarts | **PASS** |
| Health check | Installer and independent LAN request returned HTTP 200, `ok: true`, 35 schedule days and no warnings | **PASS** |
| Concurrency | Workflow group `raspberry-pi-production` plus on-disk `flock` | **PASS** |
| Manual deployment | `workflow_dispatch` run `34872254224`: hosted validation and Pi deployment succeeded | **PASS** |
| Rollback | Previous release activated against the current database; health and persistent inodes remained valid; manual workflow restored `f7579d8` | **PASS** |
| Single scheduler | A second ARM64 process using the production data directory failed with `Another Azan controller owns this data directory` | **PASS** |
| Backup timer/manual backup | Timer enabled/active; on-demand verified SQLite backup created | **PASS** |
| Reboot survival | Full-host reboot blocked pending fresh user approval | **NOT VERIFIED** |
| Bluetooth/audible output | PipeWire physical analog sink detected; no Bluetooth device discoverable or paired | **NOT VERIFIED** |
| Visual browser QA | HTTP/UI assets and DOM behavior passed; no targetable browser session was available | **NOT VERIFIED** |

The first controlled push (`cfc7d8e`) exposed a one-second asynchronous DOM-test
flake in required CI. Its already-started deployment workflow was cancelled before
release activation. The DOM clock is now fixed in the test, and production deploys
are triggered only by a successful completed `Test` workflow from a `main` push.
This failure/recovery is retained here because it directly verified that the final
workflow needed a cross-workflow gate rather than an independent duplicate test.

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

- Full reboot survival remains outstanding because the automatic approval review
  required a fresh explicit user approval for host disruption.
- The normal and Fajr files decode successfully with `ffprobe`, PipeWire/PulseAudio
  runs in the persistent `pi` user session, and a physical analog sink is present.
  No Bluetooth device was paired/discoverable, so reconnection and audible output
  remain outstanding.
- Browser tools reported no targetable browser, including the in-app browser.
  Visual desktop/mobile/tablet QA remains outstanding. HTTP assets and DOM tests
  pass, but DOM tests are not visual verification.
- OCR adapter/upload safety is tested with a stub. Real Tesseract/Poppler/Pillow
  extraction and confidence accuracy on a Masjid photo/PDF remain unverified.
  The adapter conservatively recognizes ISO Gregorian date candidates; other date
  formats/scripts/complex tables need manual correction.
- No frontend production build exists or is needed: assets are served directly.
- No UI audio preview, PWA installation or live playback-volume adjustment was
  implemented. Volume changes reliably apply to subsequent playback.
- Offline operation is limited to known cached/persisted dates. Long outages
  beyond schedule coverage produce visible warnings, not fabricated schedules.
- Physical completion across power loss cannot be guaranteed. Durable claims
  provide at-most-once automatic starts and interrupted outcomes remain explicit.

Production commits were pushed to `main`; no history rewrite was performed.
