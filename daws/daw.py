from typing import Callable
import threading
from pubsub import pub
from enum import IntEnum, auto
from constants import PyPubSubTopics


class DawFeature(IntEnum):
    NAME_ONLY_MATCH = auto()


class Daw:
    type = "Unknown"
    supported_features: list[DawFeature] = []

    def __init__(self) -> None:
        self._shutdown_server_event = threading.Event()
        pub.subscribe(self._shutdown_server_event.set, PyPubSubTopics.SHUTDOWN_SERVERS)

    def start_managed_threads(
        self, start_managed_thread: Callable[[str, Callable], None]
    ) -> None:
        pass
