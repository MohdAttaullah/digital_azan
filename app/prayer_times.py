import requests
from typing import Dict

from app.cache import load_today_cache, save_today_cache


class PrayerTimesClient:
    BASE_URL = "https://api.aladhan.com/v1/timingsByCity"

    def __init__(self, city: str, country: str, method: int):
        self.city = city
        self.country = country
        self.method = method

    def fetch_today(self) -> Dict[str, str]:
        # 1) Try cache first
        cached = load_today_cache()
        if cached:
            return cached

        # 2) Fetch from API
        params = {
            "city": self.city,
            "country": self.country,
            "method": self.method,
        }

        response = requests.get(
            self.BASE_URL,
            params=params,
            timeout=10,
            allow_redirects=True,
        )
        response.raise_for_status()

        data = response.json()
        timings = data["data"]["timings"]

        result = {
            "Fajr": timings["Fajr"],
            "Dhuhr": timings["Dhuhr"],
            "Asr": timings["Asr"],
            "Maghrib": timings["Maghrib"],
            "Isha": timings["Isha"],
        }

        # 3) Save cache
        save_today_cache(result)
        return result
