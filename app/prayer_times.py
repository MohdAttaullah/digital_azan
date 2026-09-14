"""Aladhan date-specific schedules, cached by location/method/timezone and month."""
import hashlib
import json
import logging
import re
import threading
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from app.config import DEFAULT_TIMEZONE, PRAYERS, ROOT

log = logging.getLogger(__name__)


def clean_timings(values):
    cleaned = {}
    for prayer in PRAYERS:
        match = re.match(r"^(\d{1,2}):(\d{2})(?:\s.*)?$", str(values[prayer]))
        if not match:
            raise ValueError(f"Invalid provider time for {prayer}")
        h, m = map(int, match.groups())
        if h > 23 or m > 59:
            raise ValueError(f"Invalid provider time for {prayer}")
        cleaned[prayer] = f"{h:02}:{m:02}"
    return cleaned


class PrayerTimesClient:
    def __init__(self, city, country, method, ramadan_override_enabled=False,
                 timezone=DEFAULT_TIMEZONE, cache_dir=None, school=0):
        self.city, self.country, self.method = city, country, method
        self.timezone, self.school = timezone, school
        self.cache_dir = Path(cache_dir or ROOT / "state/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.params = dict(city=city, country=country, method=method,
                           school=school, timezonestring=timezone)
        self.key = hashlib.sha256(json.dumps(self.params, sort_keys=True).encode()).hexdigest()[:16]
        self.lock = threading.Lock()
        self.warning = None

    def fetch_date(self, day: date):
        path = self.cache_dir / f"{self.key}_{day:%Y-%m}.json"
        with self.lock:
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    return clean_timings(data[day.isoformat()])
                except (ValueError, KeyError, TypeError):
                    log.warning("Ignoring invalid calendar cache %s", path.name)
            try:
                response = requests.get(
                    f"https://api.aladhan.com/v1/calendarByCity/{day.year}/{day.month}",
                    params=self.params, timeout=(5, 15))
                response.raise_for_status()
                rows = response.json()["data"]
                calendar = {}
                for row in rows:
                    d = datetime.strptime(row["date"]["gregorian"]["date"], "%d-%m-%Y").date()
                    if (d.year, d.month) != (day.year, day.month):
                        raise ValueError("Provider returned wrong month")
                    calendar[d.isoformat()] = clean_timings(row["timings"])
                result = calendar[day.isoformat()]
                temporary = path.with_suffix(".tmp")
                temporary.write_text(json.dumps(calendar), encoding="utf-8")
                temporary.replace(path)
                self.warning = None
                log.info("Cached calendar for %s", day.strftime("%Y-%m"))
                return result
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                self.warning = f"Prayer provider unavailable for {day.isoformat()}: {type(exc).__name__}"
                log.warning(self.warning)
                # Legacy daily files are usable only for the matching location and method.
                for folder in (self.cache_dir, ROOT / "app/cache"):
                    old = folder / f"prayer_times_{day.isoformat()}.json"
                    if old.exists():
                        try:
                            data = json.loads(old.read_text(encoding="utf-8"))
                            if (data.get("city"), data.get("country"), data.get("method")) == (
                                    self.city, self.country, self.method) and self.school == 0:
                                return clean_timings(data["timings"])
                        except (ValueError, KeyError, TypeError):
                            continue
                raise RuntimeError(self.warning) from exc

    def fetch_today(self):
        # Overrides belong to the durable schedule service, never the base cache.
        return self.fetch_date(datetime.now(ZoneInfo(self.timezone)).date())
