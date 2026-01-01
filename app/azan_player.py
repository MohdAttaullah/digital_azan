from app.audio.factory import create_audio_engine


class AzanPlayer:
    def __init__(self, cfg):
        self.engine = create_audio_engine(cfg)
        self.audio_files = cfg.audio_files

    def _select_azan_file(self, prayer_name: str) -> str:
        if prayer_name.lower() == "fajr":
            return self.audio_files["fajr"]
        return self.audio_files["default"]

    def play(self, prayer_name: str) -> None:
        azan_file = self._select_azan_file(prayer_name)

        print(f"[AUDIO] Playing Azan for {prayer_name}")
        self.engine.play_file(azan_file)
