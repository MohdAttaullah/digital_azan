"""Durable state. Every connection is short-lived; mutations are transactional."""
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, date
from pathlib import Path

log = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path, migrate=True):
        self.path = Path(path)
        if not migrate and not self.path.is_file():
            raise ValueError("Database does not exist")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
        if migrate:
            self.migrate()

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def migrate(self):
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            migrations = sorted((Path(__file__).parent / "migrations").glob("*.sql"))
            if version > len(migrations):
                raise RuntimeError("Database is newer than this application; restore compatible release")
            for index, path in enumerate(migrations, 1):
                if index > version:
                    db.executescript("BEGIN IMMEDIATE;\n" + path.read_text()
                                     + f"\nPRAGMA user_version={index};\nCOMMIT;")

    @staticmethod
    def get(db, key, default=None):
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    @staticmethod
    def put(db, key, value):
        db.execute("INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (key, json.dumps(value)))

    @staticmethod
    def event(db, action, detail="", occurrence_id=None, at=None):
        db.execute("INSERT INTO events(at,action,occurrence_id,detail) VALUES (?,?,?,?)",
                   (at or utcnow(), action, occurrence_id, detail))
        log.info("%s occurrence=%s %s", action, occurrence_id, detail)

    def rows(self, sql, params=()):
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, params)]

    def import_legacy(self, state_path, ramadan_enabled):
        from app.ramadan_overrides import RAMADAN_2026_LOCAL
        with self.connect(write=True) as db:
            if self.get(db, "legacy_imported", False):
                return
            path = Path(state_path)
            if path.exists():
                state = json.loads(path.read_text(encoding="utf-8-sig"))
                day = date.fromisoformat(state["date"]).isoformat()
                for prayer, triggered in state["triggered"].items():
                    if triggered:
                        db.execute("INSERT OR IGNORE INTO legacy_triggers VALUES (?,?)", (day, prayer))
            cur = db.execute("INSERT INTO profiles(name,source,notes,active,created_at) VALUES (?,?,?,?,?)",
                             ("Ramadan 2026", "Darul Uloom Ziya-e-Mustafa",
                              "Migrated existing timetable; evening Maghrib normalized to 24-hour time.",
                              int(ramadan_enabled), utcnow()))
            for day, (fajr, maghrib) in RAMADAN_2026_LOCAL.items():
                h, m = map(int, maghrib.split(":"))
                fh, fm = map(int, fajr.split(":"))
                db.execute("INSERT INTO overrides(profile_id,date,fajr,maghrib) VALUES (?,?,?,?)",
                           (cur.lastrowid, day, f"{fh:02}:{fm:02}", f"{h + 12:02}:{m:02}"))
            self.put(db, "legacy_imported", True)
            self.event(db, "legacy_imported", "Trigger claims preserved; historical completion unknown")

    def backup(self, destination):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.resolve() == self.path.resolve():
            raise ValueError("Backup destination must differ from database")
        with self.connect() as source, sqlite3.connect(destination) as target:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup integrity check failed")
