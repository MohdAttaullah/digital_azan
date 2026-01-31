import subprocess
from app.audio.factory import create_audio_engine


class AzanPlayer:
    def __init__(self, cfg):
        self.engine = create_audio_engine(cfg)
        self.audio_files = cfg.audio_files

    def _select_azan_file(self, prayer_name: str) -> str:
        if prayer_name.lower() == "fajr":
            return self.audio_files["fajr"]
        return self.audio_files["default"]

    def _is_mpd_playing(self) -> bool:
        try:
            result = subprocess.check_output(
                ["mpc", "status"],
                stderr=subprocess.DEVNULL
            ).decode()
            return "[playing]" in result
        except:
            return False

    def _stop_mpd(self):
        subprocess.run(
            ["mpc", "stop"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    def _resume_mpd(self):
        subprocess.run(
            ["mpc", "play"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    def play(self, prayer_name: str) -> None:
        azan_file = self._select_azan_file(prayer_name)

        mpd_was_playing = self._is_mpd_playing()

        if mpd_was_playing:
            print("[AUDIO] Stopping MPD")
            self._stop_mpd()

        print(f"[AUDIO] Playing Azan for {prayer_name}")
        self.engine.play_file(azan_file)

        if mpd_was_playing:
            print("[AUDIO] Resuming MPD")
            self._resume_mpd()
