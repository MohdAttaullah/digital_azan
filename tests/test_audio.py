from pathlib import Path

from app.audio.collections import AudioCollections
from tests.conftest import wav


def test_independent_rotation_persists(rig):
    c, _, _ = rig
    def pick(prayer):
        with c.store.connect(write=True) as db:
            return Path(c.collections.select(db, prayer)).name
    assert pick("Dhuhr") == "azan_1.wav"
    assert pick("Fajr") == "fajr_1.wav"
    assert pick("Asr") == "azan_2.wav"
    c.collections = AudioCollections(c.cfg)
    assert pick("Maghrib") == "azan_10.wav"
    assert pick("Fajr") == "fajr_2.wav"
    assert pick("Isha") == "azan_1.wav"


def test_added_removed_and_invalid_files(rig):
    c, _, _ = rig
    with c.store.connect(write=True) as db:
        c.collections.select(db, "Asr")
    (c.cfg.normal_dir / "azan_1.wav").unlink()
    wav(c.cfg.normal_dir / "azan_3.wav")
    (c.cfg.normal_dir / "bad.wav").write_text("bad audio")
    (c.cfg.normal_dir / "README.txt").write_text("not audio")
    c.collections.refresh()
    assert len(c.collections.files["normal"]) == 3
    assert len(c.collections.warnings) == 2
    with c.store.connect(write=True) as db:
        assert Path(c.collections.select(db, "Asr")).name == "azan_2.wav"


def test_no_fajr_fallback(rig):
    c, clock, p = rig
    for path in c.cfg.fajr_dir.iterdir():
        path.unlink()
    c.collections.refresh()
    clock.set("2027-03-05T05:21:00+05:30")
    c.tick()
    assert not p.starts
    assert c.history("2027-03-05")["occurrences"][0]["status"] == "FAILED"


def test_volume_persisted_and_sent_to_player(rig):
    c, clock, p = rig
    c.set_volume(25)
    clock.set("2027-03-05T05:21:00+05:30")
    c.tick()
    assert p.starts[0][1] == 25
    with c.store.connect() as db:
        assert c.store.get(db, "volume") == 25


def test_system_engine_software_volume_and_stop(monkeypatch, tmp_path):
    from app.audio.system import SystemAudioEngine
    calls = []
    class Process:
        def poll(self):
            return None
        def terminate(self):
            calls.append("terminate")
        def wait(self, timeout):
            calls.append("wait")
    monkeypatch.setattr("app.audio.system.subprocess.Popen", lambda args, **kw: (calls.append(args) or Process()))
    audio = tmp_path / "audio.wav"
    wav(audio)
    engine = SystemAudioEngine()
    engine.start(str(audio), 25)
    engine.stop()
    assert "--volume=25" in calls[0]
    assert calls[1:] == ["terminate", "wait"]


def test_mpd_resumed_on_start_failure_and_stop(rig, monkeypatch):
    from app.azan_player import AzanPlayer
    from tests.conftest import FakePlayer
    c, _, _ = rig
    engine = FakePlayer()
    player = AzanPlayer(c.cfg, engine=engine)
    player.use_mpd = True
    calls = []
    class Result:
        stdout = "[playing]"
    monkeypatch.setattr(player, "_mpc", lambda command: (calls.append(command) or Result()))
    engine.fail = True
    import pytest
    with pytest.raises(OSError):
        player.start("file.wav", 25)
    assert calls == ["status", "stop", "play"]
    calls.clear()
    engine.fail = False
    player.start("file.wav", 25)
    player.stop()
    player.finish()
    assert calls == ["status", "stop", "play"]
