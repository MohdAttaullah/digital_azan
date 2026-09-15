"""mpv's software mixer changes only Azan volume, never the host master mixer."""
import json
import os
import socket
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from app.audio.base import AudioEngine


class SystemAudioEngine(AudioEngine):
    def __init__(self, output="pulse"):
        self.output = output
        self.process = None
        self.ipc_path = None

    def _new_ipc_path(self):
        name = f"digital-azan-mpv-{os.getpid()}-{uuid.uuid4().hex[:12]}"
        if os.name == "nt":
            return rf"\\.\pipe\{name}"
        runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
        return str(runtime_dir / f"{name}.sock")

    def _cleanup_ipc(self):
        if self.ipc_path and os.name != "nt":
            try:
                Path(self.ipc_path).unlink(missing_ok=True)
            except OSError:
                pass
        self.ipc_path = None

    def _send_command(self, command):
        payload = (json.dumps({"command": command}) + "\n").encode()
        deadline = time.monotonic() + 1.5
        last_error = None
        while time.monotonic() < deadline:
            try:
                if os.name == "nt":
                    with open(self.ipc_path, "r+b", buffering=0) as channel:
                        channel.write(payload)
                        response = channel.readline()
                else:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
                        channel.settimeout(1)
                        channel.connect(self.ipc_path)
                        channel.sendall(payload)
                        response = b""
                        while not response.endswith(b"\n"):
                            chunk = channel.recv(4096)
                            if not chunk:
                                break
                            response += chunk
                result = json.loads(response)
                if result.get("error") != "success":
                    raise RuntimeError(f"mpv rejected volume change: {result.get('error', 'unknown error')}")
                return
            except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
                last_error = exc
                time.sleep(0.03)
        raise RuntimeError("mpv control channel is unavailable") from last_error

    def start(self, file_path, volume):
        if self.process and self.process.poll() is None:
            raise RuntimeError("Audio is already playing")
        if not Path(file_path).is_file():
            raise FileNotFoundError("Selected recording is missing")
        self._cleanup_ipc()
        self.ipc_path = self._new_ipc_path()
        command = ["mpv", "--no-config", "--no-video", "--no-terminal", "--really-quiet",
                   "--audio-display=no", f"--volume={volume}", f"--input-ipc-server={self.ipc_path}"]
        if os.name != "nt" and self.output:
            command.append(f"--ao={self.output}")
        command.extend(["--", str(Path(file_path).resolve())])
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except Exception:
            self._cleanup_ipc()
            raise

    def poll(self):
        result = self.process.poll() if self.process else None
        if result is not None:
            self._cleanup_ipc()
        return result

    def set_volume(self, volume):
        if not self.process or self.process.poll() is not None:
            return False
        self._send_command(["set_property", "volume", volume])
        return True

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self._cleanup_ipc()
