import threading
import time
from collections.abc import Callable

import mido
from pubsub import pub

import constants
from constants import PyPubSubTopics, TransportAction
from external_control.midi import MidiImplementation, MidiPortUnavailableError
from logger_config import logger


class MidoMidiImplementation(MidiImplementation):
    def external_midi_control(self, stop_event: threading.Event):
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
                        callback=MidoMidiImplementation._handle_midi_message,
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

    def refresh_midi_ports(
        self,
        callback: Callable[[list[str]], None] | None = None,
    ) -> None:
        threading.Thread(target=self._refresh_midi_ports, args=(callback,)).start()

    def _refresh_midi_ports(
        self,
        callback: Callable[[list[str]], None] | None = None,
    ) -> None:
        try:
            midi_ports = [constants.MIDI_PORT_NONE]
            midi_ports.extend(dict.fromkeys(mido.get_input_names()))  # pyright: ignore[reportAttributeAccessIssue]
            with self._midi_ports_lock:
                self._midi_ports = midi_ports
                if callable(callback):
                    callback(self._midi_ports)
        except Exception as e:
            logger.error(f"Error getting MIDI ports: {e}")

    def _handle_midi_message(self, message: mido.Message) -> None:
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
