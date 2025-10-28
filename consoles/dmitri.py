import time
from typing import Any, Callable, Optional, Tuple, List, Iterator
from logger_config import logger

from pubsub import pub
import pythonosc
from pythonosc import udp_client
from pythonosc.osc_message import OscMessage, osc_types, ParseError

import struct

import constants
from constants import PyPubSubTopics

from . import Console, Feature

class CustomOscMessage(OscMessage):
    # Extends python-osc to handle custom type tag "A"

    def __init__(self, dgram: bytes) -> None:
        self._dgram = dgram
        self._parameters = []  # type: List[Any]
        self._parse_datagram()

    def __str__(self):
        return f"{self.address} {' '.join(str(p) for p in self.params)}"

    def _get_control_point_address(self, dgram: bytes, start_index: int) -> Tuple[int, int]:
        if len(dgram[start_index:]) < 16:
            raise ValueError(
                "Not enough data for Control Point Address Type (needs 16 bytes)"
            )
            # Unpack as 8 big-endian signed shorts
        return (
            struct.unpack(">8h", dgram[start_index : start_index + 16]),
            start_index + 16,
        ) # return (value, remaining_data)

    def _parse_datagram(self) -> None:
        # Custom datagram parsing to support the Control Point Address type tag
        try:
            self._address_regexp, index = osc_types.get_string(self._dgram, 0)
            if not self._dgram[index:]:
                # No params is legit, just return now.
                return

            # Get the parameters types.
            type_tag, index = osc_types.get_string(self._dgram, index)
            if type_tag.startswith(","):
                type_tag = type_tag[1:]

            params = []  # type: List[Any]
            param_stack = [params]
            # Parse each parameter given its type.
            for param in type_tag:
                val = NotImplemented  # type: Any
                if param == "i":  # Integer.
                    val, index = osc_types.get_int(self._dgram, index)
                elif param == "h":  # Int64.
                    val, index = osc_types.get_int64(self._dgram, index)
                elif param == "f":  # Float.
                    val, index = osc_types.get_float(self._dgram, index)
                elif param == "d":  # Double.
                    val, index = osc_types.get_double(self._dgram, index)
                elif param == "s":  # String.
                    val, index = osc_types.get_string(self._dgram, index)
                elif param == "b":  # Blob.
                    val, index = osc_types.get_blob(self._dgram, index)
                elif param == "r":  # RGBA.
                    val, index = osc_types.get_rgba(self._dgram, index)
                elif param == "m":  # MIDI.
                    val, index = osc_types.get_midi(self._dgram, index)
                elif param == "t":  # osc time tag:
                    val, index = osc_types.get_timetag(self._dgram, index)
                elif param == "T":  # True.
                    val = True
                elif param == "F":  # False.
                    val = False
                elif param == "N":  # Nil.
                    val = None
                elif param == "A":
                    val, index = self._get_control_point_address(self._dgram, index)
                elif param == "[":  # Array start.
                    array = []  # type: List[Any]
                    param_stack[-1].append(array)
                    param_stack.append(array)
                elif param == "]":  # Array stop.
                    if len(param_stack) < 2:
                        raise ParseError(
                            f"Unexpected closing bracket in type tag: {type_tag}"
                        )
                    param_stack.pop()
                # TODO: Support more exotic types as described in the specification.
                else:
                    logger.warning(f"Unhandled parameter type: {param}")
                    continue
                if param not in "[]":
                    param_stack[-1].append(val)
            if len(param_stack) != 1:
                raise ParseError(f"Missing closing bracket in type tag: {type_tag}")
            self._parameters = params
        except osc_types.ParseError as pe:
            raise ParseError("Found incorrect datagram, ignoring it", pe)

    @property
    def address(self) -> str:
        """Returns the OSC address regular expression."""
        return self._address_regexp

    @staticmethod
    def dgram_is_message(dgram: bytes) -> bool:
        """Returns whether this datagram starts as an OSC message."""
        return dgram.startswith(b"/")

    @property
    def size(self) -> int:
        """Returns the length of the datagram for this message."""
        return len(self._dgram)

    @property
    def dgram(self) -> bytes:
        """Returns the datagram from which this message was built."""
        return self._dgram

    @property
    def params(self) -> List[Any]:
        """Convenience method for list(self) to get the list of parameters."""
        return list(self)

    def __iter__(self) -> Iterator[Any]:
        """Returns an iterator over the parameters of this message."""
        return iter(self._parameters)


# Monkey patch our custom class:
pythonosc.osc_message.OscMessage = CustomOscMessage


class Dmitri(Console):
    fixed_send_port: int = 18033  # pyright: ignore[reportIncompatibleVariableOverride]
    type = "D'Mitri"
    supported_features = [Feature.CUE_LIST_PLAYER]
    _client: udp_client.DispatchClient
    _sent_subscribe = False

    def start_managed_threads(
        self, start_managed_thread: Callable[[str, Callable[..., Any]], None]
    ) -> None:
        start_managed_thread("console_connection_thread", self._console_client_thread)

    def _console_client_thread(self) -> None:
        from app_settings import settings

        self.selected_list = settings.cue_list_player

        self._client = udp_client.DispatchClient(
            settings.console_ip, self.fixed_send_port
        )

        self._client.dispatcher.map("/pong", self._subscribe_ok_received)
        self._client.dispatcher.map("/got", self._subscribed_data_received)
        self._client.dispatcher.set_default_handler(self._message_received)

        while not self._shutdown_server_event.is_set():
            try:
                self.heartbeat()
                while not self._shutdown_server_event.is_set():
                    self._client.handle_messages(constants.MESSAGE_TIMEOUT_SECONDS)
            except Exception:
                time.sleep(constants.CONNECTION_RECONNECTION_DELAY_SECONDS)
        self._sent_subscribe = False

    def _subscribe_ok_received(self, _address: str, _expires_seconds: int) -> None:
        if not self._sent_subscribe:
            self._cue_list_subscribe()
            self._sent_subscribe = True
        else:
            self._message_received()

    def _subscribed_data_received(self, _address, *args):
        if (
            args[1] == f"Automation {self.selected_list} Active Cue Name"
            and args[3] == f"Automation {self.selected_list} Active Cue ID"
        ):
            cue_name = str(args[2])
            cue_id = str(args[4])
            new_cue = cue_id + " " + cue_name
            pub.sendMessage(PyPubSubTopics.HANDLE_CUE_LOAD, cue=new_cue)
        self._message_received()

    def _message_received(self, *_) -> None:
        pub.sendMessage(PyPubSubTopics.CONSOLE_CONNECTED)

    def heartbeat(self) -> None:
        if hasattr(self, "_client"):
            # Send ping message to D'Mitri, it will respond with pong and MarkerMatic identifier
            self._client.send_message("/ping", "MarkerMatic")

    def _cue_list_subscribe(self) -> None:
        if hasattr(self, "_client"):
            self._client.send_message("/unsubscribeall", None)
            self._client.send_message(
                "/subscribe", f"Automation {self.selected_list} Active Cue ID"
            )
            self._client.send_message(
                "/subscribe", f"Automation {self.selected_list} Active Cue Name"
            )
