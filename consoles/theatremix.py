import time
from typing import Any, Callable, Optional

from pubsub import pub
from pythonosc import udp_client

import constants
from constants import PyPubSubTopics

from . import Console


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
        self._client.dispatcher.set_default_handler(self._message_received)

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

    def _cue_number_received(
        self, _address: str, cue_number: str, cue_name: Optional[str] = None, *_
    ) -> None:
        if cue_name is not None:
            # Cue names are only supported in TheatreMix 3.4 or above
            cue_number = f"{cue_number} {cue_name}"
        pub.sendMessage(PyPubSubTopics.HANDLE_CUE_LOAD, cue=cue_number)
        self._message_received()

    def _message_received(self, *_) -> None:
        pub.sendMessage(PyPubSubTopics.CONSOLE_CONNECTED)

    def heartbeat(self) -> None:
        if hasattr(self, "_client"):
            self._client.send_message("/subscribe", [])
