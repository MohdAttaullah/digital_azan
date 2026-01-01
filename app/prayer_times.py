import requests
from datetime import datetime
from typing import Dict


class PrayerTimesClient:
    BASE_URL = "https://api.aladhan.com/v1/timingsByCity"

    def __init__(self, city: str, country: str, method: int):
        self.city = city
        self.country = country
        self.method = method

    def fetch_today(self) -> Dict[str, str]:
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

        return {
            "Fajr": timings["Fajr"],
            "Dhuhr": timings["Dhuhr"],
            "Asr": timings["Asr"],
            "Maghrib": timings["Maghrib"],
            "Isha": timings["Isha"],
        }
