"""Local web UI and validated control API; creating the app never starts a scheduler."""
import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import subprocess
import threading
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.exceptions import HTTPException

from app.ramadan import parse_csv


def revision(profile):
    return hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()


def create_app(controller):
    app = Flask(__name__, static_folder="static")
    app.config.update(MAX_CONTENT_LENGTH=8 * 1024 * 1024, SECRET_KEY=secrets.token_hex(32),
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")
    import_slot = threading.BoundedSemaphore(1)

    @app.before_request
    def protect_controls():
        hostname = (urlsplit(request.host_url).hostname or "").lower()
        machine = socket.gethostname().lower()
        trusted = {"localhost", machine, machine + ".local", *controller.cfg.allowed_hosts}
        try:
            private_address = ipaddress.ip_address(hostname).is_private
        except ValueError:
            private_address = False
        if hostname not in trusted and not private_address:
            return jsonify(error="Untrusted host; configure AZAN_ALLOWED_HOSTS for a custom hostname"), 400
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if request.headers.get("X-Azan-Control") != "1":
                return jsonify(error="Missing control request header"), 403
            origin = request.headers.get("Origin")
            if origin and urlsplit(origin).netloc != request.host:
                return jsonify(error="Cross-origin controls are forbidden"), 403
            if request.headers.get("Sec-Fetch-Site") == "cross-site":
                return jsonify(error="Cross-site controls are forbidden"), 403
            token = controller.cfg.control_token
            if token and not hmac.compare_digest(request.headers.get("Authorization", ""), f"Bearer {token}"):
                return jsonify(error="Enter the control token in Settings"), 401

    @app.after_request
    def secure_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        return response

    @app.errorhandler(ValueError)
    def bad_input(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(Exception)
    def internal_error(error):
        app.logger.exception("Request failed")
        return jsonify(error="Request failed; inspect service logs"), 500

    def body():
        payload = request.get_json()
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        return payload

    def control(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            fn(*args, **kwargs)
            return jsonify(ok=True)
        return wrapped

    @app.get("/")
    def dashboard():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/status")
    def status():
        return jsonify(controller.status())

    @app.get("/health")
    def health():
        result = controller.health()
        return jsonify(result), 200 if result["ok"] else 503

    @app.get("/api/history")
    def history():
        return jsonify(controller.history(request.args.get("date", "")))

    @app.get("/api/settings")
    def settings():
        return jsonify(controller.settings())

    @app.post("/api/volume")
    @control
    def volume():
        controller.set_volume(body().get("volume"))

    @app.post("/api/prayers/<prayer>")
    @control
    def enabled(prayer):
        controller.set_enabled(prayer, body().get("enabled"))

    @app.post("/api/snooze")
    @control
    def snooze():
        data = body()
        if "minutes" in data:
            if type(data["minutes"]) is not int or not 1 <= data["minutes"] <= 1440:
                raise ValueError("Snooze minutes must be 1–1440")
            until = controller.now() + timedelta(minutes=data["minutes"])
        elif "until_time" in data:
            import re
            value = str(data["until_time"])
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
                raise ValueError("Choose a valid local snooze end time")
            day = controller.now().astimezone(controller.tz).date()
            until = datetime.fromisoformat(controller.timestamp(day, value))
            if until <= controller.now():
                until = datetime.fromisoformat(controller.timestamp(day + timedelta(days=1), value))
        else:
            until = datetime.fromisoformat(str(data.get("until", "")))
        controller.snooze(until)

    @app.post("/api/resume")
    @control
    def resume():
        controller.resume()

    @app.post("/api/stop")
    @control
    def stop():
        controller.stop_audio()

    @app.post("/api/occurrences/<int:occurrence_id>/skip")
    @control
    def skip(occurrence_id):
        controller.skip(occurrence_id)

    @app.get("/api/audio")
    def audio():
        with controller.lock:
            result = {name: [{"filename": p.name} for p in paths]
                      for name, paths in controller.collections.files.items()}
            result["warnings"] = controller.collections.warnings
        return jsonify(result)

    @app.post("/api/audio/test")
    def audio_test():
        data = body()
        return jsonify(controller.start_audio_test(data.get("collection", "normal")))

    @app.get("/api/ramadan")
    def profiles():
        with controller.lock:
            return jsonify(controller.ramadan.list())

    @app.post("/api/ramadan")
    def create_profile():
        with controller.lock:
            return jsonify(controller.ramadan.save(body())), 201

    @app.put("/api/ramadan/<int:profile_id>")
    def edit_profile(profile_id):
        with controller.lock:
            return jsonify(controller.ramadan.save(body(), profile_id))

    @app.delete("/api/ramadan/<int:profile_id>")
    @control
    def delete_profile(profile_id):
        if body().get("confirmed") is not True:
            raise ValueError("Confirm deletion")
        with controller.lock:
            controller.ramadan.delete(profile_id)

    @app.post("/api/ramadan/csv")
    def csv_draft():
        data = body()
        if not isinstance(data.get("csv"), str):
            raise ValueError("CSV text is required")
        rows, warnings = parse_csv(data["csv"], data.get("mapping"))
        return jsonify(rows=rows, warnings=warnings, active=False)

    @app.post("/api/ramadan/ocr")
    def ocr_draft():
        from app.ocr import extract
        upload = request.files.get("file")
        if not upload:
            raise ValueError("Choose a timetable image or PDF")
        if not import_slot.acquire(blocking=False):
            return jsonify(error="Another import or preview is running; try again shortly"), 409
        try:
            return jsonify(extract(upload.read(), upload.filename or ""))
        except (subprocess.SubprocessError, OSError) as exc:
            raise ValueError("OCR could not read this file; use CSV/manual entry") from exc
        finally:
            import_slot.release()

    @app.get("/api/ramadan/<int:profile_id>/preview")
    def preview(profile_id):
        if not import_slot.acquire(blocking=False):
            return jsonify(error="Another import or preview is running; try again shortly"), 409
        try:
            result = controller.ramadan.preview(profile_id)
        finally:
            import_slot.release()
        result["revision"] = revision(result["profile"])
        session[f"preview:{profile_id}"] = result["revision"]
        return jsonify(result)

    @app.post("/api/ramadan/<int:profile_id>/activation")
    @control
    def activation(profile_id):
        data = body()
        if type(data.get("active")) is not bool:
            raise ValueError("active must be a boolean")
        with controller.lock:
            if data["active"]:
                profiles = [p for p in controller.ramadan.list() if p["id"] == profile_id]
                if not profiles:
                    raise ValueError("Profile not found")
                current = revision(profiles[0])
                if (data.get("confirmed") is not True or data.get("revision") != current
                        or session.get(f"preview:{profile_id}") != current):
                    raise ValueError("Preview this draft, review the differences, then confirm activation")
            controller.activate_profile(profile_id, data["active"])

    return app
