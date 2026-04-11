import threading
from abc import ABC, abstractmethod
from collections.abc import Callable

import constants


class MidiImplementation(ABC):
    midi_supported = True

    def __init__(self) -> None:
        self._midi_ports: list[str] = [constants.MIDI_PORT_NONE]
        self._midi_ports_lock = threading.Lock()

    @abstractmethod
    def external_midi_control(self, stop_event: threading.Event) -> None:
        """The MIDI handler, which the application will run in its own
        thread"""
        pass

    @property
    def midi_ports(self) -> list[str]:
        """The cached list of available MIDI input ports, including None"""
        with self._midi_ports_lock:
            return self._midi_ports

    @abstractmethod
    def refresh_midi_ports(
        self,
        callback: Callable[[list[str]], None] | None = None,
    ) -> None:
        """Refreshes the cached list of MIDI input ports"""
        pass


class MidiPortUnavailableError(Exception):
    pass


def load_midi() -> MidiImplementation:
    try:
        import mido.backends.rtmidi  # noqa: F401

        from external_control.midi_mido import MidoMidiImplementation

        return MidoMidiImplementation()
    except ImportError:
        from external_control.midi_nomidi import NoMidiImplementation

        return NoMidiImplementation()
