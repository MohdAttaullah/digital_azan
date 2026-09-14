import sqlite3
from pathlib import Path

import yaml

from app.storage import Store
from scripts.seed_install import seed
from tests.conftest import wav


def test_install_preserves_legacy_location_audio_and_existing_shared_data(tmp_path):
    legacy, install = tmp_path / "legacy", tmp_path / "install"
    (legacy / "config").mkdir(parents=True)
    (legacy / "audio").mkdir()
    wav(legacy / "audio/custom.wav")
    wav(legacy / "audio/fajr.wav")
    (legacy / "config/config.yaml").write_text(yaml.safe_dump({
        "location": {"city": "Custom City", "country": "India", "method": 1},
        "runtime": {"timezone": "Asia/Kolkata", "check_interval_seconds": 20, "trigger_window_seconds": 90},
        "audio": {"mode": "system", "files": {"default": "audio/custom.wav", "fajr": "audio/fajr.wav"}}}))
    seed(legacy, install)
    cfg_path = install / "shared/config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    assert cfg["location"]["city"] == "Custom City"
    assert (install / "shared/audio/normal/custom.wav").exists()
    assert (install / "shared/audio/fajr/fajr.wav").exists()
    cfg_path.write_text("operator config")
    seed(legacy, install)
    assert cfg_path.read_text() == "operator config"


def test_backup_does_not_apply_new_migrations(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript(Path("app/migrations/001_initial.sql").read_text())
        db.execute("PRAGMA user_version=1")
    Store(path, migrate=False).backup(tmp_path / "backup.sqlite3")
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
