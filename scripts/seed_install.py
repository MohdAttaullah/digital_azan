"""First-install configuration/audio migration. Never replaces shared user files."""
import shutil
import sys
from pathlib import Path

import yaml

from app.config import ROOT


def seed(legacy_root, install_root):
    legacy_root, install_root = Path(legacy_root), Path(install_root)
    destination = install_root / "shared/config.yaml"
    if destination.exists():
        return
    source = legacy_root / "config/config.yaml"
    if not source.is_file():
        source, legacy_root = ROOT / "config/config.yaml", ROOT
    cfg = yaml.safe_load(source.read_text(encoding="utf-8-sig"))
    audio = cfg["audio"]
    for collection, old_key in (("normal", "default"), ("fajr", "fajr")):
        target_dir = install_root / "shared/audio" / collection
        target_dir.mkdir(parents=True, exist_ok=True)
        folder = audio.get("collections", {}).get(collection)
        value = folder or audio.get("files", {}).get(old_key)
        candidates = []
        if value:
            old_path = Path(value)
            if not old_path.is_absolute():
                old_path = legacy_root / old_path
            candidates = list(old_path.iterdir()) if folder and old_path.is_dir() else [old_path]
        for old_file in candidates:
            target = target_dir / old_file.name
            if old_file.is_file() and not target.exists():
                shutil.copy2(old_file, target)
    cfg.setdefault("runtime", {})["data_dir"] = str(install_root / "shared/data")
    cfg["runtime"]["check_interval_seconds"] = 2
    audio["collections"] = {key: str(install_root / "shared/audio" / key) for key in ("normal", "fajr")}
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects a concurrently supplied operator configuration.
    with destination.open("x", encoding="utf-8") as file:
        yaml.safe_dump(cfg, file, sort_keys=False)


if __name__ == "__main__":
    seed(*sys.argv[1:])
