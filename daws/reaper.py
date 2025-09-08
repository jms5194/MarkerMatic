import threading
import time
from typing import Any, Callable

from pubsub import pub
from pythonosc import dispatcher, osc_server, udp_client

import constants
from constants import PlaybackState, PyPubSubTopics, TransportAction
from logger_config import logger

from . import Daw, configure_reaper


class Reaper(Daw):
    type = "Reaper"
    _shutdown_server_event = threading.Event()
    _connected = threading.Event()
    _connection_check_lock = threading.Lock()
    _connection_timeout_counter = 0

    def __init__(self):
        super().__init__()
        self.reaper_send_lock = threading.Lock()
        self.name_to_match = ""
        self.is_playing = False
        self.is_recording = False
        self.reaper_osc_server = None
        pub.subscribe(
            self._place_marker_with_name, PyPubSubTopics.PLACE_MARKER_WITH_NAME
        )
        pub.subscribe(self._incoming_transport_action, PyPubSubTopics.TRANSPORT_ACTION)
        pub.subscribe(self._handle_cue_load, PyPubSubTopics.HANDLE_CUE_LOAD)
        pub.subscribe(self._shutdown_servers, PyPubSubTopics.SHUTDOWN_SERVERS)
        pub.subscribe(self._shutdown_server_event.set, PyPubSubTopics.SHUTDOWN_SERVERS)

    def start_managed_threads(
        self, start_managed_thread: Callable[[str, Any], None]
    ) -> None:
        logger.info("Starting Reaper Connection threads")
        self._shutdown_server_event.clear()
        start_managed_thread(
            "validate_reaper_prefs_thread", self._validate_reaper_prefs
        )
        start_managed_thread("daw_connection_thread", self._build_reaper_osc_servers)
        start_managed_thread("daw_connection_monitor", self._daw_connection_monitor)

    def _daw_connection_monitor(self):
        while not self._shutdown_server_event.is_set():
            time.sleep(1)
            with self._connection_check_lock:
                self._connection_timeout_counter += 1
                if self._connection_timeout_counter == constants.CHECK_CONNECTION_TIME:
                    self._refresh_control_surfaces()
                elif (
                    self._connection_timeout_counter
                    >= constants.CHECK_CONNECTION_TIME_COMBINED
                ):
                    self._connected.clear()
                    pub.sendMessage(
                        PyPubSubTopics.DAW_CONNECTION_STATUS, connected=False
                    )
                    self._connection_timeout_counter = 0

    def _validate_reaper_prefs(self):
        # If the Reaper .ini file does not contain an entry for Digico-Reaper Link, add one.
        from app_settings import settings

        while not self._shutdown_server_event.is_set():
            try:
                if not self._check_reaper_prefs(
                    settings.reaper_receive_port, settings.reaper_port
                ):
                    self._add_reaper_prefs(
                        settings.reaper_receive_port, settings.reaper_port
                    )
                    pub.sendMessage(
                        PyPubSubTopics.REQUEST_DAW_RESTART, daw_name="Reaper"
                    )
                return True
            except RuntimeError:
                # If reaper is not running, wait and try again
                logger.error("Reaper not running. Will retry in 1 seconds.")
                time.sleep(1)
        return None

    @staticmethod
    def _check_reaper_prefs(rpr_rcv, rpr_send):
        if configure_reaper.osc_interface_exists(
            configure_reaper.get_resource_path(True), rpr_rcv, rpr_send
        ):
            logger.info("Reaper OSC interface config already exists")
            return True
        else:
            logger.info("Reaper OSC interface config does not exist")
            return False

    @staticmethod
    def _add_reaper_prefs(rpr_rcv, rpr_send):
        configure_reaper.add_OSC_interface(
            configure_reaper.get_resource_path(True), rpr_rcv, rpr_send
        )
        logger.info("Added OSC interface to Reaper preferences")

    def _build_reaper_osc_servers(self):
        # Connect to Reaper via OSC
        from app_settings import settings

        logger.info("Starting Reaper OSC server")
        self.reaper_client = udp_client.SimpleUDPClient(
            constants.IP_LOOPBACK, settings.reaper_port
        )
        self.reaper_dispatcher = dispatcher.Dispatcher()
        self._receive_reaper_OSC()
        try:
            self.reaper_osc_server = osc_server.ThreadingOSCUDPServer(
                (constants.IP_LOOPBACK, settings.reaper_receive_port),
                self.reaper_dispatcher,
            )
            logger.info("Reaper OSC server started")
            self.reaper_osc_server.serve_forever()
        except Exception as e:
            logger.error(f"Reaper OSC server startup error: {e}")

    def _receive_reaper_OSC(self):
        # Receives and distributes OSC from Reaper, based on matching OSC values
        self.reaper_dispatcher.map("/marker/*/name", self._marker_matcher)
        self.reaper_dispatcher.map("/play", self._current_transport_state)
        self.reaper_dispatcher.map("/record", self._current_transport_state)
        self.reaper_dispatcher.set_default_handler(self._message_received)

    def _message_received(self, *_) -> None:
        if not self._connected.is_set():
            self._connected.set()
            # Always refresh control surfaces on connection have Reaper's state
            self._refresh_control_surfaces()
            pub.sendMessage(PyPubSubTopics.DAW_CONNECTION_STATUS, connected=True)
        with self._connection_check_lock:
            self._connection_timeout_counter = 0

    def _marker_matcher(self, osc_address, test_name):
        self._message_received()
        # Matches a marker composite name with its Reaper ID
        from app_settings import settings

        address_split = osc_address.split("/")
        marker_id = address_split[2]
        if settings.name_only_match:
            test_name = test_name.split(" ")
            test_name = test_name[1:]
            test_name = " ".join(test_name)
        if test_name == self.name_to_match:
            self._goto_marker_by_id(marker_id)

    def _current_transport_state(self, osc_address, val):
        self._message_received()
        # Watches what the Reaper playhead is doing.
        playing = None
        recording = None
        if osc_address == "/play":
            if val == 0:
                playing = False
            elif val == 1:
                playing = True
        elif osc_address == "/record":
            if val == 0:
                recording = False
            elif val == 1:
                recording = True
        if playing is True:
            self.is_playing = True
            logger.info("Reaper is playing")
        elif playing is False:
            self.is_playing = False
            logger.info("Reaper is not playing")
        if recording is True:
            self.is_recording = True
            logger.info("Reaper is recording")
        elif recording is False:
            self.is_recording = False
            logger.info("Reaper is not recording")

    def _refresh_control_surfaces(self) -> None:
        with self.reaper_send_lock:
            self.reaper_client.send_message("/action", 41743)

    def _goto_marker_by_id(self, marker_id):
        with self.reaper_send_lock:
            self.reaper_client.send_message("/marker", int(marker_id))

    def _place_marker_with_name(self, marker_name: str):
        logger.info(f"Placed marker for cue: {marker_name}")
        with self.reaper_send_lock:
            self.reaper_client.send_message("/action", 40157)
            self.reaper_client.send_message("/lastmarker/name", marker_name)

    def get_marker_id_by_name(self, name: str):
        # Asks for current marker information based upon number of markers.
        from app_settings import settings

        if self.is_playing is False:
            self.name_to_match = name
            if settings.name_only_match:
                self.name_to_match = self.name_to_match.split(" ")
                self.name_to_match = self.name_to_match[1:]
                self.name_to_match = " ".join(self.name_to_match)
            with self.reaper_send_lock:
                self.reaper_client.send_message("/device/marker/count", 0)
                # Is there a better way to handle this in OSC only? Max of 512 markers.
                self.reaper_client.send_message("/device/marker/count", 512)

    def _incoming_transport_action(self, transport_action: TransportAction):
        try:
            if transport_action is TransportAction.PLAY:
                self._reaper_play()
            elif transport_action is TransportAction.STOP:
                self._reaper_stop()
            elif transport_action is TransportAction.RECORD:
                self._reaper_rec()
        except Exception as e:
            logger.error(f"Error processing transport macros: {e}")

    def _reaper_play(self):
        with self.reaper_send_lock:
            self.reaper_client.send_message("/action", 1007)

    def _reaper_stop(self):
        with self.reaper_send_lock:
            self.reaper_client.send_message("/action", 1016)

    def _reaper_rec(self):
        # Sends action to skip to end of project and then record, to prevent overwrites
        from app_settings import settings

        settings.marker_mode = PlaybackState.RECORDING
        pub.sendMessage(
            PyPubSubTopics.CHANGE_PLAYBACK_STATE, selected_mode=PlaybackState.RECORDING
        )
        with self.reaper_send_lock:
            self.reaper_client.send_message("/action", 40043)
            self.reaper_client.send_message("/action", 1013)

    def _handle_cue_load(self, cue: str) -> None:
        from app_settings import settings

        if (
            settings.marker_mode is PlaybackState.RECORDING
            and self.is_recording is True
        ):
            self._place_marker_with_name(cue)
        elif (
            settings.marker_mode is PlaybackState.PLAYBACK_TRACK
            and self.is_playing is False
        ):
            self.get_marker_id_by_name(cue)

    def _shutdown_servers(self):
        try:
            if self.reaper_osc_server:
                self.reaper_osc_server.shutdown()
                self.reaper_osc_server.server_close()
            logger.info("Reaper OSC Server shutdown completed")
        except Exception as e:
            logger.error(f"Error shutting down Reaper server: {e}")
