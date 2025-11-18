# tests/test_main_attempt_reconnect.py
import types

import main


class DummyEvent:
    """Simple stand‑in for a wx event."""
    pass


def test_attempt_reconnect_calls_bridge():
    # Arrange: patch MainWindow.BridgeFunctions with a dummy that records calls
    calls = {"attempted": False}

    class DummyBridge:
        def attempt_reconnect(self):
            calls["attempted"] = True

    original_bridge = main.MainWindow.BridgeFunctions
    main.MainWindow.BridgeFunctions = DummyBridge()

    try:
        # Act
        main.attempt_reconnect(DummyEvent())

        # Assert
        assert calls["attempted"] is True
    finally:
        # Always restore the original object to avoid affecting other tests
        main.MainWindow.BridgeFunctions = original_bridge