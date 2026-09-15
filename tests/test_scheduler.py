from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.controller import Controller
from app.instance import InstanceLock
from tests.conftest import FakePlayer, TIMINGS


def occurrence(c, prayer="Fajr", day="2027-03-05"):
    return next(r for r in c.history(day)["occurrences"] if r["prayer"] == prayer)


def test_due_once_and_completion(rig):
    c, clock, player = rig
    clock.set("2027-03-05T05:21:00+05:30")
    c.tick()
    c.tick()
    assert len(player.starts) == 1
    assert Path(player.starts[0][0]).name == "fajr_1.wav"
    assert occurrence(c)["status"] == "PLAYING"
    player.result = 0
    c.tick()
    c.tick()
    assert occurrence(c)["status"] == "PLAYED"
    assert c.history("2027-03-05")["counts"]["PLAYED"] == 1


def test_restart_after_completion_never_replays(rig):
    c, clock, p = rig
    clock.set("2027-03-05T05:21:00+05:30")
    c.tick()
    p.result = 0
    c.tick()
    fresh = FakePlayer()
    restarted = Controller(c.cfg, c.store, c.provider, fresh, clock)
    restarted.recover()
    restarted.build_day(date(2027, 3, 5), TIMINGS)
    restarted.tick()
    assert fresh.starts == []
    assert occurrence(restarted)["status"] == "PLAYED"


def test_interrupted_claim_fails_without_replay(rig):
    c, clock, _ = rig
    clock.set("2027-03-05T05:21:00+05:30")
    c.tick()
    fresh = FakePlayer()
    restarted = Controller(c.cfg, c.store, c.provider, fresh, clock)
    restarted.recover()
    restarted.tick()
    assert fresh.starts == []
    assert occurrence(restarted)["status"] == "FAILED"


@pytest.mark.parametrize("seconds,expected", [(0, "PLAYING"), (90, "PLAYING"), (91, "MISSED_DOWNTIME"), (1500, "MISSED_DOWNTIME")])
def test_grace(rig, seconds, expected):
    c, clock, _ = rig
    clock.set("2027-03-05T05:21:00+05:30")
    clock.value += timedelta(seconds=seconds)
    c.tick()
    assert occurrence(c)["status"] == expected


def test_disable_survives_and_enable_only_future(rig):
    c, clock, p = rig
    c.set_enabled("Asr", False)
    clock.set("2027-03-05T16:39:00+05:30")
    c.tick()
    assert occurrence(c, "Asr")["status"] == "DISABLED"
    c.set_enabled("Asr", True)
    c.tick()
    assert p.starts == []
    c.build_day(date(2027, 3, 6), TIMINGS)
    assert occurrence(c, "Asr", "2027-03-06")["status"] == "PENDING"


def test_snooze_expired_during_downtime_still_suppressed(rig):
    c, clock, p = rig
    clock.set("2027-03-05T16:00:00+05:30")
    c.snooze(clock.value + timedelta(hours=1))
    clock.set("2027-03-05T17:01:00+05:30")
    c.tick()
    assert occurrence(c, "Asr")["status"] == "SUPPRESSED"
    c.resume()
    c.tick()
    assert p.starts == []
    assert c.settings()["snooze_until"] is None


def test_resume_before_due_allows_playback(rig):
    c, clock, p = rig
    c.snooze(clock.value + timedelta(hours=2))
    c.resume()
    clock.set("2027-03-05T05:21:00+05:30")
    c.tick()
    assert len(p.starts) == 1


def test_snooze_does_not_stop_active_audio(rig):
    c, clock, p = rig
    clock.set("2027-03-05T05:21:00+05:30")
    c.tick()
    c.snooze(clock.value + timedelta(minutes=30))
    assert not p.stopped
    c.stop_audio()
    assert p.stopped
    assert occurrence(c)["status"] == "STOPPED_BY_USER"
    assert occurrence(c)["completed_at"]
    c.tick()
    assert len(p.starts) == 1


def test_audio_test_uses_volume_stops_and_does_not_advance_rotation(rig):
    c, _, player = rig
    c.set_volume(25)
    result = c.start_audio_test("normal")
    assert result["audio_file"] == "azan_1.wav"
    assert result["volume"] == 25
    assert c.status()["playing"] == "test"
    assert c.store.rows("SELECT * FROM rotations") == []
    c.stop_audio()
    assert player.stopped
    assert c.status()["playing"] is None
    actions = [row["action"] for row in c.store.rows("SELECT action FROM events ORDER BY id")]
    assert "audio_test_started" in actions
    assert "audio_test_stopped" in actions


def test_audio_test_is_blocked_near_prayer(rig):
    c, clock, _ = rig
    clock.set("2027-03-05T05:12:00+05:30")
    with pytest.raises(ValueError, match="within 10 minutes"):
        c.start_audio_test("normal")


def test_skip_one_day(rig):
    c, clock, _ = rig
    c.skip(occurrence(c, "Maghrib")["id"])
    c.build_day(date(2027, 3, 6), TIMINGS)
    clock.set("2027-03-05T18:34:00+05:30")
    c.tick()
    assert occurrence(c, "Maghrib")["status"] == "SKIPPED"
    assert occurrence(c, "Maghrib", "2027-03-06")["status"] == "PENDING"


def test_concurrent_ticks_and_controls(rig):
    c, clock, p = rig
    clock.set("2027-03-05T05:21:00+05:30")
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: c.tick(), range(24)))
    assert len(p.starts) == 1
    with pytest.raises(ValueError):
        c.skip(occurrence(c)["id"])


def test_failure_is_terminal(rig):
    c, clock, p = rig
    p.fail = True
    clock.set("2027-03-05T05:21:00+05:30")
    c.tick()
    p.fail = False
    c.tick()
    assert occurrence(c)["status"] == "FAILED"
    assert p.starts == []


def test_exit_failure_and_timeout(rig):
    c, clock, p = rig
    clock.set("2027-03-05T05:21:00+05:30")
    c.tick()
    p.result = 3
    c.tick()
    assert occurrence(c)["status"] == "FAILED"
    clock.set("2027-03-05T12:17:00+05:30")
    c.tick()
    clock.value += timedelta(minutes=16)
    c.tick()
    assert occurrence(c, "Dhuhr")["status"] == "FAILED"
    assert p.stopped


def test_midnight_and_tomorrow_next(rig):
    c, clock, _ = rig
    c.refresh_schedule()
    clock.set("2027-03-05T23:59:00+05:30")
    c.tick()
    assert c.status()["next"]["date"] == "2027-03-06"
    clock.set("2027-03-06T00:01:00+05:30")
    assert len(c.status()["occurrences"]) == 5


def test_timetable_change_does_not_replay_played(rig):
    c, clock, p = rig
    clock.set("2027-03-05T05:21:00+05:30")
    c.tick()
    p.result = 0
    c.tick()
    c.build_day(date(2027, 3, 5), dict(TIMINGS, Fajr="05:22"))
    clock.value += timedelta(minutes=1)
    c.tick()
    assert len(p.starts) == 1
    assert occurrence(c)["effective_time"] == "05:21"


def test_process_lock(tmp_path):
    first, second = InstanceLock(tmp_path / "lock"), InstanceLock(tmp_path / "lock")
    first.acquire()
    try:
        with pytest.raises(RuntimeError):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()
