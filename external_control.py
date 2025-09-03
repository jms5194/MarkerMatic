import threading
import time
from typing import Optional

import mido
import mido.backends.rtmidi
from pubsub import pub
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

import constants
from app_settings import settings
from constants import PlaybackState, PyPubSubTopics, TransportAction
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
    dispatcher.map("/markermatic/marker", _handle_marker)


def _handle_mode_change(_: str, mode: str) -> None:
    try:
        playback_state = PlaybackState(mode)
    except ValueError:
        logger.warning("%s is not a supported playback state", mode)
        return
    pub.sendMessage(PyPubSubTopics.CHANGE_PLAYBACK_STATE, selected_mode=playback_state)


def _handle_transport_change(_: str, mode: str) -> None:
    try:
        playback_state = TransportAction(mode)
    except ValueError:
        logger.warning("%s is not a supported transport state", mode)
        return
    pub.sendMessage(PyPubSubTopics.TRANSPORT_ACTION, transport_action=playback_state)


def _handle_marker(_: str, marker_name: Optional[str]) -> None:
    if marker_name is not None:
        pub.sendMessage(PyPubSubTopics.PLACE_MARKER_WITH_NAME, marker_name=marker_name)
    else:
        pub.sendMessage(
            PyPubSubTopics.PLACE_MARKER_WITH_NAME,
            marker_name="Marker from External Control",
        )


def external_midi_control(stop_event: threading.Event):
    from app_settings import settings

    if (
        settings.external_control_midi_port
        and settings.external_control_midi_port != constants.MIDI_PORT_NONE
    ):
        while not stop_event.is_set():
            # Checking if the port is closed doesn't seem to work if disconnected, so no point to check
            try:
                port_name = settings.external_control_midi_port
                # Check to make sure the MIDI port is actually available
                if port_name not in mido.get_input_names():  # pyright: ignore[reportAttributeAccessIssue]
                    raise MidiPortUnavailableError("MIDI port isn't available")
                port: mido.ports.BasePort = mido.open_input(  # pyright: ignore[reportAttributeAccessIssue]
                    port_name,
                    callback=_handle_midi_message,
                )
                if port.name == port_name:
                    logger.info(f"Opened MIDI port {port_name}")
                    pub.subscribe(port.close, PyPubSubTopics.SHUTDOWN_SERVERS)
                    # This thread needs to block so the port doesn't get shutdown
                    stop_event.wait()
                else:
                    print(port.name)
                    print(port_name)
                    logger.error("mido opened the wrong MIDI port")
                    port.close()
            except (OSError, MidiPortUnavailableError) as e:
                logger.error(
                    f"Could not open MIDI port {settings.external_control_midi_port}, {e}"
                )
            if not stop_event.is_set():
                time.sleep(constants.CONNECTION_RECONNECTION_DELAY_SECONDS)


class MidiPortUnavailableError(Exception):
    pass


def get_midi_ports() -> list[str]:
    # Returns a list of available MIDI input ports.
    try:
        return list(dict.fromkeys(mido.get_input_names()))  # pyright: ignore[reportAttributeAccessIssue]
    except Exception as e:
        logger.error(f"Error getting MIDI ports: {e}")
        return []


def _handle_midi_message(message: mido.Message) -> None:
    # First, test if the incoming midi is a MMC commmand
    logger.info(f"Received MIDI message: {message}")
    from app_settings import settings

    if settings.mmc_control_enabled:
        if message.type == "sysex":  # pyright: ignore[reportAttributeAccessIssue]
            if message.hex() == "F0 7F 06 02 F7":
                # If MMC Play is received, send a play command
                logger.info("Received MMC Play command")
                pub.sendMessage(
                    PyPubSubTopics.TRANSPORT_ACTION,
                    transport_action=TransportAction.PLAY,
                )
            elif message.hex() == "F0 7F 06 03 F7":
                logger.info("Received MMC Stop command")
                # If MMC Stop is received, send a stop command
                pub.sendMessage(
                    PyPubSubTopics.TRANSPORT_ACTION,
                    transport_action=TransportAction.STOP,
                )
            elif message.hex() == "F0 7F 06 06 F7":
                logger.info("Received MMC Record command")
                # If MMC Record is received, send a record command
                pub.sendMessage(
                    PyPubSubTopics.TRANSPORT_ACTION,
                    transport_action=TransportAction.RECORD,
                )
        else:
            pass
            """
            # Implement logic here to use captured midi messages. 

            cur_play_msg = mido.Message.from_bytes(settings.midi_play_message)
            cur_stop_msg = mido.Message.from_bytes(settings.midi_stop_message)
            cur_rec_msg = mido.Message.from_bytes(settings.midi_record_message)
            cur_marker_msg = mido.Message.from_bytes(settings.midi_marker_message)
            if message == cur_play_msg:
                pub.sendMessage("incoming_transport_action", transport_action=TransportAction.PLAY)
            elif message == cur_stop_msg:
                pub.sendMessage("incoming_transport_action", transport_action=TransportAction.STOP)
            elif message == cur_rec_msg:
                pub.sendMessage("incoming_transport_action", transport_action=TransportAction.RECORD)
            elif message == cur_marker_msg:
                pub.sendMessage("place_marker_with_name", marker_name="Marker from MIDI")
            """
