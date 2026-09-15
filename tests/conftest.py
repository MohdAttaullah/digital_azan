import wave
from datetime import datetime

import pytest

from app.config import AppConfig
from app.controller import Controller
from app.storage import Store


TIMINGS = {"Fajr": "05:21", "Dhuhr": "12:17", "Asr": "16:39", "Maghrib": "18:34", "Isha": "19:34"}


def wav(path):
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"\x00\x00" * 800)


class Clock:
    def __init__(self):
        self.set("2027-03-05T04:00:00+05:30")

    def set(self, value):
        self.value = datetime.fromisoformat(value)

    def __call__(self):
        return self.value


class Provider:
    warning = None

    def fetch_date(self, day):
        return dict(TIMINGS)


class FakePlayer:
    def __init__(self):
        self.starts = []
        self.result = None
        self.stopped = False
        self.fail = False
        self.volume_changes = []

    def start(self, path, volume):
        if self.fail:
            raise OSError("fake hardware failure")
        self.starts.append((path, volume))
        self.result = None

    def poll(self):
        return self.result

    def finish(self):
        pass

    def set_volume(self, volume):
        self.volume_changes.append(volume)
        return True

    def stop(self):
        self.stopped = True


@pytest.fixture
def rig(tmp_path):
    normal, fajr = tmp_path / "normal", tmp_path / "fajr"
    normal.mkdir()
    fajr.mkdir()
    for name in ("azan_1.wav", "azan_2.wav", "azan_10.wav"):
        wav(normal / name)
    for name in ("fajr_1.wav", "fajr_2.wav"):
        wav(fajr / name)
    cfg = AppConfig(data_dir=tmp_path / "data", normal_dir=normal, fajr_dir=fajr, audio_mode="console")
    clock, player = Clock(), FakePlayer()
    controller = Controller(cfg, Store(cfg.database), Provider(), player, clock)
    controller.build_day(clock.value.date(), TIMINGS)
    return controller, clock, player
