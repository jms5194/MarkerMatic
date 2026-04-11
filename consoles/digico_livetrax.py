import socket
from typing import Any, Callable

from pubsub import pub
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

import external_control
import constants
from constants import PlaybackState, PyPubSubTopics, TransportAction, ArmedAction
from logger_config import logger
import utilities

from . import Console, Feature

class DiGiCo_LiveTrax(Console):
    fixed_receive_port: int = 3819
    type = "DiGiCo_LiveTrax"
    supported_features = [
        Feature.CUE_NUMBER,
        Feature.SEPERATE_RECEIVE_PORT,
        Feature.MACROS,
    ]

    def __init__(self):
        super().__init__()
        self.digico_osc_server = None
        pub.subscribe(self._shutdown_servers, PyPubSubTopics.SHUTDOWN_SERVERS)

    def start_managed_threads(
        self, start_managed_thread: Callable[[str, Callable[..., Any]], None]
    ) -> None:
        logger.info("Starting OSC Server threads")
        start_managed_thread(
            "console_connection_thread", self._build_digico_osc_servers
        )

    def _build_digico_osc_servers(self) -> None:
        # Connect to the Digico console
        logger.info("Starting Digico OSC server")
        from app_settings import settings

        self.digico_dispatcher = Dispatcher()
        self._receive_console_OSC(macros_enabled=settings.macros_enabled)
        try:
            self.digico_osc_server = ThreadingOSCUDPServer(
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

    def _receive_console_OSC(self, macros_enabled=True) -> None:
        """Receives and distributes OSC from Digico, based on matching OSC values"""
        self.digico_dispatcher.map("/snapshot", self.snapshot_OSC_handler)
        if macros_enabled:
            self.digico_dispatcher.set_default_handler(self._macro_name_handler)
        external_control.map_osc_external_control_dispatcher(self.digico_dispatcher)

    def snapshot_OSC_handler(self, osc_address: str, *args) -> None:
        pub.sendMessage(PyPubSubTopics.CONSOLE_CONNECTED)

        # Processes the current cue number
        from app_settings import settings

        cue_payload = args[0]
        
        # if this cue is in a group, the cue number will have a "+" prepended
        if cue_payload[0] == "+":
            cue_payload = cue_payload[1:]
        
        logger.info(f"Digico recalled cue: {cue_payload}")
        pub.sendMessage(PyPubSubTopics.HANDLE_CUE_LOAD, cue=cue_payload)

    def _macro_name_handler(self, osc_address: str, *args) -> None:
        pub.sendMessage(PyPubSubTopics.CONSOLE_CONNECTED)

        # If macros match names, then send behavior to Reaper
        from app_settings import settings

        macro_name = osc_address[1:]
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
            "transport_stop",
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
            "transport_play",
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
            "add_marker",
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
        elif macro_name in (
            "reaper, arm_all",
            "reaper, arm",
            "reaper arm_all",
            "reaper arm",
            "arm, all",
            "arm,all",
            "arm all",
            "arm",
        ):
            pub.sendMessage(
                PyPubSubTopics.ARMED_ACTION,
                armed_action=ArmedAction.ARM_ALL,
            )
        elif macro_name in (
            "reaper, disarm_all",
            "reaper, disarm",
            "reaper disarm_all",
            "reaper disarm",
            "disarm, all",
            "disarm,all",
            "disarm all",
            "disarm",
        ):
            pub.sendMessage(
                PyPubSubTopics.ARMED_ACTION,
                armed_action=ArmedAction.DISARM_ALL,
            )

    @staticmethod
    def process_marker_macro():
        pub.sendMessage(
            PyPubSubTopics.PLACE_MARKER_WITH_NAME, marker_name="Marker from Console"
        )

    def _shutdown_servers(self) -> None:
        try:
            if self.digico_osc_server:
                self.digico_osc_server.shutdown()
                self.digico_osc_server.server_close()
                logger.info("Digico OSC Server shutdown completed")
        except Exception as e:
            logger.error(f"Error shutting down Digico server: {e}")
