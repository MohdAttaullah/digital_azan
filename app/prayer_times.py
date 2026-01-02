# app/prayer_times.py

import json
import requests
from datetime import date
from pathlib import Path


class PrayerTimesClient:
    def __init__(self, city: str, country: str, method: int):
        self.city = city
        self.country = country
        self.method = method
        self.cache_dir = Path("app/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_file(self) -> Path:
        today = date.today().isoformat()
        return self.cache_dir / f"prayer_times_{today}.json"

    def _save_cache(self, timings: dict):
        payload = {
            "date": date.today().isoformat(),
            "city": self.city,
            "country": self.country,
            "method": self.method,
            "timings": timings,
        }
        self._cache_file().write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def _load_cache(self) -> dict:
        cache_file = self._cache_file()
        if not cache_file.exists():
            raise FileNotFoundError("No cached prayer times available")
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        return payload["timings"]

    def fetch_today(self) -> dict:
        url = "https://api.aladhan.com/v1/timingsByCity"
        params = {
            "city": self.city,
            "country": self.country,
            "method": self.method,
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            timings = data["data"]["timings"]

            # Keep only required prayers
            cleaned = {
                k: timings[k]
                for k in ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha")
            }

            self._save_cache(cleaned)
            print("[CACHE] Prayer times fetched from API")
            return cleaned

        except Exception as e:
            print(f"[WARN] API failed, using cached timings: {e}")
            return self._load_cache()
