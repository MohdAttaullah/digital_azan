from app.audio.factory import create_audio_engine


class AzanPlayer:
    def __init__(self, cfg):
        self.engine = create_audio_engine(cfg)

    def play(self, prayer_name: str) -> None:
        print(f"[AUDIO] Azan triggered for {prayer_name}")
        self.engine.play_azan(prayer_name)
