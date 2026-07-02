import threading
from collections.abc import Callable

from external_control.midi import MidiImplementation


class NoMidiImplementation(MidiImplementation):
    midi_supported = False

    def external_midi_control(self, stop_event: threading.Event) -> None:
        pass

    def refresh_midi_ports(
        self, callback: Callable[[list[str]], None] | None = None
    ) -> None:
        pass
