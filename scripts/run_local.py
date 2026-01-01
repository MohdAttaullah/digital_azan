from app.config import load_config
from app.prayer_times import PrayerTimesClient


if __name__ == "__main__":
    cfg = load_config()

    client = PrayerTimesClient(
        city=cfg.city,
        country=cfg.country,
        method=cfg.method,
    )

    timings = client.fetch_today()

    print("Today's Prayer Times:")
    for p in cfg.prayers:
        print(f"{p}: {timings[p]}")
