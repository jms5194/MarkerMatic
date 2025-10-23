import threading
from enum import Enum
from typing import Callable, List, Optional

from pubsub import pub

from constants import PyPubSubTopics


class Feature(Enum):
    CUE_NUMBER = 1
    REPEATER = 2
    SEPERATE_RECEIVE_PORT = 3
    CUE_LIST_PLAYER = 4


class Console:
    fixed_receive_port: Optional[int] = None
    fixed_send_port: Optional[int] = None
    _shutdown_server_event: threading.Event
    supported_features: List[Feature]
    type = "Unknown"

    def __init__(self) -> None:
        self._shutdown_server_event = threading.Event()
        pub.subscribe(self._shutdown_server_event.set, PyPubSubTopics.SHUTDOWN_SERVERS)

    def heartbeat(self) -> None:
        pass

    def start_managed_threads(
        self, start_managed_thread: Callable[[str, Callable], None]
    ) -> None:
        pass
