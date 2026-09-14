"""Appliance orchestration: browser-independent scheduling and serialized controls."""
import logging
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from zoneinfo import ZoneInfo

from app.audio.collections import AudioCollections
from app.azan_player import AzanPlayer
from app.health import probe_host
from app.prayer_times import PrayerTimesClient
from app.ramadan import RamadanService
from app.storage import Store

log = logging.getLogger(__name__)


class Controller:
    def __init__(self, cfg, store=None, provider=None, player=None, clock=None):
        self.cfg = cfg
        self.tz = ZoneInfo(cfg.timezone)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.store = store or Store(cfg.database)
        self.provider = provider or PrayerTimesClient(
            cfg.city, cfg.country, cfg.method, timezone=cfg.timezone,
            cache_dir=cfg.data_dir / "cache", school=cfg.school)
        self.player = player or AzanPlayer(cfg)
        self.collections = AudioCollections(cfg)
        self.ramadan = RamadanService(self.store, self.provider)
        self.lock = threading.RLock()
        self.halt = threading.Event()
        self.refresh_requested = threading.Event()
        self.threads = []
        self.active = None
        self.heartbeat = None
        self.schedule_warning = "Schedule loading"
        self.runtime_warning = None
        self.last_refresh = None
        self.host_health = {"clock_sync": "Checking", "audio_device": "Checking", "warnings": []}

    def now(self):
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("Clock must return an aware datetime")
        return now.astimezone(timezone.utc)

    def recover(self):
        with self.lock, self.store.connect(write=True) as db:
            interrupted = db.execute("SELECT id FROM occurrences WHERE status='PLAYING'").fetchall()
            db.execute("UPDATE occurrences SET status='FAILED',completed_at=?,failure_reason=? WHERE status='PLAYING'",
                       (self.now().isoformat(), "Service interrupted during playback; completion unknown"))
            for row in interrupted:
                self.store.event(db, "playback_interrupted", "No automatic retry", row[0])

    def _effective(self, db, day, prayer, normal):
        if prayer in ("Fajr", "Maghrib"):
            row = db.execute(
                "SELECT o.fajr,o.maghrib,p.name,p.source FROM overrides o "
                "JOIN profiles p ON p.id=o.profile_id WHERE p.active=1 AND o.date=?", (day,)).fetchone()
            if row and row[prayer.lower()]:
                return row[prayer.lower()], f"{row['name']} — {row['source']} override"
        return normal, "Standard calculation"

    def timestamp(self, day, hhmm):
        local = datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=self.tz)
        # Fail closed on a nonexistent wall time at a DST transition.
        if local.astimezone(timezone.utc).astimezone(self.tz).replace(tzinfo=None) != local.replace(tzinfo=None):
            raise ValueError(f"Nonexistent local prayer time: {day} {hhmm}")
        return local.astimezone(timezone.utc).isoformat()

    def build_day(self, day, timings):
        now = self.now().isoformat()
        with self.lock, self.store.connect(write=True) as db:
            for prayer in self.cfg.prayers:
                normal = timings[prayer]
                effective, source = self._effective(db, day.isoformat(), prayer, normal)
                scheduled_at = self.timestamp(day, effective)
                enabled = self.store.get(db, f"enabled:{prayer}", True)
                old = db.execute("SELECT * FROM occurrences WHERE date=? AND prayer=?",
                                 (day.isoformat(), prayer)).fetchone()
                if old:
                    if old["status"] in ("PENDING", "DISABLED") and old["scheduled_at"] > now:
                        # A correction into the past is recorded, never sounded late on activation.
                        status = ("PENDING" if enabled else "DISABLED") if scheduled_at > now else "MISSED_DOWNTIME"
                        db.execute("UPDATE occurrences SET scheduled_time=?,effective_time=?,scheduled_at=?,"
                                   "timing_source=?,enabled=?,status=? WHERE id=?",
                                   (normal, effective, scheduled_at, source, int(enabled), status, old["id"]))
                    continue
                legacy = db.execute("SELECT 1 FROM legacy_triggers WHERE date=? AND prayer=?",
                                    (day.isoformat(), prayer)).fetchone()
                status = "FAILED" if legacy else ("PENDING" if enabled else "DISABLED")
                failure = "Legacy trigger claimed; completion unknown" if legacy else None
                db.execute("INSERT INTO occurrences(date,prayer,scheduled_time,effective_time,scheduled_at,"
                           "timing_source,enabled,status,failure_reason) VALUES (?,?,?,?,?,?,?,?,?)",
                           (day.isoformat(), prayer, normal, effective, scheduled_at, source,
                            int(enabled), status, failure))

    def refresh_schedule(self):
        today = self.now().astimezone(self.tz).date()
        errors = []
        # Materialize a month ahead: no network on the time-critical scheduler thread.
        for offset in range(35):
            if self.halt.is_set():
                break
            day = today + timedelta(days=offset)
            try:
                self.build_day(day, self.provider.fetch_date(day))
            except Exception as exc:
                log.warning("Schedule unavailable for %s: %s", day, exc)
                errors.append(f"Schedule unavailable for {day}")
                # Avoid 35 identical network timeouts during an outage.
                break
        self.schedule_warning = "; ".join(errors) or None
        self.last_refresh = self.now().isoformat()

    def _finish(self, db, status, reason=None):
        occurrence_id = self.active
        if occurrence_id is None:
            return
        db.execute("UPDATE occurrences SET status=?,completed_at=?,failure_reason=? WHERE id=? AND status='PLAYING'",
                   (status, self.now().isoformat(), reason, occurrence_id))
        self.store.event(db, status, reason or "", occurrence_id)
        self.active = None

    def tick(self):
        with self.lock:
            now = self.now()
            selected = None
            with self.store.connect(write=True) as db:
                if self.active is not None:
                    result = self.player.poll()
                    row = db.execute("SELECT started_at FROM occurrences WHERE id=?", (self.active,)).fetchone()
                    if row and (now - datetime.fromisoformat(row[0])).total_seconds() > 900:
                        self.player.stop()
                        self._finish(db, "FAILED", "Playback exceeded 15-minute safety limit")
                    elif result is not None:
                        self.player.finish()
                        self._finish(db, "PLAYED" if result == 0 else "FAILED",
                                     None if result == 0 else f"Player exited with code {result}")
                due = db.execute("SELECT * FROM occurrences WHERE status='PENDING' AND scheduled_at<=? "
                                 "ORDER BY scheduled_at,id", (now.isoformat(),)).fetchall()
                for row in due:
                    status, reason = None, None
                    elapsed = (now - datetime.fromisoformat(row["scheduled_at"])).total_seconds()
                    if not self.store.get(db, f"enabled:{row['prayer']}", True):
                        status, reason = "DISABLED", "Prayer disabled"
                    elif db.execute("SELECT 1 FROM snooze_windows WHERE starts_at<=? AND ends_at>?",
                                    (row["scheduled_at"], row["scheduled_at"])).fetchone():
                        status, reason = "SUPPRESSED", "Meeting snooze"
                    elif elapsed > self.cfg.trigger_window_seconds:
                        status, reason = "MISSED_DOWNTIME", "Outside late-start grace period"
                    elif self.active is not None:
                        status, reason = "FAILED", "Another Azan is already playing"
                    if status:
                        db.execute("UPDATE occurrences SET status=?,suppression_reason=?,completed_at=? WHERE id=?",
                                   (status, reason, now.isoformat(), row["id"]))
                        self.store.event(db, status, reason, row["id"])
                        continue
                    try:
                        audio = self.collections.select(db, row["prayer"])
                    except ValueError as exc:
                        db.execute("UPDATE occurrences SET status='FAILED',failure_reason=?,completed_at=? WHERE id=?",
                                   (str(exc), now.isoformat(), row["id"]))
                        self.store.event(db, "FAILED", str(exc), row["id"])
                        continue
                    claimed = db.execute("UPDATE occurrences SET status='PLAYING',audio_file=?,started_at=? "
                                         "WHERE id=? AND status='PENDING'", (audio, now.isoformat(), row["id"]))
                    if claimed.rowcount:
                        selected = (row["id"], audio, self.store.get(db, "volume", 70))
                        self.active = row["id"]
                        self.store.event(db, "PLAYING", Path(audio).name, row["id"])
                        break
            # Claim and rotation commit BEFORE touching hardware, still under the control lock.
            if selected:
                try:
                    self.player.start(selected[1], selected[2])
                    with self.store.connect(write=True) as db:
                        db.execute("UPDATE occurrences SET started_at=? WHERE id=? AND status='PLAYING'",
                                   (self.now().isoformat(), selected[0]))
                        self.store.event(db, "audio_started", Path(selected[1]).name, selected[0])
                except Exception as exc:
                    log.exception("Audio start failed")
                    with self.store.connect(write=True) as db:
                        self._finish(db, "FAILED", f"Audio start failed: {type(exc).__name__}")
            self.heartbeat = now.isoformat()

    def set_volume(self, volume):
        if type(volume) is not int or not 0 <= volume <= 100:
            raise ValueError("Volume must be an integer from 0 to 100")
        with self.lock, self.store.connect(write=True) as db:
            self.store.put(db, "volume", volume)
            self.store.event(db, "volume_changed", str(volume))

    def set_enabled(self, prayer, enabled):
        if prayer not in self.cfg.prayers or type(enabled) is not bool:
            raise ValueError("Invalid prayer or enabled value")
        with self.lock, self.store.connect(write=True) as db:
            self.store.put(db, f"enabled:{prayer}", enabled)
            db.execute("UPDATE occurrences SET enabled=?,status=? WHERE prayer=? "
                       "AND status IN ('PENDING','DISABLED') AND scheduled_at>?",
                       (int(enabled), "PENDING" if enabled else "DISABLED", prayer, self.now().isoformat()))
            self.store.event(db, "prayer_enabled" if enabled else "prayer_disabled", prayer)

    def snooze(self, until):
        if until.tzinfo is None:
            raise ValueError("Snooze end must include timezone")
        until = until.astimezone(timezone.utc)
        with self.lock, self.store.connect(write=True) as db:
            now = self.now()
            if not now < until <= now + timedelta(days=1):
                raise ValueError("Snooze must end within the next 24 hours")
            db.execute("INSERT INTO snooze_windows(starts_at,ends_at) VALUES (?,?)",
                       (now.isoformat(), until.isoformat()))
            self.store.event(db, "snoozed", until.isoformat())

    def resume(self):
        with self.lock, self.store.connect(write=True) as db:
            now = self.now().isoformat()
            db.execute("UPDATE snooze_windows SET ends_at=? WHERE ends_at>?", (now, now))
            self.store.event(db, "resumed")

    def skip(self, occurrence_id):
        with self.lock, self.store.connect(write=True) as db:
            result = db.execute("UPDATE occurrences SET status='SKIPPED',suppression_reason='Skipped by user',"
                                "completed_at=? WHERE id=? AND status='PENDING' AND scheduled_at>?",
                                (self.now().isoformat(), occurrence_id, self.now().isoformat()))
            if not result.rowcount:
                raise ValueError("Only an upcoming pending occurrence can be skipped")
            self.store.event(db, "SKIPPED", "Skipped by user", occurrence_id)

    def stop_audio(self, shutdown=False):
        with self.lock:
            if self.active is not None:
                # Completion that won the race with Stop must remain a successful completion.
                result = self.player.poll()
                self.player.stop()
                with self.store.connect(write=True) as db:
                    if result == 0:
                        self._finish(db, "PLAYED")
                    else:
                        self._finish(db, "FAILED" if shutdown else "STOPPED_BY_USER",
                                     "Service shutting down" if shutdown else None)

    def activate_profile(self, profile_id, active):
        with self.lock:
            self.tick()  # Resolve due occurrences before changing future timetable entries.
            with self.store.connect(write=True) as db:
                self.ramadan.activate(db, profile_id, active)
                now = self.now().isoformat()
                rows = db.execute("SELECT * FROM occurrences WHERE status IN ('PENDING','DISABLED') "
                                  "AND scheduled_at>?", (now,)).fetchall()
                for row in rows:
                    effective, source = self._effective(db, row["date"], row["prayer"], row["scheduled_time"])
                    target = self.timestamp(row["date"], effective)
                    status = row["status"] if target > now else "MISSED_DOWNTIME"
                    db.execute("UPDATE occurrences SET effective_time=?,scheduled_at=?,timing_source=?,status=? WHERE id=?",
                               (effective, target, source, status, row["id"]))
            self.refresh_requested.set()

    def settings(self):
        with self.store.connect() as db:
            now = self.now().isoformat()
            snooze = db.execute("SELECT MAX(ends_at) FROM snooze_windows WHERE starts_at<=? AND ends_at>?",
                                (now, now)).fetchone()[0]
            return {"volume": self.store.get(db, "volume", 70), "snooze_until": snooze,
                    "enabled": {p: self.store.get(db, f"enabled:{p}", True) for p in self.cfg.prayers},
                    "timezone": self.cfg.timezone, "city": self.cfg.city, "country": self.cfg.country,
                    "method": self.cfg.method, "school": self.cfg.school,
                    "grace_seconds": self.cfg.trigger_window_seconds,
                    "audio_mode": self.cfg.audio_mode, "volume_applies": "Next playback"}

    def history(self, day):
        day = date.fromisoformat(day).isoformat()
        rows = self.store.rows("SELECT * FROM occurrences WHERE date=? ORDER BY scheduled_at", (day,))
        for row in rows:
            row["audio_file"] = Path(row["audio_file"]).name if row["audio_file"] else None
        counts = Counter(row["status"] for row in rows)
        return {"date": day, "occurrences": rows, "counts": dict(counts), "scheduled": len(rows)}

    def status(self):
        with self.lock:
            now = self.now()
            result = self.history(now.astimezone(self.tz).date().isoformat())
            upcoming = self.store.rows("SELECT * FROM occurrences WHERE status='PENDING' AND scheduled_at>? "
                                       "ORDER BY scheduled_at LIMIT 1", (now.isoformat(),))
            result.update(now=now.isoformat(), settings=self.settings(),
                          next=upcoming[0] if upcoming else None, playing=self.active,
                          health=self.health())
            return result

    def health(self):
        now = self.now()
        alive = self.heartbeat is not None and (
            now - datetime.fromisoformat(self.heartbeat)).total_seconds() < max(30, self.cfg.check_interval_seconds * 3)
        today = now.astimezone(self.tz).date().isoformat()
        known = self.store.rows("SELECT COUNT(*) AS n FROM occurrences WHERE date=?", (today,))[0]["n"]
        warnings = list(self.collections.warnings)
        warnings.extend(self.host_health["warnings"])
        for warning in (self.schedule_warning, self.runtime_warning, getattr(self.provider, "warning", None)):
            if warning:
                warnings.append(warning)
        if self.cfg.audio_mode == "console":
            warnings.append("Console simulation: no physical audio")
        return {"ok": alive and known == len(self.cfg.prayers) and not warnings,
                "database": "ok", "scheduler_alive": alive, "heartbeat": self.heartbeat,
                "schedule_days": self.store.rows("SELECT COUNT(DISTINCT date) AS n FROM occurrences WHERE date>=?", (today,))[0]["n"],
                "last_refresh": self.last_refresh, "warnings": warnings,
                "clock_sync": self.host_health["clock_sync"],
                "audio_device": self.host_health["audio_device"], "timezone": self.cfg.timezone}

    def start(self):
        self.recover()

        def scheduler_loop():
            while not self.halt.is_set():
                try:
                    self.tick()
                    self.runtime_warning = None
                except Exception:
                    self.runtime_warning = "Scheduler error; inspect service logs"
                    log.exception("Scheduler tick failed")
                self.halt.wait(self.cfg.check_interval_seconds)

        def schedule_loop():
            last_day, refresh_at, audio_at = None, 0, 0
            while not self.halt.is_set():
                current_day = self.now().astimezone(self.tz).date()
                if (current_day != last_day or time.monotonic() >= refresh_at
                        or self.refresh_requested.is_set()):
                    self.refresh_requested.clear()
                    try:
                        self.refresh_schedule()
                    except Exception:
                        self.schedule_warning = "Schedule refresh failed; inspect service logs"
                        log.exception("Schedule refresh failed")
                    last_day = current_day
                    refresh_at = time.monotonic() + (300 if self.schedule_warning else 3600)
                if time.monotonic() >= audio_at:
                    self.host_health = probe_host(self.cfg)
                    try:
                        # Validation is off the scheduler thread; swap the complete snapshot atomically.
                        collections = AudioCollections(self.cfg)
                        with self.lock:
                            self.collections = collections
                    except Exception:
                        log.exception("Audio collection refresh failed")
                    audio_at = time.monotonic() + 60
                self.halt.wait(1)

        self.threads = [threading.Thread(target=fn, name=name, daemon=True)
                        for fn, name in ((scheduler_loop, "azan-scheduler"), (schedule_loop, "azan-calendar"))]
        for thread in self.threads:
            thread.start()

    def close(self):
        self.halt.set()
        self.stop_audio(shutdown=True)
        for thread in self.threads:
            thread.join(timeout=25)
