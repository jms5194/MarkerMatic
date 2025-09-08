import threading
import time
from typing import Any, Callable

import grpc
import ptsl
from ptsl import PTSL_pb2 as pt
from pubsub import pub

import constants
from constants import PlaybackState, PyPubSubTopics, TransportAction
from logger_config import logger

from . import Daw


class ProTools(Daw):
    type = "ProTools"
    _shutdown_server_event = threading.Event()

    def __init__(self):
        super().__init__()
        self.pt_engine_connection = None
        self.pt_send_lock = threading.Lock()
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
        logger.info("Starting Pro Tools Connection thread")
        start_managed_thread("daw_connection_thread", self._open_protools_connection)

    def _open_protools_connection(self) -> None:
        # Open a connection to Pro Tools using the PTSL scripting interface
        while not self._shutdown_server_event.is_set():
            try:
                self.pt_engine_connection = ptsl.engine.Engine(
                    company_name="JSSD", application_name=sys.argv[0]
                )
                if self.pt_engine_connection is not None:
                    logger.info("Connection established to Pro Tools")
                    pub.sendMessage(
                        PyPubSubTopics.DAW_CONNECTION_STATUS, connected=True
                    )
                    return
            except Exception:
                logger.error("Unable to connect to Pro Tools. Retrying in 1 second")
                time.sleep(1)

    def _place_marker_with_name(self, marker_name):
        with self.pt_send_lock:
            assert self.pt_engine_connection
            try:
                self.pt_engine_connection.create_memory_location(
                    memory_number=-1,
                    start_time="current_pos",
                    name=marker_name,
                    location="MLC_MainRuler",
                )
                # -1 seems to be a magic number for the next available memory_number.
                # Start_time as current_pos is a hacky way to get it to drop where the playhead is- but throws an error.
                # There must be a constant to put here that doesn't throw the error.
            except ptsl.errors.CommandError as e:
                if e.error_type == pt.PT_InvalidParameter:
                    logger.error("Bad parameter input to create_memory_location")
            except grpc._channel._InactiveRpcError:
                pub.sendMessage(PyPubSubTopics.DAW_CONNECTION_STATUS, connected=False)
                logger.error("Pro Tools connection lost, Retrying connection")
                self._open_protools_connection()

    def _incoming_transport_action(self, transport_action):
        # If transport actions are received from the console, send to Pro Tools
        try:
            if transport_action is TransportAction.PLAY:
                self._pro_tools_play()
            elif transport_action is TransportAction.STOP:
                self._pro_tools_stop()
            elif transport_action is TransportAction.RECORD:
                self._pro_tools_rec()
        except Exception as e:
            logger.error(f"Error processing transport macros: {e}")

    def _handle_cue_load(self, cue: str):
        # Receives cue information from console and actions based on software mode
        from app_settings import settings

        if (
            settings.marker_mode is PlaybackState.RECORDING
            and self._get_current_transport_state() == "TS_TransportRecording"
        ):
            self._place_marker_with_name(cue)
        elif (
            settings.marker_mode is PlaybackState.PLAYBACK_TRACK
            and self._get_current_transport_state() == "TS_TransportStopped"
        ):
            self._get_marker_id_by_name(cue)

    def _get_marker_id_by_name(self, name):
        # Match marker by name to the MemoryLocation object it represents
        from app_settings import settings

        name_to_match = name
        if self._get_current_transport_state() not in (
            "TS_TransportPlaying",
            "TS_TransportRecording",
        ):
            if settings.name_only_match:
                name_to_match = name_to_match.split(" ")
                name_to_match = name_to_match[1:]
                name_to_match = " ".join(name_to_match)
            with self.pt_send_lock:
                mem_locs = self.pt_engine_connection.get_memory_locations()
                for pt.MemoryLocation in mem_locs:
                    try:
                        test_name = pt.MemoryLocation.name
                        if settings.name_only_match:
                            test_name = test_name.split(" ")
                            test_name = test_name[1:]
                            test_name = " ".join(test_name)
                        if name_to_match == test_name:
                            self._goto_marker_by_loc(pt.MemoryLocation)
                    except Exception:
                        logger.error("No matching memory location found")
                    except grpc._channel._InactiveRpcError:
                        pub.sendMessage(
                            PyPubSubTopics.DAW_CONNECTION_STATUS, connected=False
                        )
                        logger.error("Pro Tools connection lost, Retrying connection")
                        self._open_protools_connection()

    def _goto_marker_by_loc(self, memory_loc):
        # Jump playhead to the given memory location
        match_loc_time = str(memory_loc.start_time)
        with self.pt_send_lock:
            try:
                self.pt_engine_connection.set_timeline_selection(in_time=match_loc_time)
            except grpc._channel._InactiveRpcError:
                pub.sendMessage(PyPubSubTopics.DAW_CONNECTION_STATUS, connected=False)
                logger.error("Pro Tools connection lost, Retrying connection")
                self._open_protools_connection()

    def _get_current_transport_state(self):
        with self.pt_send_lock:
            try:
                return self.pt_engine_connection.transport_state()
            except grpc._channel._InactiveRpcError:
                pub.sendMessage(PyPubSubTopics.DAW_CONNECTION_STATUS, connected=False)
                logger.error("Pro Tools connection lost, Retrying connection")
                self._open_protools_connection()

    def _pro_tools_play(self):
        # Since Pro Tools only has a toggle of play state, additional logic is here to validate the toggle to the
        # correct mode
        with self.pt_send_lock:
            assert self.pt_engine_connection
            try:
                current_transport_state = self.pt_engine_connection.transport_state()
                if current_transport_state not in (
                    "TS_TransportPlaying",
                    "TS_TransportRecording",
                ):
                    try:
                        self.pt_engine_connection.toggle_play_state()
                    except ptsl.errors.CommandError as e:
                        if e.error_type == pt.PT_NoOpenedSession:
                            logger.error(
                                "Play command failed, no session is currently open"
                            )
                            return False
            except grpc._channel._InactiveRpcError:
                pub.sendMessage(PyPubSubTopics.DAW_CONNECTION_STATUS, connected=False)
                logger.error("Pro Tools connection lost, Retrying connection")
                self._open_protools_connection()
            return None

    def _pro_tools_stop(self):
        # Since Pro Tools only has a toggle of play state, additional logic is here to validate the toggle to the
        # correct mode
        with self.pt_send_lock:
            assert self.pt_engine_connection
            try:
                current_transport_state = self.pt_engine_connection.transport_state()
                if current_transport_state not in (
                    "TS_TransportStopped",
                    "TS_TransportStopping",
                ):
                    try:
                        self.pt_engine_connection.toggle_play_state()
                    except ptsl.errors.CommandError as e:
                        if e.error_type == pt.PT_NoOpenedSession:
                            logger.error(
                                "Play command failed, no session is currently open"
                            )
                            return False
            except grpc._channel._InactiveRpcError:
                pub.sendMessage(PyPubSubTopics.DAW_CONNECTION_STATUS, connected=False)
                logger.error("Pro Tools connection lost, Retrying connection")
                self._open_protools_connection()
            return None

    def _pro_tools_rec(self):
        # Arm transport and validate proper play state
        with self.pt_send_lock:
            assert self.pt_engine_connection
            try:
                current_transport_state = self.pt_engine_connection.transport_state()
                current_armed_state = self.pt_engine_connection.transport_armed()
                if not current_armed_state:
                    self.pt_engine_connection.toggle_record_enable()
                    if current_transport_state != "TS_TransportRecording":
                        try:
                            self.pt_engine_connection.toggle_play_state()
                        except ptsl.errors.CommandError as e:
                            if e.error_type == pt.PT_NoOpenedSession:
                                logger.error(
                                    "Play command failed, no session is currently open"
                                )
                                return False
            except grpc._channel._InactiveRpcError:
                pub.sendMessage(PyPubSubTopics.DAW_CONNECTION_STATUS, connected=False)
                logger.error("Pro Tools connection lost, Retrying connection")
                self._open_protools_connection()
            return None

    def _shutdown_servers(self):
        try:
            if self.pt_engine_connection:
                self.pt_engine_connection.close()
                logger.info("Disconnected from Pro Tools")
        except Exception as e:
            logger.error(f"Error closing Pro Tools connection: {e}")
