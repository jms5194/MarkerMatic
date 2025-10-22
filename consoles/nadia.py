import time
from typing import Any, Callable, Optional

from pubsub import pub
from pythonosc import udp_client

import constants
from constants import PyPubSubTopics

from . import Console


class Nadia(Console):
    fixed_send_port: int = 28133  # pyright: ignore[reportIncompatibleVariableOverride]
    type = "Nadia"
    supported_features = []
    _client: udp_client.DispatchClient

    def start_managed_threads(
        self, start_managed_thread: Callable[[str, Callable[..., Any]], None]
    ) -> None:
        start_managed_thread("console_connection_thread", self._console_client_thread)

    def _console_client_thread(self) -> None:
        from app_settings import settings

        self._client = udp_client.DispatchClient(
            settings.console_ip, self.fixed_send_port
        )

        self._client.dispatcher.map("/pong", self._subscribe_ok_received)
        self._client.dispatcher.map("/subscribefail", self._subscribe_fail_received)
        self._client.dispatcher.map("/got", self._subscribed_data_received)
        self._client.dispatcher.set_default_handler(self._message_received)
        self._cue_list_subscribe()

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

    def _subscribed_data_received(self, _address, *args):
        for i in args:
            print(i)

        # pub.sendMessage(PyPubSubTopics.HANDLE_CUE_LOAD, cue=cue_number)
        self._message_received()

    def _message_received(self, *_) -> None:
        pub.sendMessage(PyPubSubTopics.CONSOLE_CONNECTED)

    def heartbeat(self) -> None:
        if hasattr(self, "_client"):
            # Send ping message to Nadia, it will respond with pong and MarkerMatic identifier
            self._client.send_message("/ping", "MarkerMatic")

    def _cue_list_subscribe(self) -> None:
        if hasattr(self, "_client"):
            self._client.send_message("/subscribe", "CueListPlayer 1 Active Cue ID")
            self._client.send_message("/subscribe", "CueListPlayer 1 Active Cue Name")
