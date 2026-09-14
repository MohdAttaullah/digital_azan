import logging
from app.audio.base import AudioEngine


class ConsoleAudioEngine(AudioEngine):
    def start(self, file_path, volume):
        logging.getLogger(__name__).info("SIMULATED audio: %s volume=%s", file_path, volume)

    def poll(self):
        return 0

    def stop(self):
        pass
