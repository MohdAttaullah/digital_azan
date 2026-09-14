import json
import sqlite3
from datetime import date

import pytest
import requests

from app.prayer_times import PrayerTimesClient
from app.storage import Store
from tests.conftest import TIMINGS


def test_migrations_repeat_backup_and_legacy(tmp_path):
    path = tmp_path / "azan.sqlite3"
    legacy = tmp_path / "scheduler_state.json"
    legacy.write_text(json.dumps({"date": "2027-03-05", "triggered": {"Fajr": True}}))
    store = Store(path)
    store.import_legacy(legacy, True)
    store.import_legacy(legacy, True)
    assert len(store.rows("SELECT * FROM profiles")) == 1
    assert store.rows("SELECT * FROM overrides WHERE date='2026-03-05'")[0]["maghrib"] == "18:29"
    assert len(store.rows("SELECT * FROM legacy_triggers")) == 1
    Store(path)
    backup = tmp_path / "backup.sqlite3"
    store.backup(backup)
    assert Store(backup).rows("SELECT * FROM legacy_triggers") == store.rows("SELECT * FROM legacy_triggers")


def test_migrate_version_one_preserves_settings(tmp_path):
    from pathlib import Path
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript(Path("app/migrations/001_initial.sql").read_text())
        db.execute("PRAGMA user_version=1")
        db.execute("INSERT INTO settings VALUES ('volume','25')")
    store = Store(path)
    with store.connect() as db:
        assert store.get(db, "volume") == 25
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2


def test_corrupt_legacy_fails_closed(tmp_path):
    state = tmp_path / "scheduler_state.json"
    state.write_text("broken")
    with pytest.raises(ValueError):
        Store(tmp_path / "db").import_legacy(state, True)


def test_month_cache_offline_and_location_separation(monkeypatch, tmp_path):
    calls = []
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {"data": [{"date": {"gregorian": {"date": f"{d:02}-03-2027"}},
                              "timings": TIMINGS} for d in range(1, 32)]}
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()
    monkeypatch.setattr("app.prayer_times.requests.get", get)
    client = PrayerTimesClient("Hyderabad", "India", 1, cache_dir=tmp_path)
    assert client.fetch_date(date(2027, 3, 5)) == TIMINGS
    monkeypatch.setattr("app.prayer_times.requests.get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError()))
    assert client.fetch_date(date(2027, 3, 20)) == TIMINGS
    assert len(calls) == 1
    other = PrayerTimesClient("Delhi", "India", 1, cache_dir=tmp_path)
    with pytest.raises(RuntimeError):
        other.fetch_date(date(2027, 3, 5))
    assert calls[0][1]["params"]["method"] == 1
    assert calls[0][1]["params"]["school"] == 0


def test_invalid_provider_cache_never_used(monkeypatch, tmp_path):
    client = PrayerTimesClient("Test", "India", 1, cache_dir=tmp_path)
    (tmp_path / f"{client.key}_2027-03.json").write_text('{"2027-03-05":{"Fajr":"99:00"}}')
    monkeypatch.setattr("app.prayer_times.requests.get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError()))
    with pytest.raises(RuntimeError):
        client.fetch_date(date(2027, 3, 5))


def test_legacy_trigger_blocks_new_controller_playback(rig, tmp_path):
    c, clock, player = rig
    state = tmp_path / "legacy.json"
    state.write_text(json.dumps({"date": "2027-03-05", "triggered": {"Fajr": True}}))
    c.store.import_legacy(state, False)
    # Real migration imports legacy claims before materializing occurrences.
    with c.store.connect(write=True) as db:
        db.execute("DELETE FROM occurrences")
    c.build_day(date(2027, 3, 5), TIMINGS)
    clock.set("2027-03-05T05:21:00+05:30")
    c.tick()
    assert not player.starts
    assert c.history("2027-03-05")["occurrences"][0]["status"] == "FAILED"
