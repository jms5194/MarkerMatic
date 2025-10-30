import threading
import time
from typing import Any, Callable

from pubsub import pub
from pythonosc import tcp_client, osc_message_builder

from zeroconf import Zeroconf, ServiceInfo

import constants
from constants import PlaybackState, PyPubSubTopics, TransportAction
from logger_config import logger

from . import Daw


class DigitalPerformer(Daw):
    type = "Digital Performer"

    def __init__(self):
        super().__init__()
        self._shutdown_server_event = threading.Event()
        self._connected = threading.Event()
        self._connection_check_lock = threading.Lock()
        self._connection_timeout_counter = 0
        self.digitalperformer_send_lock = threading.Lock()
        self.name_to_match = ""
        self.new_marker_name = ""
        self.is_playing = False
        self.is_recording = False
        self.transport_state_validated = threading.Event()
        self.digitalperformer_osc_server = None
        self.markers_to_ignore = ["Auto Record Start", "Memory Start", "Sequence Start", "Sequence End"]
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
        logger.info("Starting Digital Performer Connection threads")
        self._shutdown_server_event.clear()
        start_managed_thread("daw_connection_thread", self._build_digitalperformer_osc_servers)
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

    @staticmethod
    def _get_current_digital_performer_osc_port():
        zeroconf_type = "_osc._tcp.local."
        zeroconf_name = "Digital Performer OSC"

        with Zeroconf() as zc:
            info = None
            while not info:
                try:
                    full_name = zeroconf_name + "." + zeroconf_type
                    info = ServiceInfo(zeroconf_type, full_name)
                    success = info.request(zc, timeout=1.0)
                    if not success:
                        logger.info("No Digital Performer instance running.")
                        time.sleep(1)
                        info = None
                except Exception as e:
                    logger.error(f"Zeroconf error: {e}")
                    time.sleep(1)

            dp_port = info.port
            logger.info(f"Digital Performer's OSC server can be found at: {dp_port}")
            return dp_port

    def _build_digitalperformer_osc_servers(self):
        # Connect to Digital Performer via OSC
        logger.info("Starting Digital Performer OSC server")
        self.digitalperformer_client = tcp_client.TCPDispatchClient(
            constants.IP_LOOPBACK, self._get_current_digital_performer_osc_port(),mode='1.0',
        )
        self._receive_digitalperformer_OSC()
        while not self._shutdown_server_event.is_set():
            try:
                self._refresh_control_surfaces()
                while not self._shutdown_server_event.is_set():
                    self.digitalperformer_client.handle_messages(constants.MESSAGE_TIMEOUT_SECONDS)
            except Exception:
                time.sleep(constants.CONNECTION_RECONNECTION_DELAY_SECONDS)

    def _receive_digitalperformer_OSC(self):
        # Receives and distributes OSC from Digital Performer, based on matching OSC values
        self.digitalperformer_client.dispatcher.map("/MarkersSelList/SelList_Ready", self._marker_matcher)
        self.digitalperformer_client.dispatcher.map("/TransportState/Get", self._current_transport_state)
        self.digitalperformer_client.dispatcher.map("/Get_Time", self._place_marker_at_time)
        self.digitalperformer_client.dispatcher.set_default_handler(self._message_received)

    def _message_received(self, *_) -> None:
        if not self._connected.is_set():
            self._connected.set()
            pub.sendMessage(PyPubSubTopics.DAW_CONNECTION_STATUS, connected=True)
        with self._connection_check_lock:
            self._connection_timeout_counter = 0

    def _marker_matcher(self, osc_address, *args):
        from app_settings import settings
        sel_list_cookie = int(args[0])
        marker_qty = int(args[2])

        for i in range(3, marker_qty + 3):
            max_length = 36
            test_name = args[i]
            # Remove the timestamp at the end of the name that DP returns
            test_name = test_name[:-9]
            if not test_name.startswith(tuple(self.markers_to_ignore)):
                if settings.name_only_match:
                    try:
                        test_name = test_name.split(" ")
                        # Remove string slices from max_length to deal with removed number
                        max_length = max_length - len(test_name[0])
                        test_name = test_name[1:]
                        test_name = " ".join(test_name)
                    except Exception as e:
                        logger.error(f"Unable to format string for name only match:{e}")
                # DP will only build OSC markers that are 36 characters of text or shorter, so slice matching string
                if test_name == self.name_to_match[:max_length]:
                    self._goto_marker_by_id(sel_list_cookie, i-3)
                    break

        # Sel List must be deleted after use
        with self.digitalperformer_send_lock:
            self.digitalperformer_client.send_message("/SelList_Delete", sel_list_cookie)

    def _update_current_transport_state(self):
        with self.digitalperformer_send_lock:
            self.digitalperformer_client.send_message("/TransportState/Get", None)

    def _current_transport_state(self, osc_address, val):
        # Watches what the Digital Performer playhead is doing.
        playing = None
        recording = None
        if osc_address == "/TransportState/Get":
            if val == 0:
                playing = False
                recording = False
            elif val == 2:
                playing = True
                recording = False
            elif val == 4:
                recording = True
                playing = True
        if playing is True:
            self.is_playing = True
            logger.info("Digital Performer is playing")
        elif playing is False:
            self.is_playing = False
            logger.info("Digital Performer is not playing")
        if recording is True:
            self.is_recording = True
            logger.info("Digital Performer is recording")
        elif recording is False:
            self.is_recording = False
            logger.info("Digital Performer is not recording")
        self.transport_state_validated.set()

    def _refresh_control_surfaces(self) -> None:
        with self.digitalperformer_send_lock:
            # Use the API version response as a keep alive
            try:
                self.digitalperformer_client.send_message("/API_Version/Get", None)
            except BrokenPipeError:
                self._connected.clear()

    def _goto_marker_by_id(self, list_cookie, marker_id):
        with self.digitalperformer_send_lock:
            # Selecting a marker in a SelList moves the playhead to that location
            self.digitalperformer_client.send_message("/SelList_Set", [list_cookie, marker_id])

    def _place_marker_with_name(self, marker_name: str):
        with self.digitalperformer_send_lock:
            self.new_marker_name = marker_name
            # Get our current playhead time in samples
            self.digitalperformer_client.send_message("/Get_Time", 6)

    def _place_marker_at_time(self, osc_address, *args):
        if osc_address == "/Get_Time":
            try:
                cur_pos = args[0]
                with self.digitalperformer_send_lock:
                    msg = osc_message_builder.OscMessageBuilder(address="/MakeMarker")
                    # Arg1 value 6 indicates we want to work in samples
                    msg.add_arg(6)
                    # Arg2 is the position, it must be sent as a double, not float
                    msg.add_arg(cur_pos, arg_type='d')
                    msg.add_arg(self.new_marker_name)
                    osc_message = msg.build()
                    self.digitalperformer_client.send(osc_message)
            except Exception as e:
                logger.error(f"Unable to resolve current playhead time: {e}")
            logger.info(f"Placed marker for cue: {self.new_marker_name}")

    def get_marker_id_by_name(self, name: str):
        # Asks for current marker information based upon number of markers.
        from app_settings import settings
        self.transport_state_validated.wait()
        if (not self.is_playing) or settings.allow_loading_while_playing:
            self.name_to_match = name
            if settings.name_only_match:
                try:
                    self.name_to_match = self.name_to_match.split(" ")
                    self.name_to_match = self.name_to_match[1:]
                    self.name_to_match = " ".join(self.name_to_match)
                except Exception as e:
                    logger.error(f"Unable to format incoming cue string{e}")
            with self.digitalperformer_send_lock:
                # Request the list of all markers currently in project
                self.digitalperformer_client.send_message("/MarkersSelList/Get_NewSelList", None)

    def _incoming_transport_action(self, transport_action: TransportAction):
        try:
            if transport_action is TransportAction.PLAY:
                self._digitalperformer_play()
            elif transport_action is TransportAction.STOP:
                self._digitalperformer_stop()
            elif transport_action is TransportAction.RECORD:
                self._digitalperformer_rec()
        except Exception as e:
            logger.error(f"Error processing transport macros: {e}")

    def _digitalperformer_play(self):
        with self.digitalperformer_send_lock:
            self.digitalperformer_client.send_message("/TransportState", 2)

    def _digitalperformer_stop(self):
        with self.digitalperformer_send_lock:
            self.digitalperformer_client.send_message("/TransportState", 0)

    def _digitalperformer_rec(self):
        from app_settings import settings

        settings.marker_mode = PlaybackState.RECORDING
        pub.sendMessage(
            PyPubSubTopics.CHANGE_PLAYBACK_STATE, selected_mode=PlaybackState.RECORDING
        )
        with self.digitalperformer_send_lock:
            self.digitalperformer_client.send_message("/TransportState", 4)

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
        ):
            self.get_marker_id_by_name(cue)

    def _shutdown_servers(self):
        try:
            if self.digitalperformer_osc_server:
                self.digitalperformer_osc_server.shutdown()
                self.digitalperformer_osc_server.server_close()
            logger.info("Digital Performer OSC Server shutdown completed")
        except Exception as e:
            logger.error(f"Error shutting down Digital Performer server: {e}")
