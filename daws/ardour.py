import threading
import time
from typing import Any, Callable

import psutil
import wx
from pubsub import pub
from pythonosc import dispatcher, osc_server, udp_client

from constants import PlaybackState, PyPubSubTopics, TransportAction
from logger_config import logger

from . import Daw, configure_ardour


class Ardour(Daw):
    type = "Ardour"
    _shutdown_server_event = threading.Event()
    _ardour_responded_event = threading.Event()
    _ardour_heartbeat_event = threading.Event()

    def __init__(self):
        super().__init__()
        self.ardour_send_lock = threading.Lock()
        self.name_to_match = ""
        self.is_playing = False
        self.is_recording = False
        self.ardour_osc_server = None
        self._ardour_responded_event.clear()
        self.current_heartbeat_timestamp = 0
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
        self._shutdown_server_event.clear()
        logger.info("Starting Ardour Connection thread")
        self._validate_ardour_prefs()
        start_managed_thread("daw_connection_thread", self._build_ardour_osc_servers)
        start_managed_thread("daw_heartbeat_thread", self._send_ardour_osc_config)

    def _validate_ardour_prefs(self):
        # Check if OSC is turned on in Ardour's config file.
        # If not, enable it and restart Ardour.
        try:
            if not configure_ardour.osc_interface_exists(
                configure_ardour.get_resource_path(True)
            ):
                try:
                    configure_ardour.get_ardour_process_path()
                    pub.sendMessage(
                        PyPubSubTopics.REQUEST_DAW_RESTART, daw_name="Ardour"
                    )
                    enable_osc_thread = threading.Thread(
                        target=configure_ardour.enable_osc_interface,
                        args=(configure_ardour.get_resource_path(True),),
                    )
                    enable_osc_thread.start()
                except RuntimeError:
                    enable_osc_thread = threading.Thread(
                        target=configure_ardour.enable_osc_interface,
                        args=(configure_ardour.get_resource_path(True),),
                    )
                    enable_osc_thread.start()
        except Exception as e:
            logger.error(f"Error validating Ardour preferences: {e}")

    def _receive_ardour_OSC(self):
        # Receives and distributes OSC from Ardour, based on matching OSC values
        self.ardour_dispatcher.map("/transport_play", self._current_transport_state)
        self.ardour_dispatcher.map("/transport_stop", self._current_transport_state)
        self.ardour_dispatcher.map("/rec_enable_toggle", self._current_transport_state)
        self.ardour_dispatcher.map("/heartbeat", self._ardour_connected_status)
        self.ardour_dispatcher.map("/set_surface", self._ardour_responded_flag_set)

    def _build_ardour_osc_servers(self):
        # Connect to Ardour via OSC
        while not self._shutdown_server_event.is_set():
            logger.info("Starting Ardour OSC server")
            self.ardour_client = udp_client.SimpleUDPClient("127.0.0.1", 3819)
            self.ardour_dispatcher = dispatcher.Dispatcher()
            self._receive_ardour_OSC()
            try:
                self.ardour_osc_server = osc_server.ThreadingOSCUDPServer(
                    ("127.0.0.1", 3820), self.ardour_dispatcher
                )
                logger.info("Ardour OSC server started")
                self.ardour_osc_server.serve_forever()
            except Exception as e:
                logger.error(f"Ardour OSC server startup error: {e}")
            time.sleep(0.1)

    def _send_ardour_osc_config(self):
        while not self._shutdown_server_event.is_set():
            if not self._ardour_responded_event.is_set():
                try:
                    with self.ardour_send_lock:
                        # Send a message to Ardour describing what information we want to receive
                        self.ardour_client.send_message(
                            "/set_surface/0/159/24/0/0/0", 3820
                        )
                        # Check that Ardour has received our configuration request
                        self.ardour_client.send_message("/set_surface", None)
                    logger.info("Sent Ardour OSC configuration request")
                except Exception:
                    logger.error("Ardour not yet available, retrying in 1 second")
            time.sleep(1)

    def _ardour_connected_status(self, osc_address, val):
        # Watches if Ardour is connected to the OSC server.
        if osc_address == "/heartbeat":
            if val == 1:
                self.current_heartbeat_timestamp = time.time()

    def _ardour_responded_flag_set(self, osc_address, *args):
        # Watches if Ardour has responded to the OSC server.
        self._ardour_responded_event.set()
        self._ardour_heartbeat_check()
        logger.info("Ardour has responded to OSC server")

    def _ardour_heartbeat_check(self):
        # Checks if Ardour is still connected and updates the UI
        # Initial delay to allow Ardour to respond
        time.sleep(2)
        while not self._shutdown_server_event.is_set():
            if self._ardour_responded_event.is_set():
                if time.time() - self.current_heartbeat_timestamp > 2.2:
                    # If Ardour has not sent a heartbeat in the last 5 seconds, it is disconnected.
                    wx.CallAfter(
                        pub.sendMessage,
                        PyPubSubTopics.DAW_CONNECTION_STATUS,
                        connected=False,
                    )
                    logger.error("MarkerMatic has lost connection to Ardour. Retrying.")
                    try:
                        if self.ardour_osc_server:
                            self.ardour_osc_server.shutdown()
                            self.ardour_osc_server.server_close()
                    except Exception as e:
                        logger.error(f"Error while shutting down Ardour server: {e}")
                    self._ardour_responded_event.clear()
                    break
                else:
                    # If Ardour is still connected, set the connection status to True.
                    wx.CallAfter(
                        pub.sendMessage,
                        PyPubSubTopics.DAW_CONNECTION_STATUS,
                        connected=True,
                    )
            time.sleep(1)

    def _current_transport_state(self, osc_address, val):
        # Watches what the Ardour playhead is doing.
        playing = None
        recording = None
        if osc_address == "/transport_play":
            if val == 0:
                playing = False
            elif val == 1:
                playing = True
        elif osc_address == "/rec_enable_toggle":
            if val == 0:
                recording = False
            elif val == 1:
                recording = True
        if playing is True:
            self.is_playing = True
            logger.info("Ardour is playing")
        elif playing is False:
            self.is_playing = False
            logger.info("Ardour is not playing")
        if recording is True:
            self.is_recording = True
            logger.info("Ardour is recording")
        elif recording is False:
            self.is_recording = False
            logger.info("Ardour is not recording")

    def _goto_marker_by_name(self, marker_name):
        from app_settings import settings

        if settings.name_only_match:
            self._get_open_files_for_ardour()
        else:
            with self.ardour_send_lock:
                self.ardour_client.send_message("/marker", marker_name)

    def get_marker_id_by_name(self, name):
        pass

    def _get_open_files_for_ardour(self):
        # TODO: find a way to match that
        process_name = "Ardour8"
        open_files = []
        for proc in psutil.process_iter(["pid", "name", "open_files"]):
            try:
                if proc.info["name"] == process_name:
                    for f in proc.info["open_files"]:
                        open_files.append(f.path)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        logger.debug(f"Ardour process open files: {open_files}")

    def _place_marker_with_name(self, marker_name):
        with self.ardour_send_lock:
            self.ardour_client.send_message("/add_marker", marker_name)

    def _incoming_transport_action(self, transport_action):
        try:
            if transport_action is TransportAction.PLAY:
                self._ardour_play()
            elif transport_action is TransportAction.STOP:
                self._ardour_stop()
            elif transport_action is TransportAction.RECORD:
                self._ardour_rec()
        except Exception as e:
            logger.error(f"Error processing transport macros: {e}")

    def _ardour_play(self):
        with self.ardour_send_lock:
            self.ardour_client.send_message("/transport_play", 1.0)

    def _ardour_stop(self):
        with self.ardour_send_lock:
            self.ardour_client.send_message("/transport_stop", 1.0)

    def _ardour_rec(self):
        # Sends action to skip to end of project and then record, to prevent overwrites
        from app_settings import settings

        settings.marker_mode = PlaybackState.RECORDING
        wx.CallAfter(
            pub.sendMessage,
            PyPubSubTopics.CHANGE_PLAYBACK_STATE,
            selected_mode=PlaybackState.RECORDING,
        )
        with self.ardour_send_lock:
            self.ardour_client.send_message("/goto_end", None)
            self.ardour_client.send_message("/rec_enable_toggle", 1.0)
            self.ardour_client.send_message("/transport_play", 1.0)

    def _handle_cue_load(self, cue: str) -> None:
        from app_settings import settings

        if (
            settings.marker_mode is PlaybackState.RECORDING
            and self.is_recording is True
            and self.is_playing is True
        ):
            self._place_marker_with_name(cue)
        elif (
            settings.marker_mode is PlaybackState.PLAYBACK_TRACK
            and self.is_playing is False
        ):
            self._goto_marker_by_name(cue)
            # TODO: Add name only logic here

    def _shutdown_servers(self):
        try:
            if self.ardour_osc_server:
                self.ardour_osc_server.shutdown()
                self.ardour_osc_server.server_close()
            logger.info("Ardour OSC Server shutdown completed")
        except Exception as e:
            logger.error(f"Error shutting down Ardour server: {e}")
