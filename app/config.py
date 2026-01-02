from dataclasses import dataclass
from pathlib import Path
from typing import List, Any, Dict

import yaml


@dataclass(frozen=True)
class AppConfig:
    city: str
    country: str
    method: int
    timezone: str
    prayers: list[str]
    check_interval_seconds: int
    trigger_window_seconds: int
    audio_mode: str
    audio_files: dict[str, str]




def _require(d: Dict[str, Any], key: str, ctx: str) -> Any:
    if key not in d:
        raise ValueError(f"Missing required key '{key}' in {ctx}")
    return d[key]


def load_config(path: str | Path = "config/config.yaml") -> AppConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path.resolve()}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    loc = _require(raw, "location", "root")
    runtime = _require(raw, "runtime", "root")
    behavior = _require(raw, "behavior", "root")

    city = str(_require(loc, "city", "location")).strip()
    country = str(_require(loc, "country", "location")).strip()
    method = int(_require(loc, "method", "location"))

    timezone = str(_require(runtime, "timezone", "runtime")).strip()

    check_interval_seconds = int(_require(runtime, "check_interval_seconds", "runtime"))
    trigger_window_seconds = int(_require(runtime, "trigger_window_seconds", "runtime"))


    prayers = _require(behavior, "prayers", "behavior")

    audio = _require(raw, "audio", "root")

    audio_mode = str(_require(audio, "mode", "audio")).strip()
    audio_files = _require(audio, "files", "audio")
    if not isinstance(audio_files, dict):
        raise ValueError("audio.files must be a mapping")


    if not isinstance(prayers, list) or not prayers:
        raise ValueError("behavior.prayers must be a non-empty list")

    prayers = [str(p).strip() for p in prayers]

    return AppConfig(
        city=city,
        country=country,
        method=method,
        timezone=timezone,
        prayers=prayers,
        check_interval_seconds=check_interval_seconds,
        trigger_window_seconds=trigger_window_seconds,
        audio_mode=audio_mode,
        audio_files=audio_files,
    )


