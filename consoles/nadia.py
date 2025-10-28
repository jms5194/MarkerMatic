import time
from typing import Any, Callable, Optional
from logger_config import logger
from pubsub import pub
from pythonosc import udp_client

import constants
from constants import PyPubSubTopics

from . import Console, Feature


class Nadia(Console):
    fixed_send_port: int = 28133  # pyright: ignore[reportIncompatibleVariableOverride]
    type = "Nadia"
    supported_features = [Feature.CUE_LIST_PLAYER]
    _client: udp_client.DispatchClient
    _sent_subscribe = False

    def start_managed_threads(
        self, start_managed_thread: Callable[[str, Callable[..., Any]], None]
    ) -> None:
        logger.info("Starting Nadia Connection thread")
        start_managed_thread("console_connection_thread", self._console_client_thread)

    def _console_client_thread(self) -> None:
        from app_settings import settings

        self.selected_list = settings.cue_list_player

        self._client = udp_client.DispatchClient(
            settings.console_ip, self.fixed_send_port
        )

        self._client.dispatcher.map("/pong", self._pong_received)
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
        self._sent_subscribe = False

    def _pong_received(self, _address: str, _expires_seconds: int) -> None:
        if not self._sent_subscribe:
            self._cue_list_subscribe()
            self._sent_subscribe = True
        else:
            self._message_received()

    def _subscribed_data_received(self, _address, *args):
        if args[1] == f"CueListPlayer {self.selected_list} Active Cue Name" and args[3] == f"CueListPlayer {self.selected_list} Active Cue ID":
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
            logger.info("Subscribing to Meyer control points")
            self._client.send_message("/unsubscribeall", None)
            self._client.send_message("/subscribe", f"CueListPlayer {self.selected_list} Active Cue ID")
            self._client.send_message("/subscribe", f"CueListPlayer {self.selected_list} Active Cue Name")
