# Repository recovery and implementation plan

Inspected on 2026-09-14: clean `main`, HEAD `d807a04`; no AGENTS.md,
CLAUDE.md, tests, Docker, database, checked-in systemd unit or CI workflow.

## Original system

Python 3, requests and PyYAML. Entrypoint: `python -m
scripts.run_scheduler_local`. Aladhan timingsByCity, Hyderabad/India,
method 1 (Karachi), provider-default school (0); no explicit madhab override.
Runtime timezone Asia/Kolkata, but cache and trigger dates used host-local
`date.today()`. Polling every 20 seconds with a 90-second grace window.
Schedule fetched only at startup, never at midnight. Internet required for
uncached dates; only today's JSON cached in app/cache. A second unused cache
helper wrote to state. JSON trigger flags were saved before blocking playback,
without transactions or completion tracking. State cleanup could delete data.

Pi audio: mpv `--ao=pulse`, with MPD stopped/resumed around playback;
Windows: winsound. Two bundled WAVs in assets/audio. No volume/stop API.
README describes a user systemd service under /home/pi/projects/digital_azan,
lingering, PipeWire/WirePlumber and Bluetooth. No credentials or SSH target
discovered, no CI/CD files in available Git history. Actual SSD mount unknown.
YAML configuration; .env ignored but not loaded. No web stack.

Hardcoded Ramadan 2026 table used 12-hour evening values as 24-hour morning
values. Preserve the source table as migration evidence, explicitly convert
Maghrib to evening, and retain prior enablement as an imported legacy profile.

## Implementation sequence

1. SQLite versioned migrations, legacy trigger import and runtime ownership lock.
2. Preserve Aladhan method/location, date-aware monthly caching; persisted daily
   occurrences and transactional claims, crash recovery and terminal history.
3. Nonblocking mpv playback, MPD restoration, stop, application volume,
   validated normal/Fajr collections and independent durable rotation.
4. Flask + Waitress local appliance API, static responsive HTML/CSS/JS, no
   frontend runtime/build service. Browser is never the scheduler.
5. Persist controls, history, health; reviewed Ramadan CSV/manual profiles,
   comparison preview and explicit activation; optional local OCR adapter.
6. Fake-clock/player tests, API and migration tests, syntax/lint and browser QA.
7. Preserve user systemd/PulseAudio deployment; repeatable SSD install,
   backups, staged releases/rollback and explicit GitHub deployment workflow.
8. Document verified results separately from unavailable Pi/audio/CI checks.

## Reliability decisions

Occurrence identity is local date + prayer, stronger than date + effective
time: moving a timetable must never replay an already claimed prayer. Only
future PENDING/DISABLED occurrences may change timing. All controls and claims
share a lock and an SQLite write transaction. A process file lock prevents two
controllers owning the same database. A persisted claim precedes audio start;
interrupted claims become FAILED, never replayed. This provides at-most-once
automatic starts; physical completion cannot be guaranteed across power loss.
