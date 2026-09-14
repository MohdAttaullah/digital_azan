"""Safe operator commands. Simulation is isolated in a temporary data directory."""
import argparse
import json
import tempfile
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.config import load_config
from app.controller import Controller
from app.instance import InstanceLock
from app.storage import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    backup = sub.add_parser("backup")
    backup.add_argument("destination", type=Path)
    schedule = sub.add_parser("schedule")
    schedule.add_argument("date", type=date.fromisoformat)
    sub.add_parser("simulate")
    args = parser.parse_args()
    cfg = load_config()
    if args.command == "backup":
        Store(cfg.database, migrate=False).backup(args.destination)
        print(f"Verified SQLite backup: {args.destination}")
    elif args.command == "migrate":
        lock = InstanceLock(cfg.data_dir / "controller.lock")
        lock.acquire()
        try:
            store = Store(cfg.database)
            store.import_legacy(cfg.data_dir / "scheduler_state.json", cfg.ramadan_override_enabled)
            print("Migrations and legacy import complete")
        finally:
            lock.release()
    elif args.command == "schedule":
        from app.prayer_times import PrayerTimesClient
        client = PrayerTimesClient(cfg.city, cfg.country, cfg.method, timezone=cfg.timezone,
                                   cache_dir=cfg.data_dir / "cache", school=cfg.school)
        print(json.dumps(client.fetch_date(args.date), indent=2))
        print("Standard calculation only; use the dashboard for effective overrides.")
    else:
        with tempfile.TemporaryDirectory(prefix="azan-simulation-") as folder:
            cfg = replace(cfg, data_dir=Path(folder), audio_mode="console")
            now = datetime(2027, 3, 5, 0, 0, tzinfo=timezone.utc)
            controller = Controller(cfg, clock=lambda: now)
            controller.build_day(date(2027, 3, 5), {
                "Fajr": "05:31", "Dhuhr": "12:17", "Asr": "16:39", "Maghrib": "18:34", "Isha": "19:34"})
            now += timedelta(minutes=1)
            controller.tick()
            controller.tick()
            print("SIMULATION ONLY — no production database or audio used")
            print(json.dumps(controller.history("2027-03-05"), indent=2))


if __name__ == "__main__":
    main()
