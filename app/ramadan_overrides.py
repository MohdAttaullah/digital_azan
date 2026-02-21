# app/ramadan_overrides.py
#
# Local Ramadan 2026 timetable for Hyderabad (Darul Uloom Ziya-e-Mustafa).
# Overrides Fajr (Sehr) and Maghrib (Iftar) with masjid-published times
# so they match the local printed timetable instead of the API values.

from datetime import date

# Mapping: date -> (Fajr/Sehr time, Maghrib/Iftar time)
RAMADAN_2026_LOCAL: dict[str, tuple[str, str]] = {
    # ---- February 2026 ----
    "2026-02-19": ("5:19", "6:25"),   # Ramzan 1
    "2026-02-20": ("5:18", "6:25"),   # Ramzan 2
    "2026-02-21": ("5:18", "6:26"),   # Ramzan 3
    "2026-02-22": ("5:18", "6:26"),   # Ramzan 4
    "2026-02-23": ("5:17", "6:27"),   # Ramzan 5
    "2026-02-24": ("5:17", "6:27"),   # Ramzan 6
    "2026-02-25": ("5:15", "6:27"),   # Ramzan 7
    "2026-02-26": ("5:15", "6:27"),   # Ramzan 8
    "2026-02-27": ("5:14", "6:28"),   # Ramzan 9
    "2026-02-28": ("5:14", "6:28"),   # Ramzan 10
    # ---- March 2026 ----
    "2026-03-01": ("5:13", "6:28"),   # Ramzan 11
    "2026-03-02": ("5:11", "6:28"),   # Ramzan 12
    "2026-03-03": ("5:11", "6:28"),   # Ramzan 13
    "2026-03-04": ("5:10", "6:29"),   # Ramzan 14
    "2026-03-05": ("5:10", "6:29"),   # Ramzan 15
    "2026-03-06": ("5:09", "6:29"),   # Ramzan 16
    "2026-03-07": ("5:08", "6:30"),   # Ramzan 17
    "2026-03-08": ("5:08", "6:30"),   # Ramzan 18
    "2026-03-09": ("5:07", "6:30"),   # Ramzan 19
    "2026-03-10": ("5:06", "6:30"),   # Ramzan 20
    "2026-03-11": ("5:05", "6:31"),   # Ramzan 21
    "2026-03-12": ("5:05", "6:31"),   # Ramzan 22
    "2026-03-13": ("5:04", "6:31"),   # Ramzan 23
    "2026-03-14": ("5:03", "6:31"),   # Ramzan 24
    "2026-03-15": ("5:02", "6:31"),   # Ramzan 25
    "2026-03-16": ("5:01", "6:32"),   # Ramzan 26
    "2026-03-17": ("5:00", "6:32"),   # Ramzan 27
    "2026-03-18": ("5:00", "6:32"),   # Ramzan 28
    "2026-03-19": ("4:59", "6:32"),   # Ramzan 29
    "2026-03-20": ("4:58", "6:33"),   # Ramzan 30
}


def apply_ramadan_overrides(timings: dict, enabled: bool = True) -> dict:
    """
    Replace Fajr and Maghrib in *timings* with local masjid values
    if today falls within Ramadan 2026 and the feature is enabled.

    Returns a (possibly modified) copy of the timings dict.
    """
    if not enabled:
        return timings

    today_key = date.today().isoformat()
    override = RAMADAN_2026_LOCAL.get(today_key)

    if override is None:
        return timings

    fajr_local, maghrib_local = override
    updated = dict(timings)
    updated["Fajr"] = fajr_local
    updated["Maghrib"] = maghrib_local

    print(f"[RAMADAN] Overriding Fajr → {fajr_local}, Maghrib → {maghrib_local}  (local timetable)")
    return updated
