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
    prayers: List[str]


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

    prayers = _require(behavior, "prayers", "behavior")
    if not isinstance(prayers, list) or not prayers:
        raise ValueError("behavior.prayers must be a non-empty list")

    prayers = [str(p).strip() for p in prayers]

    return AppConfig(
        city=city,
        country=country,
        method=method,
        timezone=timezone,
        prayers=prayers,
    )
