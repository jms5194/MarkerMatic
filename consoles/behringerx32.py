import time
from enum import Enum
from typing import Any, Callable, List

from pubsub import pub
from pythonosc import udp_client

import constants
from constants import PyPubSubTopics
from logger_config import logger

from . import Console, Feature


class BehringerX32ShowControlMode(Enum):
    CUE = 0
    SCENE = 1
    SNIPPET = 2


class BehringerX32(Console):
    fixed_send_port: int = 10023
    type = "Behringer X32"
    supported_features = [Feature.CUE_NUMBER]
    _client: udp_client.DispatchClient
    _console_name: str
    _snapshot_name: str
    _show_control_mode: BehringerX32ShowControlMode

    def start_managed_threads(
        self, start_managed_thread: Callable[[str, Callable[..., Any]], None]
    ) -> None:
        start_managed_thread("console_connection_thread", self._console_client_thread)

    def _console_client_thread(self) -> None:
        from app_settings import settings

        self._client = udp_client.DispatchClient(
            settings.console_ip, self.fixed_send_port
        )
        for show_control_mode in BehringerX32ShowControlMode:
            self._client.dispatcher.map(
                f"/-show/showfile/{show_control_mode.name.lower()}/*/name",
                self._cue_name_received,
                show_control_mode,
            )
        self._client.dispatcher.map(
            "/-show/showfile/cue/*/numb", self._cue_cue_number_received
        )
        self._client.dispatcher.map(
            "/-show/prepos/current", self._internal_cue_number_received
        )
        self._client.dispatcher.map("/xinfo", self._console_name_received)
        self._client.dispatcher.map(
            "/-prefs/show_control", self._show_control_mode_received
        )
        # self._client.dispatcher.set_default_handler(self._message_received)
        self._client.dispatcher.set_default_handler(print)
        # Try connecting to the console, and subscribing to updates
        while not self._shutdown_server_event.is_set():
            try:
                self.heartbeat()
                while not self._shutdown_server_event.is_set():
                    self._client.handle_messages(constants.MESSAGE_TIMEOUT_SECONDS)
            except Exception:
                time.sleep(constants.CONNECTION_RECONNECTION_DELAY_SECONDS)

    def _show_control_mode_received(
        self, _address: str, show_control_mode: int
    ) -> None:
        self._message_received()
        self._show_control_mode = BehringerX32ShowControlMode(show_control_mode)

    def _internal_cue_number_received(
        self, _address: str, internal_cue_number: int
    ) -> None:
        self._message_received()
        self._cue_number = internal_cue_number
        if self._show_control_mode is BehringerX32ShowControlMode.CUE:
            self._client.send_message(
                f"/-show/showfile/{self._show_control_mode.name.lower()}/{internal_cue_number:03}/numb",
                None,
            )
        if internal_cue_number != -1:
            self._client.send_message(
                f"/-show/showfile/{self._show_control_mode.name.lower()}/{internal_cue_number:03}/name",
                None,
            )

    def _cue_cue_number_received(self, _address: str, cue_number: int) -> None:
        self._cue_number = f"{cue_number:05}"
        self._cue_number = ".".join(
            [
                str(int(cue_section))
                for cue_section in (
                    self._cue_number[:-2],
                    self._cue_number[-1],
                    self._cue_number[-0],
                )
                if int(cue_section)
            ]
        )

    def _cue_name_received(
        self,
        _address: str,
        cue_type: List[BehringerX32ShowControlMode],
        cue_name: str,
    ) -> None:
        logger.info(f"Received a {cue_type[0]} named {cue_name}")
        self._message_received()
        if cue_type[0] is self._show_control_mode and self._cue_number != -1:
            pub.sendMessage(
                PyPubSubTopics.HANDLE_CUE_LOAD, cue=f"{self._cue_number} {cue_name}"
            )

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
            self._client.send_message("/xremote", None)
            self._client.send_message("/-prefs/show_control", None)
