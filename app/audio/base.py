"""Nonblocking playback contract; poll returns None while active, then exit code."""
from abc import ABC, abstractmethod


class AudioEngine(ABC):
    @abstractmethod
    def start(self, file_path: str, volume: int):
        pass

    @abstractmethod
    def poll(self):
        pass

    @abstractmethod
    def stop(self):
        pass
