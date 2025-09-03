import time
from typing import Any, Callable

from pubsub import pub
from pythonosc import udp_client

import constants
from constants import PyPubSubTopics

from . import Console, Feature


class TheatreMix(Console):
    fixed_send_port: int = 32000  # pyright: ignore[reportIncompatibleVariableOverride]
    type = "TheatreMix"
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

        self._client.dispatcher.map("/subscribeok", self._subscribe_ok_received)
        self._client.dispatcher.map("/subscribefail", self._subscribe_fail_received)
        self._client.dispatcher.map("/cuefired", self._cue_number_received)
        self._client.dispatcher.map("/thump", self._message_received)
        self._client.dispatcher.set_default_handler(print)

        # Try connecting to the console and subscribing to updates
        while not self._shutdown_server_event.is_set():
            try:
                self.heartbeat()
                while not self._shutdown_server_event.is_set():
                    self._client.handle_messages(constants.MESSAGE_TIMEOUT_SECONDS)
            except Exception:
                time.sleep(constants.CONNECTION_RECONNECTION_DELAY_SECONDS)

    def _subscribe_ok_received(self, _address: str, expires_seconds: int) -> None:
        pub.sendMessage(PyPubSubTopics.CONSOLE_CONNECTED, consolename=None)

    def _subscribe_fail_received(self, _address: str) -> None:
        pub.sendMessage(PyPubSubTopics.CONSOLE_DISCONNECTED)

    def _cue_number_received(self, _address: str, cue_number: str) -> None:
        # TheatreMix (as of Sept. 2025) does not expose names via OSC. So just record the cue number
        pub.sendMessage(PyPubSubTopics.HANDLE_CUE_LOAD, cue=cue_number)

    def _message_received(self, _address: str, *_) -> None:
        pub.sendMessage(PyPubSubTopics.CONSOLE_CONNECTED, consolename=None)

    def heartbeat(self) -> None:
        if hasattr(self, "_client"):
            self._client.send_message("/thump", [])
            self._client.send_message("/subscribe", [])
