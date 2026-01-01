import platform
import subprocess
from pathlib import Path

from app.audio.base import AudioEngine


class SystemAudioEngine(AudioEngine):
    def __init__(self, volume_percent: int):
        self.volume_percent = volume_percent
        self.system = platform.system().lower()

    def _set_volume(self):
        if self.system == "linux":
            subprocess.run(
                ["amixer", "sset", "Master", f"{self.volume_percent}%"],
                check=False,
            )

    def play_file(self, file_path: str) -> None:
        path = Path(file_path)

        if not path.exists():
            print(f"[ERROR] Audio file not found: {path}")
            return

        if self.system == "windows":
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME)

        elif self.system == "linux":
            self._set_volume()
            subprocess.run(["mpg123", str(path)], check=False)
