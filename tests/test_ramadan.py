from datetime import date

import pytest

from app.ramadan import parse_csv, validate_rows
from tests.conftest import TIMINGS
from tests.test_scheduler import occurrence


def profile(c, **extra):
    return c.ramadan.save(dict(name="Ramadan 2027", source="Local Masjid", rows=[
        {"date": "2027-03-05", "fajr": "05:25", "maghrib": "18:36"}], **extra))["id"]


def test_draft_activation_precedence_and_deactivation(rig):
    c, _, _ = rig
    pid = profile(c)
    assert occurrence(c)["effective_time"] == "05:21"
    preview = c.ramadan.preview(pid)
    assert preview["rows"][0]["differences"] == {"fajr": 4, "maghrib": 2}
    c.activate_profile(pid, True)
    assert occurrence(c)["effective_time"] == "05:25"
    assert occurrence(c, "Maghrib")["effective_time"] == "18:36"
    for prayer in ("Dhuhr", "Asr", "Isha"):
        assert occurrence(c, prayer)["effective_time"] == TIMINGS[prayer]
    c.build_day(date(2027, 3, 6), TIMINGS)
    assert occurrence(c, "Fajr", "2027-03-06")["effective_time"] == "05:21"
    c.activate_profile(pid, False)
    assert occurrence(c)["effective_time"] == "05:21"


def test_missing_time_and_dates_warn_and_fallback(rig):
    c, _, _ = rig
    rows, warnings = validate_rows([{"date": "2027-03-05", "fajr": "05:25"},
                                   {"date": "2027-03-07", "maghrib": "18:36"}])
    assert len(warnings) == 3
    pid = c.ramadan.save({"name": "Partial", "source": "Masjid", "rows": rows})["id"]
    c.activate_profile(pid, True)
    assert occurrence(c, "Maghrib")["effective_time"] == "18:34"


@pytest.mark.parametrize("rows", [[], [{"date": "2027-02-30", "fajr": "05:20"}],
    [{"date": "2027-03-05", "fajr": "25:00"}], [{"date": "2027-03-05", "maghrib": "06:35"}],
    [{"date": "2027-03-05", "fajr": "15:30"}], [{"date": "2027-03-05"}],
    [{"date": "2027-03-05", "fajr": "05:20"}]*2])
def test_invalid_rows(rows):
    with pytest.raises(ValueError):
        validate_rows(rows)


def test_csv_requires_explicit_mapping():
    text = "Date,Sehri,Iftar\n2027-03-05,05:21,18:34"
    with pytest.raises(ValueError):
        parse_csv(text)
    rows, _ = parse_csv(text, {"date": "Date", "fajr": "Sehri", "maghrib": "Iftar"})
    assert rows[0]["maghrib"] == "18:34"


def test_one_active_profile_and_no_edit_active(rig):
    c, _, _ = rig
    first, second = profile(c), profile(c)
    c.activate_profile(first, True)
    c.activate_profile(second, True)
    assert sum(p["active"] for p in c.ramadan.list()) == 1
    with pytest.raises(ValueError):
        c.ramadan.delete(second)
    c.ramadan.delete(first)


def test_retroactive_override_never_starts_audio(rig):
    c, clock, p = rig
    pid = c.ramadan.save({"name": "Past correction", "source": "Masjid", "rows": [
        {"date": "2027-03-05", "fajr": "04:00"}]})["id"]
    clock.set("2027-03-05T04:01:00+05:30")
    c.activate_profile(pid, True)
    c.tick()
    assert not p.starts
    assert occurrence(c)["status"] == "MISSED_DOWNTIME"


def test_legacy_helper_uses_evening_maghrib():
    from app.ramadan_overrides import apply_ramadan_overrides
    result = apply_ramadan_overrides(TIMINGS, day=date(2026, 3, 5))
    assert result["Maghrib"] == "18:29"
    assert result["Fajr"] == "05:10"
    assert result["Dhuhr"] == TIMINGS["Dhuhr"]
