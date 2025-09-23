import threading
import time
from typing import Any, Callable

from pubsub import pub
from pythonosc import dispatcher, osc_tcp_server, tcp_client, osc_message_builder
from pythonosc.osc_message import OscMessage

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
import socket

import constants
from constants import PlaybackState, PyPubSubTopics, TransportAction
from logger_config import logger

from . import Daw

class ZeroConfListener(ServiceListener):
    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when an existing service is updated."""
        print(f"Service {name} updated")

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when a service is removed."""
        print(f"Service {name} removed")

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when a new service is discovered."""
        print("SERVICE")
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
        self.digitalperformer_send_lock = threading.Lock()
        self.name_to_match = ""
        self.new_marker_name = ""
        self.is_playing = False
        self.is_recording = False
        self.digitalperformer_osc_server = None
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

    def _get_current_digital_performer_osc_port(self):
        zeroconf_type = "_osc._tcp.local."
        zeroconf_name = "Digital Performer OSC"
        zeroconf = Zeroconf()
        dp_port = None
        while not dp_port:
            try:
                dp_port =  zeroconf.get_service_info(zeroconf_type, zeroconf_name + "." + zeroconf_type).port
            except AttributeError as e:
                logger.info("No Digital Performer instance running.")
            time.sleep(1)
        zeroconf.close()
        logger.info(f"Digital Performer's OSC server can be found at: {dp_port}")
        return dp_port

    def _build_digitalperformer_osc_servers(self):
        #Connect to Digital Performer via OSC
        from app_settings import settings
        logger.info("Starting Digital Performer OSC server")
        self.digitalperformer_client = tcp_client.TCPClient(
            constants.IP_LOOPBACK, self._get_current_digital_performer_osc_port(), mode= '1.0',
        )
        self.digitalperformer_dispatcher = dispatcher.Dispatcher()
        self._receive_digitalperformer_OSC()
        try:
            self.digitalperformer_osc_server = osc_tcp_server.ThreadingOSCTCPServer(
                (constants.IP_LOOPBACK, self._get_current_digital_performer_osc_port()),
                self.digitalperformer_dispatcher, mode= "1.0",
            )
            logger.info("Digital Performer OSC server started")
            self.digitalperformer_osc_server.serve_forever()
        except Exception as e:
            logger.error(f"Digital Performer OSC server startup error: {e}")

    def _receive_digitalperformer_OSC(self):
        # Receives and distributes OSC from Digital Performer, based on matching OSC values
        self.digitalperformer_dispatcher.map("/MarkersSelList/SelList_Ready", self._marker_matcher)
        self.digitalperformer_dispatcher.map("/TransportState", self._current_transport_state)
        self.digitalperformer_dispatcher.set_default_handler(self._message_received)

    def _message_received(self, *_) -> None:
        if not self._connected.is_set():
            self._connected.set()
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
        # Watches what the Digital Performer playhead is doing.
        playing = None
        recording = None
        if osc_address == "/TransportState":
            if val == 0:
                playing = False
                recording = False
            elif val == 1:
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

    def _refresh_control_surfaces(self) -> None:
        with self.digitalperformer_send_lock:
            msg = osc_message_builder.OscMessageBuilder(address="/API_Version/Get")
            msg.add_arg(None)
            osc_message = msg.build()
            self.digitalperformer_client.send(osc_message)

    def _goto_marker_by_id(self, marker_id):
        with self.digitalperformer_send_lock:
            self.reaper_client.send_message("/marker", int(marker_id))

    def _place_marker_with_name(self, marker_name: str):
        with self.digitalperformer_send_lock:
            self.new_marker_name = marker_name
            # Get our current playhead time in samples
            msg = osc_message_builder.OscMessageBuilder(address="/Get_Time")
            msg.add_arg(6)
            osc_message = msg.build()
            self.digitalperformer_client.send(osc_message)

    def _place_marker_at_time(self, osc_address, *args):
        if osc_address == "/Get_Time":
            cur_pos = args[0]
            print(cur_pos)
            with self.digitalperformer_send_lock:
                msg = osc_message_builder.OscMessageBuilder(address="/MakeMarker")
                msg.add_arg(6)
                msg.add_arg(cur_pos)
                msg.add_arg(self.new_marker_name)
                osc_message = msg.build()
                self.digitalperformer_client.send(osc_message)
            logger.info(f"Placed marker for cue: {self.new_marker_name}")

    def get_marker_id_by_name(self, name: str):
        # Asks for current marker information based upon number of markers.
        from app_settings import settings

        if self.is_playing is False:
            self.name_to_match = name
            if settings.name_only_match:
                self.name_to_match = self.name_to_match.split(" ")
                self.name_to_match = self.name_to_match[1:]
                self.name_to_match = " ".join(self.name_to_match)
            with self.digitalperformer_send_lock:
                msg = osc_message_builder.OscMessageBuilder(address="/MarkersSelList/Get_NewSelList")
                msg.add_arg(None)
                osc_message = msg.build()
                self.digitalperformer_client.send(osc_message)

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
            msg = osc_message_builder.OscMessageBuilder(address="/TransportState")
            msg.add_arg(2)
            osc_message = msg.build()
            self.digitalperformer_client.send(osc_message)

    def _digitalperformer_stop(self):
        with self.digitalperformer_send_lock:
            msg = osc_message_builder.OscMessageBuilder(address="/TransportState")
            msg.add_arg(0)
            osc_message = msg.build()
            self.digitalperformer_client.send(osc_message)

    def _digitalperformer_rec(self):
        from app_settings import settings

        settings.marker_mode = PlaybackState.RECORDING
        pub.sendMessage(
            PyPubSubTopics.CHANGE_PLAYBACK_STATE, selected_mode=PlaybackState.RECORDING
        )
        with self.digitalperformer_send_lock:
            msg = osc_message_builder.OscMessageBuilder(address="/TransportState")
            msg.add_arg(4)
            osc_message = msg.build()
            self.digitalperformer_client.send(osc_message)

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
            if self.digitalperformer_osc_server:
                self.digitalperformer_osc_server.shutdown()
                self.digitalperformer_osc_server.server_close()
            logger.info("Digital Performer OSC Server shutdown completed")
        except Exception as e:
            logger.error(f"Error shutting down Digital Performer server: {e}")
