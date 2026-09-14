"""mpv's software mixer changes only Azan volume, never the host master mixer."""
import os
import subprocess
from pathlib import Path

from app.audio.base import AudioEngine


class SystemAudioEngine(AudioEngine):
    def __init__(self, output="pulse"):
        self.output = output
        self.process = None

    def start(self, file_path, volume):
        if self.process and self.process.poll() is None:
            raise RuntimeError("Audio is already playing")
        if not Path(file_path).is_file():
            raise FileNotFoundError("Selected recording is missing")
        command = ["mpv", "--no-config", "--no-video", "--no-terminal", "--really-quiet",
                   "--audio-display=no", f"--volume={volume}"]
        if os.name != "nt" and self.output:
            command.append(f"--ao={self.output}")
        command.extend(["--", str(Path(file_path).resolve())])
        self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    def poll(self):
        return self.process.poll() if self.process else None

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
