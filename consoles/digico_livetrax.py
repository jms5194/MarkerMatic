import socket
import threading
from typing import Any, Callable

import wx
from pubsub import pub
from pythonosc import dispatcher, osc_server, udp_client
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

import constants
import time
import external_control
import utilities
from constants import PlaybackState, PyPubSubTopics, TransportAction, ArmedAction
from logger_config import logger

from . import Console, Feature

class DiGiCoLiveTrax(Console):
    type = "DiGiCo_LiveTrax"
    supported_features = [
        Feature.CUE_NUMBER,
        Feature.REPEATER,
        Feature.SEPERATE_RECEIVE_PORT,
        Feature.MACROS,
    ]

    def __init__(self):
        super().__init__()
        self.console_send_lock = threading.Lock()
        self.digico_osc_server = None
        self.repeater_osc_server = None
        self.last_armed_state = False
        self._shutdown_server_event = threading.Event()
        self._connected = threading.Event()
        self._connection_check_lock = threading.Lock()
        self._connection_timeout_counter = 0
        pub.subscribe(self._shutdown_servers, PyPubSubTopics.SHUTDOWN_SERVERS)

    def start_managed_threads(
        self, start_managed_thread: Callable[[str, Any], None]
    ) -> None:
        from app_settings import settings

        logger.info("Starting OSC Server threads")
        start_managed_thread(
            "console_connection_thread", self._build_digico_osc_servers
        )
        start_managed_thread("console_connection_monitor", self._console_connection_monitor())

    def _console_connection_monitor(self) -> None:
        while not self._shutdown_server_event.is_set():
            time.sleep(1)
            with self._connection_check_lock:
                self._connection_timeout_counter += 1
                if self._connection_timeout_counter == constants.CHECK_CONNECTION_TIME:
                    self._refresh_console_connection()
                elif (
                    self._connection_timeout_counter
                    >= constants.CHECK_CONNECTION_TIME_COMBINED
                ):
                    self._connected.clear()
                    pub.sendMessage(
                        PyPubSubTopics.DAW_CONNECTION_STATUS, connected=False
                    )
                    self._connection_timeout_counter = 0

    def _build_digico_osc_servers(self) -> None:
        # Connect to the Digico console
        logger.info("Starting Digico OSC server")
        from app_settings import settings

        self.console_client = udp_client.SimpleUDPClient(
            settings.console_ip, settings.console_port
        )
        self.digico_dispatcher = dispatcher.Dispatcher()
        self._receive_console_OSC(macros_enabled=settings.macros_enabled)
        try:
            self.digico_osc_server = osc_server.ThreadingOSCUDPServer(
                (
                    utilities.get_ip_listen_any(settings.console_ip),
                    settings.receive_port,
                ),
                self.digico_dispatcher,
            )
            logger.info("Digico OSC server started")
            self.digico_osc_server.serve_forever()
        except Exception as e:
            logger.error(f"Digico OSC server startup error: {e}")

    # Digico Functions

    def _receive_console_OSC(self, macros_enabled=True) -> None:
        """Receives and distributes OSC from Digico, based on matching OSC values"""
        self.digico_dispatcher.map("/snapshots", self.snapshot_OSC_handler)
        if macros_enabled:
            self.digico_dispatcher.map("/transport_play", self._macro_play_handler)
            self.digico_dispatcher.map("/transport_stop", self._macro_stop_handler)
            self.digico_dispatcher.map("/add_marker", self._macro_marker_handler)
            self.digico_dispatcher.map("/transport_arm", self._macro_arm_handler)
        external_control.map_osc_external_control_dispatcher(self.digico_dispatcher)
        self.digico_dispatcher.set_default_handler(self._message_received)

    def _message_received(self, *_) -> None:
        if not self._connected.is_set():
            self._connected.set()
            # Always refresh control surfaces on conn
            self._refresh_control_surfaces()
            pub.sendMessage(PyPubSubTopics.DAW_CONNECTION_STATUS, connected=True)
        with self._connection_check_lock:
            self._connection_timeout_counter = 0

    def send_to_console(self, osc_address: str, *args) -> None:
        # Send an OSC message to the console
        with self.console_send_lock:
            self.console_client.send_message(osc_address, [*args])

    def _macro_play_handler(self, osc_address: str, *args) -> None:
        self._message_received()
        pub.sendMessage(
            PyPubSubTopics.TRANSPORT_ACTION,
            transport_action=TransportAction.PLAY,
        )

    def _macro_stop_handler(self, osc_address: str, *args) -> None:
        self._message_received()
        pub.sendMessage(
            PyPubSubTopics.TRANSPORT_ACTION,
            transport_action=TransportAction.STOP,
        )

    def _macro_arm_handler(self, osc_address: str, *args) -> None:
        self._message_received()
        # There's a better way to make this a toggle, I think.
        if self.last_armed_state:
            pub.sendMessage(
                PyPubSubTopics.ARMED_ACTION,
                armed_action=ArmedAction.DISARM_ALL,
            )
            self.last_armed_state = False
        elif not self.last_armed_state:
            pub.sendMessage(
                PyPubSubTopics.ARMED_ACTION,
                armed_action=ArmedAction.ARM_ALL,
            )
            self.last_armed_state = True

    def _macro_marker_handler(self, osc_address: str, *args) -> None:
        self._message_received()
        self.process_marker_macro()

    def _refresh_console_connection(self) -> None:
        with self.console_send_lock:
            self.console_client.send_message("/request_names", None)

    @staticmethod
    def process_marker_macro():
        pub.sendMessage(
            PyPubSubTopics.PLACE_MARKER_WITH_NAME, marker_name="Marker from Console"
        )

    def snapshot_OSC_handler(self, osc_address: str, *args) -> None:
        self._message_received()
        pub.sendMessage(PyPubSubTopics.CONSOLE_CONNECTED)
        # 1st arg is current snapshot string
        cue_payload = args[0]

        # Remove the leading + from snapshots that are in groups
        if cue_payload.startswith("+"):
            cue_payload = cue_payload[1:]

        logger.info(f"Digico recalled cue: {cue_payload}")
        pub.sendMessage(PyPubSubTopics.HANDLE_CUE_LOAD, cue=cue_payload)

    def _shutdown_servers(self) -> None:
        try:
            if self.digico_osc_server:
                self.digico_osc_server.shutdown()
                self.digico_osc_server.server_close()
                logger.info("Digico OSC Server shutdown completed")
        except Exception as e:
            logger.error(f"Error shutting down Digico server: {e}")
