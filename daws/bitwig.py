import threading
import time
from typing import Any, Callable

import wx
from pubsub import pub
from py4j.java_gateway import JavaGateway
from py4j.protocol import Py4JError, Py4JJavaError, Py4JNetworkError

import constants
from constants import PlaybackState, PyPubSubTopics, TransportAction
from logger_config import logger

from . import Daw, configure_bitwig, DawFeature


class Bitwig(Daw):
    type = "Bitwig Studio"
    supported_features = [DawFeature.NAME_ONLY_MATCH]

    def __init__(self):
        super().__init__()
        self._shutdown_or_restart_server_event = threading.Event()
        self.bitwig_send_lock = threading.Lock()
        self.gateway_entry_point = None
        self.marker_dict = {}
        self.gateway = None
        pub.subscribe(
            self._place_marker_with_name, PyPubSubTopics.PLACE_MARKER_WITH_NAME
        )
        pub.subscribe(self._incoming_transport_action, PyPubSubTopics.TRANSPORT_ACTION)
        pub.subscribe(self._handle_cue_load, PyPubSubTopics.HANDLE_CUE_LOAD)
        pub.subscribe(self._shutdown_servers, PyPubSubTopics.SHUTDOWN_SERVERS)
        pub.subscribe(
            self._shutdown_or_restart_server_event.set, PyPubSubTopics.SHUTDOWN_SERVERS
        )

    def start_managed_threads(
        self, start_managed_thread: Callable[[str, Any], None]
    ) -> None:
        self._shutdown_server_event.clear()
        start_managed_thread(
            "validate_bitwig_prefs_thread", self._validate_bitwig_prefs
        )
        logger.info("Starting Bitwig Connection thread")
        start_managed_thread("daw_connection_thread", self._open_bitwig_connection)

    @staticmethod
    def _validate_bitwig_prefs():
        # If the Bitwig Extensions directory does not contain our Markermatic Bridge, copy it over
        try:
            if not configure_bitwig.verify_markermatic_bridge_in_user_dir():
                pub.sendMessage(PyPubSubTopics.REQUEST_DAW_RESTART, daw_name="Bitwig")
            return True
        except Exception as e:
            logger.error(f"Unable to install Bitwig extension or error occurred: {e}")

    def _open_bitwig_connection(self) -> None:
        while not self._shutdown_server_event.is_set():
            try:
                self.gateway = JavaGateway()
                logger.info("Attempting to Connect to Bitwig")
                self.gateway_entry_point = self.gateway.entry_point
                host = self.gateway_entry_point.getHost()
                println = host.println
                logger.info("Connected to Bitwig")
                println("Connected to Bitwig")
                self._shutdown_or_restart_server_event.clear()
                wx.CallAfter(
                    pub.sendMessage,
                    PyPubSubTopics.DAW_CONNECTION_STATUS,
                    connected=True,
                )
                self.bitwig_transport = self.gateway_entry_point.getTransport()
                self.bitwig_arranger = self.gateway_entry_point.getArranger()
                self.bitwig_cuemarkerbank = self.gateway_entry_point.getCueMarkerBank()
                self._build_marker_dict()
                self._shutdown_or_restart_server_event.wait()
            except Exception:
                logger.error("Unable to connect to Bitwig. Retrying")
                time.sleep(constants.CONNECTION_RECONNECTION_DELAY_SECONDS)

    def _incoming_transport_action(self, transport_action: TransportAction) -> None:
        try:
            if transport_action is TransportAction.PLAY:
                self._bitwig_play()
            elif transport_action is TransportAction.STOP:
                self._bitwig_stop()
            elif transport_action is TransportAction.RECORD:
                self._bitwig_rec()
        except Exception as e:
            logger.error(f"Error processing transport macros: {e}")

    def _build_marker_dict(self) -> None:
        try:
            cur_marker_qty = self.bitwig_cuemarkerbank.itemCount().get()
            self.marker_dict = {}
            for i in range(0, cur_marker_qty):
                cur_marker_info = self.gateway_entry_point.getCueMarkerInfo(i)
                cur_marker_split = cur_marker_info.split("<>")
                self.marker_dict[i] = cur_marker_split
        except (
            AttributeError,
            Py4JError,
            Py4JNetworkError,
            Py4JJavaError,
            ConnectionRefusedError,
            IndexError,
        ):
            logger.error("Lost Connection to Bitwig. Attempting reconnect")
            self._bitwig_reconnect_attempt()

    def _add_to_marker_dict(self, new_marker_num: int) -> None:
        try:
            cur_marker_info = self.gateway_entry_point.getCueMarkerInfo(new_marker_num)
            cur_marker_split = cur_marker_info.split("<>")
            self.marker_dict[new_marker_num] = cur_marker_split
        except (
            Py4JError,
            Py4JNetworkError,
            Py4JJavaError,
            ConnectionRefusedError,
            IndexError,
        ):
            logger.error("Lost Connection to Bitwig. Attempting reconnect")
            self._bitwig_reconnect_attempt()

    def _place_marker_with_name(self, marker_name: str) -> None:
        # Bitwig markers can only be placed on a bar/beat reference, so will never be 100% accurate
        try:
            cur_marker_qty = self.bitwig_cuemarkerbank.itemCount().get()
            self.bitwig_transport.addCueMarkerAtPlaybackPosition()
            time.sleep(0.1)
            self.gateway_entry_point.renameMarker(cur_marker_qty, marker_name)
            time.sleep(0.1)
            self._add_to_marker_dict(cur_marker_qty)
        except (
            AttributeError,
            Py4JError,
            Py4JNetworkError,
            Py4JJavaError,
            ConnectionRefusedError,
            IndexError,
        ):
            logger.error("Lost Connection to Bitwig. Attempting reconnect")
            self._bitwig_reconnect_attempt()

    def _bitwig_reconnect_attempt(self) -> None:
        wx.CallAfter(
            pub.sendMessage,
            PyPubSubTopics.DAW_CONNECTION_STATUS,
            connected=False,
        )
        self._shutdown_servers()
        self._shutdown_or_restart_server_event.set()

    def _handle_cue_load(self, cue: str) -> None:
        from app_settings import settings

        try:
            is_playing: bool = self.bitwig_transport.isPlaying().get()
            if (
                settings.marker_mode is PlaybackState.RECORDING
                and is_playing
                and self.bitwig_transport.isArrangerRecordEnabled().get()
            ):
                self._place_marker_with_name(cue)
            elif settings.marker_mode is PlaybackState.PLAYBACK_TRACK and (
                not is_playing or settings.allow_loading_while_playing
            ):
                self._goto_marker_by_name(cue)
                if is_playing:
                    self.bitwig_transport.jumpToPlayStartPosition()
        except (
            AttributeError,
            Py4JError,
            Py4JNetworkError,
            Py4JJavaError,
            ConnectionRefusedError,
            IndexError,
        ):
            logger.error("Lost Connection to Bitwig. Attempting reconnect")
            self._bitwig_reconnect_attempt()

    def _goto_marker_by_name(self, cue: str) -> None:
        from app_settings import settings

        possible_markers = []
        try:
            if settings.name_only_match:
                cue_name_only_list = cue.split(" ")[1:]
                cue_name_only = " ".join(cue_name_only_list)
                try:
                    for key, value in self.marker_dict.items():
                        value_full_name = value[0]
                        value_name_only_list = value_full_name.split(" ")[1:]
                        value_name_only = " ".join(value_name_only_list)
                        if value_name_only == cue_name_only:
                            possible_markers.append(key)
                except Exception:
                    logger.info("Bitwig found no matching marker")
                    return
                if possible_markers[0]:
                    marker_to_nav = self.marker_dict[possible_markers[0]]
                    marker_time_to_nav = marker_to_nav[1]
                    self.gateway_entry_point.loadPlaybackPosition(marker_time_to_nav)
                pass
            else:
                try:
                    possible_markers = [
                        key
                        for key, value in self.marker_dict.items()
                        if value[0] == cue
                    ]
                except Exception:
                    logger.info("Bitwig found no matching marker")
                    return
                if possible_markers[0]:
                    marker_to_nav = self.marker_dict[possible_markers[0]]
                    marker_time_to_nav = marker_to_nav[1]
                    self.gateway_entry_point.loadPlaybackPosition(marker_time_to_nav)
        except (
            AttributeError,
            Py4JError,
            Py4JNetworkError,
            Py4JJavaError,
            ConnectionRefusedError,
            IndexError,
        ):
            logger.error("Lost Connection to Bitwig. Attempting reconnect")
            self._bitwig_reconnect_attempt()

    def _bitwig_play(self) -> None:
        try:
            if not self.bitwig_transport.isPlaying().get():
                self.bitwig_transport.play()
        except (
            AttributeError,
            Py4JError,
            Py4JNetworkError,
            Py4JJavaError,
            ConnectionRefusedError,
            IndexError,
        ):
            logger.error("Lost Connection to Bitwig. Attempting reconnect")
            self._bitwig_reconnect_attempt()

    def _bitwig_stop(self) -> None:
        try:
            self.bitwig_transport.stop()
        except (
            AttributeError,
            Py4JError,
            Py4JNetworkError,
            Py4JJavaError,
            ConnectionRefusedError,
            IndexError,
        ):
            logger.error("Lost Connection to Bitwig. Attempting reconnect")
            self._bitwig_reconnect_attempt()

    def _bitwig_rec(self) -> None:
        try:
            if not self.bitwig_transport.isPlaying().get():
                self.bitwig_transport.record()
                self.bitwig_transport.play()
            else:
                self.bitwig_transport.stop()
                self.bitwig_transport.record()
                self.bitwig_transport.play()
        except (
            AttributeError,
            Py4JError,
            Py4JNetworkError,
            Py4JJavaError,
            ConnectionRefusedError,
            IndexError,
        ):
            logger.error("Lost Connection to Bitwig. Attempting reconnect")
            self._bitwig_reconnect_attempt()

    def _shutdown_servers(self) -> None:
        logger.info("Closing connection to Bitwig")
        self.gateway.close()
