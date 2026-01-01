from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Optional

from app.state import load_state, save_state


class PrayerScheduler:
    def __init__(self, timezone: str, trigger_window_seconds: int):
        self.tz = ZoneInfo(timezone)
        self.window = trigger_window_seconds

    @staticmethod
    def _parse_today_time(tz: ZoneInfo, hhmm: str) -> datetime:
        # hhmm like "05:42" (ignore seconds / annotations)
        hhmm = hhmm.strip()[:5]
        h, m = map(int, hhmm.split(":"))
        now = datetime.now(tz)
        return now.replace(hour=h, minute=m, second=0, microsecond=0)

    def check_due_prayer(
        self,
        timings: Dict[str, str],
        prayers: list[str],
    ) -> Optional[str]:
        """
        Returns the prayer name if one should trigger now, else None.
        """
        now = datetime.now(self.tz)
        state = load_state()

        for prayer in prayers:
            if state["triggered"].get(prayer):
                continue

            target = self._parse_today_time(self.tz, timings[prayer])
            diff = (now - target).total_seconds()

            # Trigger only AFTER prayer time, within grace window
            if 0 <= diff <= self.window:
                state["triggered"][prayer] = True
                save_state(state)
                return prayer

        return None
