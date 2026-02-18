import time
from typing import Any, Callable, Optional

from pubsub import pub
from pythonosc import dispatcher, osc_server, udp_client
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

import threading
import constants
import utilities
from logger_config import logger
from constants import PyPubSubTopics

from . import Console


class QLab(Console):
    fixed_send_port: int = 53000  # pyright: ignore[reportIncompatibleVariableOverride]
    fixed_receive_port: int = 53001
    type = "QLab"
    supported_features = []

    def __init__(self) -> None:
        super().__init__()
        self._client: udp_client.SimpleUDPClient
        self._cue_uniqueID: Optional[str] = None
        self._cue_number: Optional[str] = None
        self._cue_name: Optional[str] = None
        self._new_uniqueID_received = threading.Event()
        self._new_cuenumber_received = threading.Event()
        self._new_cuename_received = threading.Event()

    def start_managed_threads(
        self, start_managed_thread: Callable[[str, Callable[..., Any]], None]
    ) -> None:
        start_managed_thread("console_connection_thread", self._console_client_thread)

    def _console_client_thread(self) -> None:
        from app_settings import settings
        print("here")
        self._client = udp_client.SimpleUDPClient(
            settings.console_ip, self.fixed_send_port
        )
        self._qlab_dispatcher = dispatcher.Dispatcher()
        self._receive_console_OSC()
        try:
            self.qlab_osc_server = osc_server.ThreadingOSCUDPServer(
                (
                    utilities.get_ip_listen_any(settings.console_ip),
                    self.fixed_receive_port,
                ),
                self._qlab_dispatcher,
            )
            logger.info("QLab OSC server started")
            self.qlab_osc_server.serve_forever()
        except Exception as e:
            logger.error(f"QLab OSC server startup error: {e}")


    def _receive_console_OSC(self) -> None:
        self._qlab_dispatcher.map("/reply/thump", self._subscribe_ok_received)

        self._qlab_dispatcher.map("/cue/*/number", self._cue_number_received)
        self._qlab_dispatcher.map("/cue/*/name", self._cue_name_received)

        self._qlab_dispatcher.map("/qlab/event/workspace/go/uniqueID", self._cue_uniqueID_received)
        self._qlab_dispatcher.set_default_handler(self._message_received)

        while not self._shutdown_server_event.is_set():
            try:
                self.heartbeat()
                while not self._shutdown_server_event.is_set():
                    self._client.handle_messages(constants.MESSAGE_TIMEOUT_SECONDS)
            except Exception:
                time.sleep(constants.CONNECTION_RECONNECTION_DELAY_SECONDS)

    def _subscribe_ok_received(self, _address: str, _expires_seconds: int) -> None:
        self._message_received()

    def _subscribe_fail_received(self, _address: str) -> None:
        pub.sendMessage(PyPubSubTopics.CONSOLE_DISCONNECTED)

    def _cue_uniqueID_received(
        self, _address: str, cue_uniqueID: str
    ) -> None:
        self._cue_uniqueID = cue_uniqueID
        self._new_uniqueID_received.set()
        self._client.send_message(f"#/cue/{cue_uniqueID}/name", None)
        self._client.send_message(f"#/cue/{cue_uniqueID}/number", None)
        self._message_received()

    def _cue_number_received(self, _address: str, cue_number: str) -> None:
        if self._new_uniqueID_received.is_set():
            incoming_id = _address.split("/")[1]
            if incoming_id == self._cue_uniqueID:
                self._cue_number = cue_number
                self._new_cuenumber_received.set()
                if self._new_uniqueID_received.is_set() and self._new_cuename_received.is_set():
                    self._handle_cue_load(self._cue_number, self._cue_name)

    def _cue_name_received(self, _address: str, cue_name: str) -> None:
        if self._new_uniqueID_received.is_set():
            incoming_id = _address.split("/")[1]
            if incoming_id == self._cue_uniqueID:
                self._cue_name = cue_name
                self._new_cuename_received.set()
                if self._new_uniqueID_received.is_set() and self._new_cuename_received.is_set():
                    self._handle_cue_load(self._cue_number, self._cue_name)

    def _handle_cue_load(self, cue_number: str, cue_name: str) -> None:
        cue_string = f"{cue_number} {cue_name}"
        pub.sendMessage(PyPubSubTopics.HANDLE_CUE_LOAD, cue=cue_string)
        self._new_uniqueID_received.clear()
        self._new_cuenumber_received.clear()
        self._new_cuename_received.clear()

    def _message_received(self, *_) -> None:
        pub.sendMessage(PyPubSubTopics.CONSOLE_CONNECTED)

    def heartbeat(self) -> None:
        if hasattr(self, "_client"):
            self._client.send_message("/forgetMeNot", True)
            self._client.send_message("/thump", None)
