from app.audio.console import ConsoleAudioEngine
from app.audio.system import SystemAudioEngine


def create_audio_engine(cfg):
    if cfg.audio_mode == "console":
        return ConsoleAudioEngine()
    if cfg.audio_mode == "system":
        return SystemAudioEngine(cfg.audio_output)
    raise ValueError(f"Unknown audio mode: {cfg.audio_mode}")
