import time
from typing import Any, Callable, Optional

from pubsub import pub
from pythonosc import udp_client

import constants
from constants import PyPubSubTopics

from . import Console


class Dmitri(Console):
    fixed_send_port: int = 18033  # pyright: ignore[reportIncompatibleVariableOverride]
    type = "D'Mitri"
    supported_features = []
    _client: udp_client.DispatchClient
    selected_list = "1"

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
        if (
            args[1] == f"Automation {self.selected_list} Active Cue Name"
            and args[3] == f"Automation {self.selected_list} Active Cue ID"
        ):
            cue_name = str(args[2])
            cue_id = str(args[4])
            new_cue = cue_id + " " + cue_name
            pub.sendMessage(PyPubSubTopics.HANDLE_CUE_LOAD, cue=new_cue)
        self._message_received()

    def _message_received(self, *_) -> None:
        pub.sendMessage(PyPubSubTopics.CONSOLE_CONNECTED)

    def heartbeat(self) -> None:
        if hasattr(self, "_client"):
            # Send ping message to Nadia, it will respond with pong and MarkerMatic identifier
            self._client.send_message("/ping", "MarkerMatic")

    def _cue_list_subscribe(self) -> None:
        if hasattr(self, "_client"):
            self._client.send_message(
                "/subscribe", f"Automation {self.selected_list} Active Cue ID"
            )
            self._client.send_message(
                "/subscribe", f"Automation {self.selected_list} Active Cue Name"
            )
