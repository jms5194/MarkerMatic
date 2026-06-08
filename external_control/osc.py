import threading
import time
from typing import Optional

from pubsub import pub
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

import constants
from app_settings import settings
from constants import (
    ArmedAction,
    PlaybackState,
    PyPubSubTopics,
    TransportAction,
)
from logger_config import logger


def external_osc_control(stop_event: threading.Event):
    logger.info("Starting external OSC control")
    if settings.external_control_osc_port is None:
        logger.error(
            "external_control_osc_port is not set. Cannot start external control OSC server."
        )
        return
    else:
        dispatcher = Dispatcher()
        map_osc_external_control_dispatcher(dispatcher)
        while not stop_event.is_set():
            try:
                server = ThreadingOSCUDPServer(
                    ("0.0.0.0", settings.external_control_osc_port), dispatcher
                )
                pub.subscribe(server.shutdown, PyPubSubTopics.SHUTDOWN_SERVERS)
                server.serve_forever()
            except OSError:
                logger.error("Could not bind external control OSC server")
                time.sleep(constants.CONNECTION_RECONNECTION_DELAY_SECONDS)
                continue


def map_osc_external_control_dispatcher(dispatcher: Dispatcher) -> None:
    # TODO: Add support for querying current mode and transport state
    for mode in PlaybackState:
        dispatcher.map(f"/markermatic/mode/{mode}", _handle_mode_change, mode)
    for action in TransportAction:
        dispatcher.map(
            f"/markermatic/transport/{action}", _handle_transport_change, action
        )
    for action in ArmedAction:
        dispatcher.map(f"/markermatic/armed/{action}", _handle_armed, action)
    dispatcher.map("/markermatic/marker", _handle_marker)


def _handle_mode_change(_address: str, mode: list[PlaybackState], *_) -> None:
    pub.sendMessage(PyPubSubTopics.CHANGE_PLAYBACK_STATE, selected_mode=mode[0])


def _handle_transport_change(_address: str, action: list[TransportAction], *_) -> None:
    pub.sendMessage(PyPubSubTopics.TRANSPORT_ACTION, transport_action=action[0])


def _handle_armed(_address: str, armed: list[ArmedAction], *_) -> None:
    pub.sendMessage(PyPubSubTopics.ARMED_ACTION, armed_action=armed[0])


def _handle_marker(_address: str, marker_name: Optional[str] = None) -> None:
    if marker_name:
        pub.sendMessage(PyPubSubTopics.PLACE_MARKER_WITH_NAME, marker_name=marker_name)
    else:
        pub.sendMessage(
            PyPubSubTopics.PLACE_MARKER_WITH_NAME,
            marker_name="Marker from External Control",
        )
