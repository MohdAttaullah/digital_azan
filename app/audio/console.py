from app.audio.base import AudioEngine


class ConsoleAudioEngine(AudioEngine):
    def play_file(self, file_path: str) -> None:
        print(f"[AUDIO] (console) Playing file: {file_path}")
