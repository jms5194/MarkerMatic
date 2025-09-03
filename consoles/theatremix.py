from typing import Any, Callable
from . import Console, Feature


class TheatreMix(Console):
    fixed_send_port: int = 32000  # pyright: ignore[reportIncompatibleVariableOverride]
    type = "TheatreMix"
    supported_features = [Feature.CUE_NUMBER]

    def start_managed_threads(
        self, start_managed_thread: Callable[[str, Callable[..., Any]], None]
    ) -> None:
        start_managed_thread("console_connection_thread", self._console_client_thread)

    def _console_client_thread(self) -> None: ...
