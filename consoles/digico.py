import socket
import threading
from typing import Any, Callable

import wx
from pubsub import pub
from pythonosc import dispatcher, osc_server, udp_client
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

import external_control
from constants import PlaybackState, PyPubSubTopics, TransportAction
from logger_config import logger

from . import Console, Feature


class RawMessageDispatcher(Dispatcher):
    def handle_error(self, OSCAddress: str, *args):
        # Handles malformed OSC messages and forwards on to console
        logger.debug(f"Received malformed OSC message at address: {OSCAddress}")
        try:
            # The last argument contains the raw message data
            raw_data = args[-1] if args else None
            if raw_data:
                # Forward the raw data exactly as received
                self.forward_raw_message(raw_data)
        except Exception as e:
            logger.error(f"Error forwarding malformed OSC message: {e}")

    @staticmethod
    def forward_raw_message(raw_data):
        from app_settings import settings

        # Forwards the raw message data without parsing
        logger.debug("Forwarding raw message.")
        try:
            # Create a raw UDP socket for forwarding
            forward_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Forward to the Digico console IP and receive port
            forward_socket.sendto(
                raw_data, (settings.console_ip, settings.receive_port)
            )
            forward_socket.close()
        except Exception as e:
            logger.error(f"Error forwarding raw message: {e}")


class RawOSCServer(ThreadingOSCUDPServer):
    def handle_request(self):
        # Override to get raw data before OSC parsing
        try:
            data, client_address = self.socket.recvfrom(65535)
            # If the raw data is not a multiple of 4 bytes, pad until it is
            # Let's at least try to make the data from the iPad valid OSC
            while len(data) % 4 != 0:
                data += bytes([0x00])
                logger.debug("Padding raw data to make it valid OSC.")
            # Try normal OSC handling first
            try:
                super().handle_request()
            except Exception as e:
                # If OSC parsing fails, handle as raw data
                logger.debug(f"OSC parsing failed, handling as raw data. {e}")
                if hasattr(self.dispatcher, "handle_error"):
                    self.dispatcher.handle_error("/", data)
        except Exception as e:
            logger.error(f"Error in raw server handler: {e}")


class DiGiCo(Console):
    type = "DiGiCo"
    supported_features = [
        Feature.CUE_NUMBER,
        Feature.REPEATER,
        Feature.SEPERATE_RECEIVE_PORT,
    ]

    def __init__(self):
        super().__init__()
        self.console_send_lock = threading.Lock()
        self.digico_osc_server = None
        self.repeater_osc_server = None
        pub.subscribe(self._shutdown_servers, PyPubSubTopics.SHUTDOWN_SERVERS)

    def start_managed_threads(
        self, start_managed_thread: Callable[[str, Any], None]
    ) -> None:
        from app_settings import settings

        logger.info("Starting OSC Server threads")
        start_managed_thread(
            "console_connection_thread", self._build_digico_osc_servers
        )
        if settings.forwarder_enabled:
            start_managed_thread(
                "repeater_osc_thread", self._build_repeater_osc_servers
            )

    def _build_digico_osc_servers(self):
        # Connect to the Digico console
        from utilities import find_local_ip_in_subnet

        logger.info("Starting Digico OSC server")
        from app_settings import settings

        self.console_client = udp_client.SimpleUDPClient(
            settings.console_ip, settings.console_port
        )
        self.digico_dispatcher = dispatcher.Dispatcher()
        self._receive_console_OSC()
        try:
            local_ip = find_local_ip_in_subnet(settings.console_ip)
            if not local_ip:
                raise RuntimeError("No local ip found in console's subnet")
            self.digico_osc_server = osc_server.ThreadingOSCUDPServer(
                (find_local_ip_in_subnet(settings.console_ip), settings.receive_port),
                self.digico_dispatcher,
            )
            logger.info("Digico OSC server started")
            self.digico_osc_server.serve_forever()
        except Exception as e:
            logger.error(f"Digico OSC server startup error: {e}")

    def _build_repeater_osc_servers(self):
        # Connect to Repeater via OSC
        logger.info("Starting Repeater OSC server")
        from app_settings import settings
        from utilities import find_local_ip_in_subnet

        self.repeater_client = udp_client.SimpleUDPClient(
            settings.repeater_ip, settings.repeater_port
        )
        # Custom dispatcher to deal with corrupted OSC from iPad
        self.repeater_dispatcher = RawMessageDispatcher()
        self._receive_repeater_OSC()
        try:
            # Raw OSC Server to deal with corrupted OSC from iPad App
            self.repeater_osc_server = RawOSCServer(
                (
                    find_local_ip_in_subnet(settings.console_ip),
                    settings.repeater_receive_port,
                ),
                self.repeater_dispatcher,
            )
            logger.info("Repeater OSC server started")
            self.repeater_osc_server.serve_forever()
        except Exception as e:
            logger.error(f"Repeater OSC server startup error: {e}")

    # Digico Functions

    def _receive_console_OSC(self):
        # Receives and distributes OSC from Digico, based on matching OSC values
        self.digico_dispatcher.map(
            "/Snapshots/Recall_Snapshot/*", self._request_snapshot_info
        )
        self.digico_dispatcher.map("/Snapshots/name", self.snapshot_OSC_handler)
        self.digico_dispatcher.map("/Macros/Recall_Macro/*", self._request_macro_info)
        self.digico_dispatcher.map("/Macros/name", self._macro_name_handler)
        self.digico_dispatcher.map("/Console/Name", self._console_name_handler)
        external_control.map_osc_external_control_dispatcher(self.digico_dispatcher)
        self.digico_dispatcher.set_default_handler(self._forward_OSC)

    def send_to_console(self, osc_address: str, *args):
        # Send an OSC message to the console
        with self.console_send_lock:
            self.console_client.send_message(osc_address, [*args])

    def _console_name_handler(self, osc_address: str, console_name: str):
        # Receives the console name response and updates the UI.
        from app_settings import settings

        if settings.forwarder_enabled:
            try:
                self.repeater_client.send_message(osc_address, console_name)
            except Exception as e:
                logger.error(f"Console name cannot be repeated: {e}")
        try:
            wx.CallAfter(
                pub.sendMessage,
                PyPubSubTopics.CONSOLE_CONNECTED,
                consolename=console_name,
            )
        except Exception as e:
            logger.error(f"Console Name Handler Error: {e}")

    def _request_snapshot_info(self, osc_address: str, *args):
        # Receives the OSC for the Current Snapshot Number and uses that to request the cue number/name
        from app_settings import settings

        if settings.forwarder_enabled:
            try:
                self.repeater_client.send_message(osc_address, *args)
            except Exception as e:
                logger.error(f"Snapshot info cannot be repeated: {e}")
        current_snapshot_number = int(osc_address.split("/")[3])
        with self.console_send_lock:
            self.console_client.send_message(
                "/Snapshots/name/?", current_snapshot_number
            )

    def _request_macro_info(self, osc_address: str, pressed):
        # When a Macro is pressed, request the name of the macro
        self.requested_macro_num = osc_address.split("/")[3]
        with self.console_send_lock:
            self.console_client.send_message(
                "/Macros/name/?", int(self.requested_macro_num)
            )

    def _macro_name_handler(self, osc_address: str, *args):
        # If macros match names, then send behavior to Reaper
        from app_settings import settings

        if settings.forwarder_enabled:
            try:
                self.repeater_client.send_message(osc_address, [*args])
            except Exception as e:
                logger.error(f"Macro name cannot be repeated: {e}")
        if self.requested_macro_num is not None:
            if int(self.requested_macro_num) == int(args[0]):
                macro_name = args[1]
                macro_name = str(macro_name).lower()
                logger.info(f"Macro {macro_name} received")
                if macro_name in (
                    "daw,rec",
                    "daw, rec",
                    "reaper, rec",
                    "reaper,rec",
                    "reaper rec",
                    "rec",
                    "record",
                    "reaper, record",
                    "reaper record",
                ):
                    pub.sendMessage(
                        PyPubSubTopics.TRANSPORT_ACTION,
                        transport_action=TransportAction.RECORD,
                    )
                elif macro_name in (
                    "daw,stop",
                    "daw, stop",
                    "reaper, stop",
                    "reaper,stop",
                    "reaper stop",
                    "stop",
                ):
                    pub.sendMessage(
                        PyPubSubTopics.TRANSPORT_ACTION,
                        transport_action=TransportAction.STOP,
                    )
                elif macro_name in (
                    "daw,play",
                    "daw, play",
                    "reaper, play",
                    "reaper,play",
                    "reaper play",
                    "play",
                ):
                    pub.sendMessage(
                        PyPubSubTopics.TRANSPORT_ACTION,
                        transport_action=TransportAction.PLAY,
                    )
                elif macro_name in (
                    "daw,marker",
                    "daw, marker",
                    "reaper, marker",
                    "reaper,marker",
                    "reaper marker",
                    "marker",
                ):
                    self.process_marker_macro()
                elif macro_name in (
                    "mode,rec",
                    "mode,record",
                    "mode,recording",
                    "mode rec",
                    "mode record",
                    "mode recording",
                ):
                    settings.marker_mode = PlaybackState.RECORDING
                    pub.sendMessage(
                        PyPubSubTopics.CHANGE_PLAYBACK_STATE,
                        selected_mode=PlaybackState.RECORDING,
                    )
                elif macro_name in (
                    "mode,track",
                    "mode,tracking",
                    "mode,PB Track",
                    "mode track",
                    "mode tracking",
                    "mode PB Track",
                ):
                    settings.marker_mode = PlaybackState.PLAYBACK_TRACK
                    pub.sendMessage(
                        PyPubSubTopics.CHANGE_PLAYBACK_STATE,
                        selected_mode=PlaybackState.PLAYBACK_TRACK,
                    )
                elif macro_name in (
                    "mode,no track",
                    "mode,no tracking",
                    "mode no track",
                    "mode no tracking",
                ):
                    settings.marker_mode = PlaybackState.PLAYBACK_NO_TRACK
                    pub.sendMessage(
                        PyPubSubTopics.CHANGE_PLAYBACK_STATE,
                        selected_mode=PlaybackState.PLAYBACK_NO_TRACK,
                    )
            self.requested_macro_num = None

    @staticmethod
    def process_marker_macro():
        pub.sendMessage(
            PyPubSubTopics.PLACE_MARKER_WITH_NAME, marker_name="Marker from Console"
        )

    def snapshot_OSC_handler(self, osc_address: str, *args):
        # Processes the current cue number
        from app_settings import settings

        if settings.forwarder_enabled:
            try:
                self.repeater_client.send_message(osc_address, [*args])
            except Exception as e:
                logger.error(f"Snapshot cue number cannot be repeated: {e}")
        cue_name = args[3]
        cue_number = str(args[1] / 100)
        cue_payload = cue_number + " " + cue_name
        logger.info(f"Digico recalled cue: {cue_payload}")
        pub.sendMessage(PyPubSubTopics.HANDLE_CUE_LOAD, cue=cue_payload)

    # Repeater Functions

    def _receive_repeater_OSC(self):
        self.repeater_dispatcher.set_default_handler(self.send_to_console)

    def _forward_OSC(self, osc_address: str, *args):
        from app_settings import settings

        if settings.forwarder_enabled:
            try:
                self.repeater_client.send_message(osc_address, [*args])
            except Exception as e:
                logger.error(f"Forwarder error: {e}")

    def heartbeat(self) -> None:
        with self.console_send_lock:
            assert isinstance(self.console_client, udp_client.UDPClient)
            self.console_client.send_message("/Console/Name/?", None)

    def _shutdown_servers(self):
        try:
            if self.digico_osc_server:
                self.digico_osc_server.shutdown()
                self.digico_osc_server.server_close()
                logger.info("Digico OSC Server shutdown completed")
        except Exception as e:
            logger.error(f"Error shutting down Digico server: {e}")
        try:
            if self.repeater_osc_server:
                self.repeater_osc_server.shutdown()
                self.repeater_osc_server.server_close()
                logger.info("Repeater OSC Server shutdown completed")
        except Exception as e:
            logger.error(f"Error shutting down OSC Repeater server: {e}")
