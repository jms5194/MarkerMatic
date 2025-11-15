import socket
import threading
import time
from typing import Any, Callable

from pubsub import pub

import constants
from constants import PyPubSubTopics
from logger_config import logger

from . import Console, Feature

DELIMITER = b"\n"
BUFFER_SIZE = 4096
SCENE_TYPES = ("MIXER:Lib/Scene", "scene_a")


class Buffer(object):
    def __init__(self, sock: socket.socket, shutdown_server_event: threading.Event):
        self.sock: socket.socket = sock
        self.buffer = b""
        self._shutdown_server_event = shutdown_server_event

    def get_line(self):
        while DELIMITER not in self.buffer and not self._shutdown_server_event.is_set():
            try:
                data = self.sock.recv(BUFFER_SIZE)
                if not data:  # socket is closed
                    return None
                self.buffer += data
            except TimeoutError:
                pass
        line, _, self.buffer = self.buffer.partition(DELIMITER)
        return line.decode()


class Yamaha(Console):
    fixed_send_port = 49280
    type = "Yamaha"
    supported_features = [Feature.CUE_NUMBER]

    def __init__(self) -> None:
        super().__init__()
        self._client_socket: socket.socket
        self._connection_established = threading.Event()

    def start_managed_threads(
        self, start_managed_thread: Callable[[str, Any], None]
    ) -> None:
        start_managed_thread("console_connection_thread", self._yamaha_client_thread)

    def _yamaha_client_thread(self):
        from app_settings import settings

        while not self._shutdown_server_event.is_set():
            self._connection_established.clear()
            with socket.socket(
                socket.AF_INET, socket.SOCK_STREAM
            ) as self._client_socket:
                try:
                    self._client_socket.settimeout(constants.CONNECTION_TIMEOUT_SECONDS)
                    self._client_socket.connect(
                        (settings.console_ip, self.fixed_send_port)
                    )
                except Exception:
                    logger.warning(f"Could not connect to {self.type}")
                    time.sleep(constants.CONNECTION_RECONNECTION_DELAY_SECONDS)
                    continue
                logger.info(f"Connected to {self.type}")
                pub.sendMessage(PyPubSubTopics.CONSOLE_CONNECTED)
                self._client_socket.settimeout(constants.MESSAGE_TIMEOUT_SECONDS)
                buff = Buffer(self._client_socket, self._shutdown_server_event)
                self._connection_established.set()
                while not self._shutdown_server_event.is_set():
                    line = buff.get_line()
                    if line is None:
                        logger.error(f"{self.type} connection reset")
                        pub.sendMessage(PyPubSubTopics.CONSOLE_DISCONNECTED)
                        break
                    # Check the line for matches against known message types
                    if self._match_internal_scene_recall(line):
                        pass
                    elif self._match_scene_info(line):
                        pass

        logger.info(f"Closing connection to {self.type}")

    def _match_internal_scene_recall(
        self,
        line: str,
    ) -> bool:
        """Checks to see if the line matches an internal scene recall for a
        supported scene type, and requests the scene's info if it does.

        Returns True if matched, False otherwise."""
        for scene_type in SCENE_TYPES:
            if line.startswith(f"NOTIFY sscurrent_ex {scene_type}"):
                internal_id = line.rsplit(maxsplit=1)[1]
                logger.info(
                    f"{self.type} internal {scene_type} scene {internal_id} recalled"
                )
                self._request_scene_info(scene_type, internal_id)
                return True
        return False

    def _request_scene_info(self, scene_type: str, internal_id: str) -> None:
        """Sends a request for a scene's info, using a scene type/cue list, and
        the scene's internal ID"""
        request_scene_info_command = f"ssinfo_ex {scene_type} {internal_id}\n"
        self._client_socket.sendall(str.encode(request_scene_info_command))

    def _match_scene_info(
        self,
        line: str,
    ) -> bool:
        """Checks to see if the line matches a response for a scene's info, and
        sends a cue load message if it does.

        Returns True if matched, False otherwise."""
        for scene_type in SCENE_TYPES:
            if line.startswith(f"OK ssinfo_ex {scene_type}"):
                quote_split_line = line.split('"')
                scene_number = quote_split_line[1]
                scene_name = quote_split_line[3]
                cue_payload = f"{scene_number} {scene_name}"
                pub.sendMessage(PyPubSubTopics.HANDLE_CUE_LOAD, cue=cue_payload)
                return True
        return False

    def heartbeat(self) -> None:
        if hasattr(self, "_client_socket") and self._connection_established.is_set():
            try:
                self._client_socket.sendall(b"\x0a")
                pub.sendMessage(PyPubSubTopics.CONSOLE_CONNECTED)
            except OSError:
                pub.sendMessage(PyPubSubTopics.CONSOLE_DISCONNECTED)
