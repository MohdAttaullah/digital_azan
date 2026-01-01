import platform
import subprocess
import os
from pathlib import Path

from app.audio.base import AudioEngine


class SystemAudioEngine(AudioEngine):
    def __init__(self, azan_file: str, volume_percent: int):
        self.azan_file = Path(azan_file)
        self.volume_percent = volume_percent
        self.system = platform.system().lower()

    def _set_volume(self):
        # Volume control only on Linux (Pi)
        if self.system == "linux":
            subprocess.run(
                ["amixer", "sset", "Master", f"{self.volume_percent}%"],
                check=False,
            )

    def play_azan(self, prayer_name: str) -> None:
        if not self.azan_file.exists():
            print(f"[ERROR] Azan file not found: {self.azan_file}")
            return

        print(f"[AUDIO] Playing Azan for {prayer_name}")

        self._set_volume()

        if self.system == "windows":
            import winsound
            # MUST be WAV on Windows
            winsound.PlaySound(
                str(self.azan_file),
                winsound.SND_FILENAME,
            )

        elif self.system == "linux":
            subprocess.run(
                ["mpg123", str(self.azan_file)],
                check=False,
            )

        else:
            print(f"[WARN] Audio not supported on OS: {self.system}")
