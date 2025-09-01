import threading
import time
from typing import Any, Callable

from pubsub import pub
from pythonosc import udp_client

import constants
from constants import PyPubSubTopics

from . import Console, Feature


class BehringerXAir(Console):
    fixed_send_port: int = 10024
    type = "Behringer X Air"
    supported_features = [Feature.CUE_NUMBER]
    _received_real_data = threading.Event()
    _client: udp_client.DispatchClient
    _console_name: str
    _snapshot_name: str

    def start_managed_threads(
        self, start_managed_thread: Callable[[str, Callable[..., Any]], None]
    ) -> None:
        start_managed_thread("console_connection_thread", self._console_client_thread)

    def _console_client_thread(self) -> None:
        from app_settings import settings

        self._client = udp_client.DispatchClient(
            settings.console_ip, self.fixed_send_port
        )
        self._client.dispatcher.map("/-snap/name", self._snapshot_name_received)
        self._client.dispatcher.map("/-snap/index", self._snapshot_number_received)
        self._client.dispatcher.map("/xinfo", self._console_name_received)
        self._client.dispatcher.set_default_handler(self._message_received)
        # Try connecting to the console, and subscribing to updates
        while not self._shutdown_server_event.is_set():
            try:
                self._client.send_message("/xinfo", None)
                self._client.send_message("/xremotenfb", None)
                while not self._shutdown_server_event.is_set():
                    self._client.handle_messages(constants.MESSAGE_TIMEOUT_SECONDS)
            except Exception:
                time.sleep(constants.CONNECTION_RECONNECTION_DELAY_SECONDS)

    def _snapshot_name_received(self, _address: str, snapshot_name: str) -> None:
        self._snapshot_name = snapshot_name
        self._message_received()

    def _snapshot_number_received(self, _address: str, snapshot_number: str) -> None:
        pub.sendMessage(
            PyPubSubTopics.HANDLE_CUE_LOAD,
            cue="{cue_number} {cue_name}".format(
                cue_number=snapshot_number, cue_name=self._snapshot_name
            ),
        )
        self._message_received()

    def _console_name_received(
        self,
        _address: str,
        _console_ip: str,
        console_name: str,
        _console_model: str,
        _console_version: str,
    ) -> None:
        self._console_name = console_name
        self._message_received()

    def _message_received(self, *_) -> None:
        pub.sendMessage(
            PyPubSubTopics.CONSOLE_CONNECTED, consolename=self._console_name
        )

    def heartbeat(self) -> None:
        if hasattr(self, "_client"):
            self._client.send_message("/xinfo", None)
            self._client.send_message("/xremotenfb", None)
