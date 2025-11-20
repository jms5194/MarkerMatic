import threading
import time
from typing import Any, Callable

from pubsub import pub
from pythonosc import dispatcher, osc_server, udp_client

import constants
from constants import PlaybackState, PyPubSubTopics, TransportAction
from logger_config import logger

from . import Daw, configure_ableton


class Ableton(Daw):
    type = "Ableton Live"
    _shutdown_server_event = threading.Event()
    _connected = threading.Event()
    _connection_check_lock = threading.Lock()
    _connection_timeout_counter = 0

    def __init__(self):
        super().__init__()
        self.ableton_send_lock = threading.Lock()
        self.name_to_match = ""
        self.is_playing = False
        self.is_recording = False
        self.ableton_osc_server = None
        self._name_flag = threading.Event()
        self.transport_state_validated = threading.Event()
        self.is_playing_validated = threading.Event()
        self.is_recording_validated = threading.Event()
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
        logger.info("Starting Ableton Connection threads")
        self._shutdown_server_event.clear()
        start_managed_thread("daw_connection_thread", self._build_ableton_osc_servers)
        start_managed_thread("daw_connection_monitor", self._daw_connection_monitor)

    def _daw_connection_monitor(self) -> None:
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

    def _refresh_control_surfaces(self) -> None:
        with self.ableton_send_lock:
            self.ableton_client.send_message("/live/application/get/version", None)

    def _build_ableton_osc_servers(self) -> None:
        # Connect to Ableton via OSC

        logger.info("Starting Ableton OSC server")
        self.ableton_client = udp_client.SimpleUDPClient(
            constants.IP_LOOPBACK, constants.PORT_ABLETON_OSC_SEND
        )
        self.ableton_dispatcher = dispatcher.Dispatcher()
        self._receive_ableton_OSC()
        try:
            self.ableton_osc_server = osc_server.ThreadingOSCUDPServer(
                (constants.IP_LOOPBACK, constants.PORT_ABLETON_OSC_RECEIVE),
                self.ableton_dispatcher,
            )
            logger.info("Ableton OSC server started")
            self.ableton_osc_server.serve_forever()
        except Exception as e:
            logger.error(f"Ableton OSC server startup error: {e}")

    def _receive_ableton_OSC(self) -> None:
        # Receives and distributes OSC from Reaper, based on matching OSC values
        self.ableton_dispatcher.map("/live/song/get/cue_points", self._marker_matcher)
        self.ableton_dispatcher.map("/live/song/get/is_playing", self._current_transport_state)
        self.ableton_dispatcher.map("/live/song/get/session_record", self._current_transport_state)
        self.ableton_dispatcher.set_default_handler(self._message_received)

    def _message_received(self, *_) -> None:
        if not self._connected.is_set():
            self._connected.set()
            pub.sendMessage(PyPubSubTopics.DAW_CONNECTION_STATUS, connected=True)
        with self._connection_check_lock:
            self._connection_timeout_counter = 0

    def _marker_matcher(self, osc_address: str, *args):
        from app_settings import settings
        self._message_received()
        # If name flag is set, we're labeling a new marker instead of matching an existing one.
        if self._name_flag.is_set():
            # We need to refer to markers by index, so we find the index number of the last marker placed
            _last_marker = int((len(args) / 2)  - 1)
            self.ableton_client.send_message("/live/song/cue_point/set/name", [_last_marker, self._new_marker_name])
            self._name_flag.clear()
        else:
            # Matches a marker composite name with its Ableton Live Index
            test_name = args[0]
            if settings.name_only_match:
                test_name = test_name.split(" ")
                test_name = test_name[1:]
                test_name = " ".join(test_name)

            _available_names = args[1::2]
            for marker in _available_names:
                if test_name == marker:
                    self._goto_marker_by_name(marker)
                    break

    def _current_transport_state(self, osc_address: str, val):
        self._message_received()
        # Watches what the Ableton playhead is doing.
        playing = None
        recording = None
        if osc_address == "/live/song/get/is_playing":
            self.is_playing_validated.set()
            if val == False:
                playing = False
            elif val == True:
                playing = True
        elif osc_address == "/live/song/get/session_record":
            self.is_recording_validated.set()
            if val == True:
                recording = False
            elif val == False:
                recording = True
        if playing is True:
            self.is_playing = True
            logger.info("Ableton is playing")
        elif playing is False:
            self.is_playing = False
            logger.info("Ableton is not playing")
        if recording is True:
            self.is_recording = True
            logger.info("Ableton is recording")
        elif recording is False:
            self.is_recording = False
            logger.info("Ableton is not recording")
        if self.is_playing_validated.is_set() and self.is_recording_validated.is_set():
            self.transport_state_validated.set()
            self.is_playing_validated.clear()
            self.is_recording_validated.clear()

    def _goto_marker_by_name(self, marker_name):
        from app_settings import settings
        if self.is_playing is False:
            if settings.name_only_match:
                pass
            else:
                with self.ableton_send_lock:
                    self.ableton_client.send_message("/live/song/cue_point/jump", marker_name)

    def _place_marker_with_name(self, marker_name: str):
        logger.info(f"Placed marker for cue: {marker_name}")
        with self.ableton_send_lock:
            self.ableton_client.send_message("/live/song/cue_point/add_or_delete", None)
            self._new_marker_name = marker_name
            self._name_flag.set()
            self.ableton_client.send_message("/live/song/get/cue_points", None)

    def get_marker_id_by_name(self, name: str):
        # Asks for current marker information based upon number of markers.
        from app_settings import settings
        self.transport_state_validated.wait()
        if self.is_playing is False:
            self.name_to_match = name
            if settings.name_only_match:
                self.name_to_match = self.name_to_match.split(" ")
                self.name_to_match = self.name_to_match[1:]
                self.name_to_match = " ".join(self.name_to_match)
            with self.ableton_send_lock:
                self.ableton_client.send_message("/live/song/get/cue_points", None)

    def _incoming_transport_action(self, transport_action: TransportAction):
        try:
            if transport_action is TransportAction.PLAY:
                self._ableton_play()
            elif transport_action is TransportAction.STOP:
                self._ableton_stop()
            elif transport_action is TransportAction.RECORD:
                self._ableton_rec()
        except Exception as e:
            logger.error(f"Error processing transport macros: {e}")

    def _ableton_play(self) -> None:
        with self.ableton_send_lock:
            self.ableton_client.send_message("/live/song/start_playing", None)

    def _ableton_stop(self) -> None:
        with self.ableton_send_lock:
            self.ableton_client.send_message("/live/song/stop_playing", None)

    def _ableton_rec(self) -> None:
        from app_settings import settings

        settings.marker_mode = PlaybackState.RECORDING
        pub.sendMessage(
            PyPubSubTopics.CHANGE_PLAYBACK_STATE, selected_mode=PlaybackState.RECORDING
        )
        with self.ableton_send_lock:
            self.ableton_client.send_message("/live/song/trigger_session_record", None)

    def _update_current_transport_state(self) -> None:
        with self.ableton_send_lock:
            self.ableton_client.send_message("/live/song/get/is_playing", None)
            self.ableton_client.send_message("/live/song/get/session_record", None)

    def _handle_cue_load(self, cue: str) -> None:
        from app_settings import settings
        self._update_current_transport_state()
        self.transport_state_validated.clear()
        if (
            settings.marker_mode is PlaybackState.RECORDING
            and self.is_recording is True
        ):
            self._place_marker_with_name(cue)
        elif (
            settings.marker_mode is PlaybackState.PLAYBACK_TRACK
            and self.is_playing is False
        ):
            self._goto_marker_by_name(cue)

    def _shutdown_servers(self) -> None:
        try:
            if self.ableton_osc_server:
                self.ableton_osc_server.shutdown()
                self.ableton_osc_server.server_close()
            logger.info("Ableton OSC Server shutdown completed")
        except Exception as e:
            logger.error(f"Error shutting down Ableton server: {e}")
