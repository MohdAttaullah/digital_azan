"""Opt-in network contract check against Aladhan's original daily endpoint."""
import argparse
import json
from datetime import date

import requests

from app.config import load_config
from app.prayer_times import PrayerTimesClient, clean_timings


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("date", type=date.fromisoformat)
    args = parser.parse_args()
    cfg = load_config()
    client = PrayerTimesClient(cfg.city, cfg.country, cfg.method, timezone=cfg.timezone,
                               school=cfg.school, cache_dir=cfg.data_dir / "cache")
    monthly = client.fetch_date(args.date)
    response = requests.get(f"https://api.aladhan.com/v1/timingsByCity/{args.date:%d-%m-%Y}",
                            params=client.params, timeout=(5, 15))
    response.raise_for_status()
    daily = clean_timings(response.json()["data"]["timings"])
    if monthly != daily:
        raise RuntimeError(f"Provider endpoints disagree: monthly={monthly}, daily={daily}")
    print(json.dumps({"date": args.date.isoformat(), "matched": True, "timings": daily}, indent=2))
