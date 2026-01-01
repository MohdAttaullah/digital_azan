from app.audio.base import AudioEngine


class ConsoleAudioEngine(AudioEngine):
    def play_azan(self, prayer_name: str) -> None:
        print(f"[AUDIO] Azan triggered for {prayer_name}")
