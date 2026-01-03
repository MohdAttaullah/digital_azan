import time
import sys
from pathlib import Path

from app.config import load_config
from app.prayer_times import PrayerTimesClient
from app.scheduler import PrayerScheduler
from app.azan_player import AzanPlayer
from app.maintenance.cleanup import cleanup_old_event_files


if __name__ == "__main__":
    cfg = load_config()

    BASE_DIR = Path(__file__).resolve().parent.parent
    EVENTS_DIR = BASE_DIR / "state"

    cleanup_old_event_files(
        events_dir=EVENTS_DIR,
        keep_days=7,
    )

    azan_player = AzanPlayer(cfg)

    if "--test-azan" in sys.argv:
        print("Manual Azan test mode")
        azan_player.play("Magrib")
        sys.exit(0)

    client = PrayerTimesClient(
        city=cfg.city,
        country=cfg.country,
        method=cfg.method,
    )

    scheduler = PrayerScheduler(
        timezone=cfg.timezone,
        trigger_window_seconds=cfg.trigger_window_seconds,
    )

    timings = client.fetch_today()

    print("Scheduler running (Ctrl+C to stop)")
    print("Timings:", timings)

    while True:
        due = scheduler.check_due_prayer(timings, cfg.prayers)
        if due:
            print(f">>> TRIGGER NOW: {due}")
            azan_player.play(due)

        time.sleep(cfg.check_interval_seconds)
