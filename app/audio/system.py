import platform
import subprocess
from pathlib import Path

from app.audio.base import AudioEngine


class SystemAudioEngine(AudioEngine):
    """
    Cross-platform system audio engine.
    - Windows: winsound (blocking)
    - Linux (Pi): mpv (headless, bluetooth-safe)
    """

    def __init__(self):
        self.system = platform.system().lower()

    def play_file(self, file_path: str) -> None:
        path = Path(file_path)

        if not path.exists():
            print(f"[ERROR] Audio file not found: {path}")
            return

        # Windows (local testing)
        if self.system == "windows":
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME)

        # Linux (Raspberry Pi)
        elif self.system == "linux":
            subprocess.run(
                [
                    "mpv",
                    "--no-video",
                    "--quiet",
                    "--ao=pulse",
                    str(path),
                ],
                check=False,
            )

        else:
            print(f"[ERROR] Unsupported OS: {self.system}")
