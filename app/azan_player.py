"""Playback lifecycle, preserving the previous MPD pause/resume behavior."""
import logging
import shutil
import subprocess
from app.audio.factory import create_audio_engine

log = logging.getLogger(__name__)


class AzanPlayer:
    def __init__(self, cfg, engine=None):
        self.engine = engine or create_audio_engine(cfg)
        self.use_mpd = cfg.audio_mode == "system" and bool(shutil.which("mpc"))
        self.resume_mpd = False

    def _mpc(self, command):
        return subprocess.run(["mpc", command], capture_output=True, text=True, timeout=2,
                              check=True)

    def start(self, file_path, volume):
        self.resume_mpd = False
        if self.use_mpd:
            try:
                self.resume_mpd = "[playing]" in self._mpc("status").stdout
                if self.resume_mpd:
                    self._mpc("stop")
            except (OSError, subprocess.SubprocessError):
                log.warning("Could not coordinate MPD", exc_info=True)
                self.resume_mpd = False
        try:
            self.engine.start(file_path, volume)
        except Exception:
            self.finish()
            raise

    def poll(self):
        return self.engine.poll()

    def finish(self):
        if self.resume_mpd:
            self.resume_mpd = False
            try:
                self._mpc("play")
            except (OSError, subprocess.SubprocessError):
                log.warning("Could not resume MPD", exc_info=True)

    def stop(self):
        try:
            self.engine.stop()
        finally:
            self.finish()
