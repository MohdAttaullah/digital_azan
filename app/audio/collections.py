import json
import re
import shutil
import subprocess
import wave
from pathlib import Path

SUPPORTED = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}


def natural_key(value):
    return tuple((0, int(p)) if p.isdigit() else (1, p.casefold())
                 for p in re.split(r"(\d+)", str(value)))


class AudioCollections:
    def __init__(self, cfg):
        self.cfg = cfg
        self.validation = {}
        self.warnings = []
        self.files = {}
        self.refresh()

    def _validate(self, path):
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if key in self.validation:
            return self.validation[key]
        error = None
        try:
            if stat.st_size < 44:
                raise ValueError("file is too small")
            if path.suffix.lower() == ".wav":
                with wave.open(str(path), "rb") as audio:
                    if audio.getnframes() < 1 or audio.getframerate() < 1:
                        raise ValueError("empty WAV")
                    # Verify declared PCM frames fit in the file; decoder reports remaining corruption.
                    if audio.getnframes() * audio.getnchannels() * audio.getsampwidth() > stat.st_size:
                        raise ValueError("truncated WAV")
            elif shutil.which("ffprobe"):
                result = subprocess.run(
                    ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                     "stream=codec_name", "-of", "json", str(path)],
                    capture_output=True, text=True, timeout=8, check=True)
                if not json.loads(result.stdout).get("streams"):
                    raise ValueError("no audio stream")
            else:
                raise ValueError("ffprobe is required to validate compressed recordings")
        except (OSError, ValueError, wave.Error, EOFError, subprocess.SubprocessError) as exc:
            error = str(exc)
        self.validation[key] = error
        return error

    def refresh(self):
        self.warnings = []
        for collection, folder, legacy in (
                ("normal", self.cfg.normal_dir, "default"),
                ("fajr", self.cfg.fajr_dir, "fajr")):
            # An explicitly configured empty collection NEVER falls back to another collection.
            if folder is not None:
                candidates = list(folder.iterdir()) if folder.is_dir() else []
            else:
                value = self.cfg.audio_files.get(legacy)
                candidates = [Path(value)] if value else []
            usable = []
            for path in sorted(candidates, key=lambda p: natural_key(p.name)):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in SUPPORTED:
                    self.warnings.append(f"{collection}/{path.name}: unsupported format")
                    continue
                error = self._validate(path)
                if error:
                    self.warnings.append(f"{collection}/{path.name}: {error}")
                else:
                    usable.append(path.resolve())
            self.files[collection] = usable
            if not usable:
                self.warnings.append(f"No usable {collection} recordings configured")
        return self.files

    def select(self, db, prayer):
        collection = "fajr" if prayer == "Fajr" else "normal"
        files = [p for p in self.files[collection] if p.is_file()]
        if not files:
            raise ValueError(f"No usable {collection} recording")
        row = db.execute("SELECT last_file FROM rotations WHERE collection=?", (collection,)).fetchone()
        last = row[0] if row else None
        names = [p.name for p in files]
        if last in names:
            selected = files[(names.index(last) + 1) % len(files)]
        else:
            selected = next((p for p in files if last and natural_key(p.name) > natural_key(last)), files[0])
        db.execute("INSERT INTO rotations VALUES (?,?) ON CONFLICT(collection) DO UPDATE SET last_file=excluded.last_file",
                   (collection, selected.name))
        return str(selected)
