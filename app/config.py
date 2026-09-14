"""Central configuration; legacy YAML remains supported."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

PRAYERS = ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha")
DEFAULT_TIMEZONE = "Asia/Kolkata"
ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class AppConfig:
    city: str = "Hyderabad"
    country: str = "India"
    method: int = 1
    timezone: str = DEFAULT_TIMEZONE
    prayers: tuple[str, ...] = PRAYERS
    check_interval_seconds: int = 2
    trigger_window_seconds: int = 90
    audio_mode: str = "system"
    audio_files: dict = field(default_factory=lambda: {
        "fajr": str(ROOT / "assets/audio/azan_fajr.wav"),
        "default": str(ROOT / "assets/audio/azan.wav"),
    })
    ramadan_override_enabled: bool = True
    data_dir: Path = ROOT / "state"
    normal_dir: Path | None = None
    fajr_dir: Path | None = None
    audio_output: str = "pulse"
    host: str = "0.0.0.0"
    port: int = 8080
    control_token: str = ""
    school: int = 0
    allowed_hosts: tuple[str, ...] = ()

    @property
    def database(self):
        return self.data_dir / "azan.sqlite3"


def load_config(path=None) -> AppConfig:
    path = Path(path or os.getenv("AZAN_CONFIG", ROOT / "config/config.yaml"))
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    loc, runtime = raw.get("location", {}), raw.get("runtime", {})
    audio, web = raw.get("audio", {}), raw.get("web", {})

    def resolve(value):
        p = Path(value).expanduser()
        return p if p.is_absolute() else ROOT / p

    files = {k: str(resolve(v)) for k, v in audio.get("files", {}).items()}
    paths = audio.get("collections", {})
    cfg = AppConfig(
        city=str(loc.get("city", "Hyderabad")),
        country=str(loc.get("country", "India")), method=int(loc.get("method", 1)),
        school=int(loc.get("school", 0)),
        timezone=os.getenv("AZAN_TIMEZONE", runtime.get("timezone", DEFAULT_TIMEZONE)),
        prayers=tuple(raw.get("behavior", {}).get("prayers", PRAYERS)),
        check_interval_seconds=int(runtime.get("check_interval_seconds", 2)),
        trigger_window_seconds=int(runtime.get("trigger_window_seconds", 90)),
        audio_mode=os.getenv("AZAN_AUDIO_MODE", audio.get("mode", "system")),
        audio_files=files or AppConfig().audio_files,
        ramadan_override_enabled=bool(raw.get("ramadan_override", {}).get("enabled", False)),
        data_dir=resolve(os.getenv("AZAN_DATA_DIR", runtime.get("data_dir", "state"))),
        normal_dir=resolve(paths["normal"]) if paths.get("normal") else None,
        fajr_dir=resolve(paths["fajr"]) if paths.get("fajr") else None,
        audio_output=audio.get("output", "pulse"),
        host=os.getenv("AZAN_HOST", web.get("host", "0.0.0.0")),
        port=int(os.getenv("AZAN_PORT", web.get("port", 8080))),
        control_token=os.getenv("AZAN_CONTROL_TOKEN", ""),
        allowed_hosts=tuple(h.strip().lower() for h in os.getenv("AZAN_ALLOWED_HOSTS", "").split(",") if h.strip()),
    )
    ZoneInfo(cfg.timezone)
    if (not cfg.prayers or len(set(cfg.prayers)) != len(cfg.prayers)
            or not set(cfg.prayers) <= set(PRAYERS)):
        raise ValueError("behavior.prayers must contain unique supported prayers")
    if not 1 <= cfg.check_interval_seconds <= 30:
        raise ValueError("check_interval_seconds must be 1-30")
    if not cfg.check_interval_seconds <= cfg.trigger_window_seconds <= 300:
        raise ValueError("trigger_window_seconds must cover polling and be <= 300")
    if cfg.audio_mode not in ("system", "console") or cfg.school not in (0, 1):
        raise ValueError("Invalid audio mode or school")
    if not 1 <= cfg.port <= 65535:
        raise ValueError("Invalid web port")
    return cfg
