from dataclasses import replace

import pytest

from app.web import create_app

HEADERS = {"X-Azan-Control": "1"}


@pytest.fixture
def web(rig):
    c, _, _ = rig
    c.tick()
    app = create_app(c)
    app.testing = True
    return app.test_client(), c


def test_dashboard_status_history(web):
    client, c = web
    assert client.get("/").status_code == 200
    data = client.get("/api/status").json
    assert len(data["occurrences"]) == 5
    assert data["next"]["prayer"] == "Fajr"
    assert client.get("/api/history?date=2027-03-05").json["scheduled"] == 5
    assert client.get("/api/history?date=bad").status_code == 400
    assert client.get("/api/audio").json["fajr"][0]["filename"] == "fajr_1.wav"


@pytest.mark.parametrize("url,data", [("/api/volume", {"volume": 25}),
    ("/api/prayers/Asr", {"enabled": False}), ("/api/snooze", {"minutes": 60}),
    ("/api/snooze", {"until_time": "05:30"}), ("/api/resume", {}), ("/api/stop", {})])
def test_controls(web, url, data):
    client, _ = web
    assert client.post(url, json=data, headers=HEADERS).status_code == 200


@pytest.mark.parametrize("url,data", [("/api/volume", {"volume": 101}),
    ("/api/volume", {"volume": True}), ("/api/prayers/Asr", {"enabled": "false"}),
    ("/api/prayers/Bad", {"enabled": True}), ("/api/snooze", {"minutes": -1}),
    ("/api/snooze", {"until": "2027-03-05T10:00:00"}),
    ("/api/snooze", {"until_time": "99:00"})])
def test_invalid_control_input(web, url, data):
    client, _ = web
    assert client.post(url, json=data, headers=HEADERS).status_code == 400


def test_control_auth_and_cross_site(web):
    client, c = web
    assert client.post("/api/stop", json={}).status_code == 403
    assert client.post("/api/stop", json={}, headers={**HEADERS, "Origin": "https://evil.example"}).status_code == 403
    c.cfg = replace(c.cfg, control_token="secret")
    assert client.post("/api/stop", json={}, headers=HEADERS).status_code == 401
    assert client.post("/api/stop", json={}, headers={**HEADERS, "Authorization": "Bearer secret"}).status_code == 200


def test_dns_rebinding_host_rejected(web):
    client, _ = web
    assert client.get("/api/status", headers={"Host": "attacker.example"}).status_code == 400
    assert client.get("/api/status", headers={"Host": "192.168.1.50:8080"}).status_code == 200


def test_skip_and_actual_stop(web, rig):
    client, c = web
    _, clock, player = rig
    next_id = client.get("/api/status").json["next"]["id"]
    assert client.post(f"/api/occurrences/{next_id}/skip", json={}, headers=HEADERS).status_code == 200
    clock.set("2027-03-05T12:17:00+05:30")
    c.tick()
    assert client.post("/api/stop", json={}, headers=HEADERS).status_code == 200
    assert player.stopped
    assert c.history("2027-03-05")["counts"]["STOPPED_BY_USER"] == 1


def test_preview_required_and_stale_preview_rejected(web):
    client, c = web
    payload = {"name": "Ramadan", "source": "Local Masjid", "rows": [
        {"date": "2027-03-05", "fajr": "05:25", "maghrib": "18:35"}]}
    result = client.post("/api/ramadan", json=payload, headers=HEADERS)
    assert result.status_code == 201
    pid = result.json["id"]
    assert not c.ramadan.list()[0]["active"]
    url = f"/api/ramadan/{pid}/activation"
    assert client.post(url, json={"active": True, "confirmed": True}, headers=HEADERS).status_code == 400
    preview = client.get(f"/api/ramadan/{pid}/preview").json
    payload["rows"][0]["fajr"] = "05:26"
    client.put(f"/api/ramadan/{pid}", json=payload, headers=HEADERS)
    assert client.post(url, json={"active": True, "confirmed": True, "revision": preview["revision"]}, headers=HEADERS).status_code == 400
    preview = client.get(f"/api/ramadan/{pid}/preview").json
    assert client.post(url, json={"active": True, "confirmed": True, "revision": preview["revision"]}, headers=HEADERS).status_code == 200
    assert c.history("2027-03-05")["occurrences"][0]["effective_time"] == "05:26"


def test_ocr_is_draft_and_upload_validation(web, monkeypatch):
    import io
    client, c = web
    monkeypatch.setattr("app.ocr.extract", lambda data, name: {"lines": [{"date":"2027-03-05", "times":["05:21","18:34"]}], "active":False})
    result = client.post("/api/ramadan/ocr", data={"file": (io.BytesIO(b"image"), "card.png")}, headers=HEADERS)
    assert result.status_code == 200
    assert result.json["active"] is False
    assert c.ramadan.list() == []
    assert client.post("/api/ramadan/ocr", data={}, headers=HEADERS).status_code == 400
