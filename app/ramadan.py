"""Validated draft profiles. Import never activates a timetable."""
import csv
import io
import re
from datetime import date

from app.storage import utcnow


def validate_rows(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 62:
        raise ValueError("Enter 1–62 timetable rows")
    cleaned, seen, warnings = [], set(), []
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"Row {number}: expected a table row")
        raw_day = str(row.get("date", ""))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_day):
            raise ValueError(f"Row {number}: use Gregorian YYYY-MM-DD dates")
        day = date.fromisoformat(raw_day)
        if day in seen:
            raise ValueError(f"Duplicate date: {day}")
        seen.add(day)
        result = {"date": day.isoformat(), "notes": str(row.get("notes", ""))[:500]}
        for prayer in ("fajr", "maghrib"):
            value = str(row.get(prayer) or "").strip()
            if not value:
                result[prayer] = None
                warnings.append(f"{day}: missing {prayer}; standard calculation will be used")
                continue
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
                raise ValueError(f"{day}: {prayer} must be 24-hour HH:MM")
            if prayer == "fajr" and value >= "12:00":
                raise ValueError(f"{day}: Fajr must be before noon")
            if prayer == "maghrib" and value < "12:00":
                raise ValueError(f"{day}: Maghrib must be an evening 24-hour time")
            result[prayer] = value
        if not result["fajr"] and not result["maghrib"]:
            raise ValueError(f"{day}: enter at least one override")
        cleaned.append(result)
    ordered = sorted(seen)
    if [r["date"] for r in cleaned] != sorted(r["date"] for r in cleaned):
        warnings.append("Rows were not chronological; preview is sorted by date")
    for left, right in zip(ordered, ordered[1:]):
        if (right - left).days > 1:
            warnings.append(f"Missing dates between {left} and {right}; standard calculation will be used")
    if (ordered[-1] - ordered[0]).days > 45:
        warnings.append("Timetable spans more than 45 days; verify the year and date range")
    return sorted(cleaned, key=lambda r: r["date"]), warnings


def parse_csv(text, mapping=None):
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    mapping = mapping or {"date": "date", "fajr": "fajr", "maghrib": "maghrib"}
    if (not isinstance(mapping, dict) or set(mapping) != {"date", "fajr", "maghrib"}
            or not all(isinstance(v, str) for v in mapping.values())
            or len(set(mapping.values())) != 3):
        raise ValueError("Confirm distinct date, Fajr and Maghrib column mappings")
    if not reader.fieldnames or not set(mapping.values()) <= set(reader.fieldnames):
        raise ValueError("CSV columns do not match the confirmed mapping")
    rows = []
    for row in reader:
        if len(rows) >= 62:
            raise ValueError("Enter no more than 62 timetable rows")
        rows.append({key: row.get(column, "") for key, column in mapping.items()})
    return validate_rows(rows)


class RamadanService:
    def __init__(self, store, provider):
        self.store, self.provider = store, provider

    def list(self):
        profiles = self.store.rows("SELECT * FROM profiles ORDER BY id DESC")
        for profile in profiles:
            profile["rows"] = self.store.rows(
                "SELECT date,fajr,maghrib,notes FROM overrides WHERE profile_id=? ORDER BY date",
                (profile["id"],))
        return profiles

    def save(self, payload, profile_id=None):
        name, source = str(payload.get("name", "")).strip(), str(payload.get("source", "")).strip()
        if not name or not source or len(name) > 120 or len(source) > 200:
            raise ValueError("A profile name (max 120) and source (max 200) are required")
        rows, warnings = validate_rows(payload.get("rows"))
        with self.store.connect(write=True) as db:
            if profile_id:
                row = db.execute("SELECT active FROM profiles WHERE id=?", (profile_id,)).fetchone()
                if not row:
                    raise ValueError("Profile not found")
                if row[0]:
                    raise ValueError("Deactivate the profile before editing")
                db.execute("UPDATE profiles SET name=?,source=?,notes=? WHERE id=?",
                           (name, source, str(payload.get("notes", ""))[:2000], profile_id))
                db.execute("DELETE FROM overrides WHERE profile_id=?", (profile_id,))
            else:
                profile_id = db.execute(
                    "INSERT INTO profiles(name,source,notes,created_at) VALUES (?,?,?,?)",
                    (name, source, str(payload.get("notes", ""))[:2000], utcnow())).lastrowid
            db.executemany("INSERT INTO overrides(profile_id,date,fajr,maghrib,notes) VALUES (?,?,?,?,?)",
                           [(profile_id, r["date"], r["fajr"], r["maghrib"], r["notes"]) for r in rows])
            self.store.event(db, "ramadan_draft_saved", str(profile_id))
        return {"id": profile_id, "warnings": warnings}

    def preview(self, profile_id):
        profiles = [p for p in self.list() if p["id"] == profile_id]
        if not profiles:
            raise ValueError("Profile not found")
        profile = profiles[0]
        _, warnings = validate_rows(profile["rows"])
        rows = []
        unavailable_months = {}
        for entry in profile["rows"]:
            try:
                month = entry["date"][:7]
                if month in unavailable_months:
                    raise RuntimeError(unavailable_months[month])
                base = self.provider.fetch_date(date.fromisoformat(entry["date"]))
                error = None
            except RuntimeError as exc:
                base, error = {}, str(exc)
                unavailable_months[entry["date"][:7]] = error
            item = dict(entry, standard=base, error=error, differences={})
            for key in ("fajr", "maghrib"):
                normal, override = base.get(key.title()), entry[key]
                if normal and override:
                    def minutes(v):
                        h, m = map(int, v.split(":"))
                        return h * 60 + m
                    delta = minutes(override) - minutes(normal)
                    item["differences"][key] = delta
                    if abs(delta) > 30:
                        warnings.append(f"{entry['date']}: {key} differs by {delta} minutes; review carefully")
            rows.append(item)
        return {"profile": profile, "rows": rows, "warnings": warnings}

    def activate(self, db, profile_id, active):
        if not db.execute("SELECT 1 FROM profiles WHERE id=?", (profile_id,)).fetchone():
            raise ValueError("Profile not found")
        if active:
            db.execute("UPDATE profiles SET active=0 WHERE active=1")
        db.execute("UPDATE profiles SET active=? WHERE id=?", (int(active), profile_id))
        self.store.event(db, "ramadan_activated" if active else "ramadan_deactivated", str(profile_id))

    def delete(self, profile_id):
        with self.store.connect(write=True) as db:
            row = db.execute("SELECT active FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if not row or row[0]:
                raise ValueError("Deactivate an existing profile before deleting it")
            db.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
            self.store.event(db, "ramadan_deleted", str(profile_id))
