import json
from datetime import date
from pathlib import Path
from typing import Dict, Optional


CACHE_DIR = Path("state")


def _cache_path_for(d: date) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"prayer_times_{d.isoformat()}.json"


def load_today_cache() -> Optional[Dict[str, str]]:
    path = _cache_path_for(date.today())
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # Corrupt cache → ignore
        return None


def save_today_cache(timings: Dict[str, str]) -> None:
    path = _cache_path_for(date.today())
    path.write_text(json.dumps(timings, indent=2), encoding="utf-8")
