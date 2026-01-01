from abc import ABC, abstractmethod


class AudioEngine(ABC):

    @abstractmethod
    def play_file(self, prayer_name: str) -> None:
        pass
