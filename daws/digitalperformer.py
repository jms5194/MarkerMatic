import threading
import time
from typing import Any, Callable

from pubsub import pub
from pythonosc import dispatcher, osc_tcp_server, tcp_client

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

import constants
from constants import PlaybackState, PyPubSubTopics, TransportAction
from logger_config import logger

from . import Daw, configure_reaper

class ZeroConfListener(ServiceListener):
    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when an existing service is updated."""
        print(f"Service {name} updated")

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when a service is removed."""
        print(f"Service {name} removed")

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when a new service is discovered."""
        info = zc.get_service_info(type_, name)
        if info:  # Ensure service info is available
            print(f"Service {name} added, service info: {info}")
            # You can add logic here to check for specific service properties
            # For example, if you are looking for a service with a specific name or property
            # if "my_unique_service_identifier" in info.properties:
            #     print("Found my specific service!")

class DigitalPerformer(Daw):
    type = "Digital Performer"
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
        logger.info("Starting Digital Performer Connection threads")
        self._shutdown_server_event.clear()
        #start_managed_thread(
        #    "validate_reaper_prefs_thread", self._validate_reaper_prefs
        #)
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

    def _get_current_digital_performer_osc_port(self):
        zeroconf = Zeroconf(interfaces= ['127.0.0.1'])
        listener = ZeroConfListener()
        browser = ServiceBrowser(zeroconf,"_osc._tcp.local", listener)
        try:
            logger.info("Attempting to discover Digital Performer OSC port")
        finally:
            zeroconf.close()

    def _build_digitalperformer_osc_servers(self):
        # Connect to Digital Performer via OSC
        from app_settings import settings

        logger.info("Starting Digital Performer OSC server")
        self.reaper_client = tcp_client.SimpleTCPClient(
            constants.IP_LOOPBACK, self._get_current_digital_performer_osc_port()
        )
        self.digitalperformer_dispatcher = dispatcher.Dispatcher()
        self._receive_digitalperformer_OSC()
        try:
            self.digitalperformer_osc_server = osc_tcp_server.ThreadingOSCTCPServer(
                (constants.IP_LOOPBACK, settings.reaper_receive_port),
                self.digitalperformer_dispatcher,
            )
            logger.info("Digital Performer OSC server started")
            self.digitalperformer_osc_server.serve_forever()
        except Exception as e:
            logger.error(f"Digital Performer OSC server startup error: {e}")

    def _receive_digitalperformer_OSC(self):
        # Receives and distributes OSC from Digital Performer, based on matching OSC values
        self.digitalperformer_dispatcher.map("/marker/*/name", self._marker_matcher)
        self.digitalperformer_dispatcher.map("/play", self._current_transport_state)
        self.digitalperformer_dispatcher.map("/record", self._current_transport_state)
        self.digitalperformer_dispatcher.set_default_handler(self._message_received)

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
