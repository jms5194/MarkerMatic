# tests/test_app_settings.py
import configparser
import threading
import time

from app_settings import ThreadSafeSettings, validate_port_num, validate_cue_list_player


def test_validate_port_num_valid_values():
    assert validate_port_num(1) is True
    assert validate_port_num(65535) is True
    assert validate_port_num(49152) is True  # typical dynamic port


def test_validate_port_num_invalid_values():
    assert validate_port_num(0) is False
    assert validate_port_num(-1) is False
    assert validate_port_num(70000) is False


def test_validate_cue_list_player_valid_values():
    assert validate_cue_list_player(1) is True
    assert validate_cue_list_player(127) is True
    assert validate_cue_list_player(64) is True


def test_validate_cue_list_player_invalid_values():
    assert validate_cue_list_player(0) is False
    assert validate_cue_list_player(128) is False
    assert validate_cue_list_player(-5) is False


def test_thread_safe_settings_port_setters_accept_valid():
    s = ThreadSafeSettings()

    # Exercise all port setters with valid ports
    s.repeater_port = 1000
    s.repeater_receive_port = 1001
    s.reaper_port = 1002
    s.reaper_receive_port = 1003
    s.console_port = 1004
    s.receive_port = 1005
    s.external_control_osc_port = 1006

    assert s.repeater_port == 1000
    assert s.repeater_receive_port == 1001
    assert s.reaper_port == 1002
    assert s.reaper_receive_port == 1003
    assert s.console_port == 1004
    assert s.receive_port == 1005
    assert s.external_control_osc_port == 1006


def test_thread_safe_settings_port_setters_reject_invalid():
    s = ThreadSafeSettings()

    for attr_name in (
        "repeater_port",
        "repeater_receive_port",
        "reaper_port",
        "reaper_receive_port",
        "console_port",
        "receive_port",
        "external_control_osc_port",
    ):
        # Use setattr inside a closure to keep the test compact
        with_value = lambda v: setattr(s, attr_name, v)

        # Below range
        for value in (0, -1):
            try:
                with_value(value)
            except ValueError as e:
                assert "Invalid port number" in str(e)
            else:
                raise AssertionError(f"{attr_name} accepted invalid value {value}")

        # Above range
        for value in (70000, 99999):
            try:
                with_value(value)
            except ValueError as e:
                assert "Invalid port number" in str(e)
            else:
                raise AssertionError(f"{attr_name} accepted invalid value {value}")


def test_thread_safe_settings_cue_list_player_accepts_valid():
    s = ThreadSafeSettings()
    s.cue_list_player = 1
    assert s.cue_list_player == 1
    s.cue_list_player = 127
    assert s.cue_list_player == 127


def test_thread_safe_settings_cue_list_player_rejects_invalid():
    s = ThreadSafeSettings()

    for value in (0, 128, -3):
        try:
            s.cue_list_player = value
        except ValueError as e:
            assert "CueListPlayer" in str(e)
        else:
            raise AssertionError(f"cue_list_player accepted invalid value {value}")


def test_update_from_config_overrides_defaults():
    s = ThreadSafeSettings()

    config = configparser.ConfigParser()
    config["main"] = {
        "default_ip": "203.0.113.10",
        "repeater_ip": "203.0.113.20",
        "console_type": "CustomConsole",
        "daw_type": "CustomDAW",
        "external_control_midi_port": "My MIDI Port",

        "default_digico_send_port": "9001",
        "default_digico_receive_port": "9000",
        "default_reaper_send_port": "9002",
        "default_repeater_send_port": "9003",
        "default_repeater_receive_port": "9004",
        "default_reaper_receive_port": "9005",
        "external_control_osc_port": "9006",
        "cue_list_player": "10",

        "forwarder_enabled": "true",
        "name_only_match": "true",
        "always_on_top": "true",
        "mmc_control_enabled": "true",
        "allow_loading_while_playing": "true",

        "window_pos_x": "123",
        "window_pos_y": "456",
    }

    s.update_from_config(config)

    # String properties
    assert s.console_ip == "203.0.113.10"
    assert s.repeater_ip == "203.0.113.20"
    assert s.console_type == "CustomConsole"
    assert s.daw_type == "CustomDAW"
    assert s.external_control_midi_port == "My MIDI Port"

    # Int properties
    assert s.console_port == 9001
    assert s.receive_port == 9000
    assert s.reaper_port == 9002
    assert s.repeater_port == 9003
    assert s.repeater_receive_port == 9004
    assert s.reaper_receive_port == 9005
    assert s.external_control_osc_port == 9006
    assert s.cue_list_player == 10

    # Boolean properties
    assert s.forwarder_enabled is True
    assert s.name_only_match is True
    assert s.always_on_top is True
    assert s.mmc_control_enabled is True
    assert s.allow_loading_while_playing is True

    # Window location
    assert s.window_loc == (123, 456)


def test_update_from_config_uses_fallbacks_when_missing():
    s = ThreadSafeSettings()
    # capture some defaults
    default_console_ip = s.console_ip
    default_console_port = s.console_port
    default_forwarder_enabled = s.forwarder_enabled
    default_window_loc = s.window_loc

    # Empty config; everything should remain at defaults
    config = configparser.ConfigParser()
    s.update_from_config(config)

    assert s.console_ip == default_console_ip
    assert s.console_port == default_console_port
    assert s.forwarder_enabled == default_forwarder_enabled
    assert s.window_loc == default_window_loc


def test_log_settings_emits_lines(caplog):
    s = ThreadSafeSettings()

    with caplog.at_level("INFO"):
        s.log_settings()

    # Should have at least one line with "Current application settings:"
    assert any("Current application settings:" in rec.message for rec in caplog.records)

    # And some actual key/value lines
    assert any("console_ip" in rec.message for rec in caplog.records)

def test_thread_safe_settings_concurrent_access():
    """
    Exercise ThreadSafeSettings with concurrent readers/writers.

    This is not a formal proof of correctness, but:
    - it should not raise exceptions (especially ValueError from port validators
      when given valid values),
    - and it should not end up with obviously inconsistent types.
    """
    settings = ThreadSafeSettings()

    stop_event = threading.Event()
    exceptions: list[Exception] = []

    valid_ports = [1000, 2000, 3000, 4000, 5000]
    valid_cue_players = [1, 2, 10, 127]
    bool_values = [True, False]

    def writer_thread():
        try:
            while not stop_event.is_set():
                # Each assignment goes through validation + lock
                port = valid_ports[int(time.time() * 1000) % len(valid_ports)]
                settings.console_port = port
                settings.repeater_port = port
                settings.receive_port = port
                settings.reaper_port = port
                settings.reaper_receive_port = port
                settings.repeater_receive_port = port
                settings.external_control_osc_port = port

                cue = valid_cue_players[
                    int(time.time() * 1000) % len(valid_cue_players)
                ]
                settings.cue_list_player = cue

                settings.forwarder_enabled = bool_values[
                    int(time.time() * 1000) % 2
                ]
                settings.always_on_top = bool_values[int(time.time() * 1000) % 2]
                settings.mmc_control_enabled = bool_values[
                    int(time.time() * 1000) % 2
                ]
        except Exception as e:  # pragma: no cover - we want to see failures
            exceptions.append(e)
            stop_event.set()

    def reader_thread():
        try:
            while not stop_event.is_set():
                # Read a snapshot of several values under concurrent writes
                _ = settings.console_ip
                _ = settings.repeater_ip
                _ = settings.console_port
                _ = settings.receive_port
                _ = settings.repeater_port
                _ = settings.repeater_receive_port
                _ = settings.reaper_port
                _ = settings.reaper_receive_port
                _ = settings.external_control_osc_port
                _ = settings.cue_list_player
                _ = settings.forwarder_enabled
                _ = settings.always_on_top
                _ = settings.mmc_control_enabled
        except Exception as e:  # pragma: no cover
            exceptions.append(e)
            stop_event.set()

    threads: list[threading.Thread] = []
    for _ in range(5):
        t = threading.Thread(target=writer_thread)
        t.start()
        threads.append(t)
    for _ in range(5):
        t = threading.Thread(target=reader_thread)
        t.start()
        threads.append(t)

    # Let them run for a short period
    time.sleep(0.5)
    stop_event.set()

    for t in threads:
        t.join(timeout=1)

    # No exceptions should have been captured
    assert not exceptions, f"Exceptions in concurrent access: {exceptions}"

    # Final values should still be valid types/ranges
    assert settings.console_port in valid_ports
    assert settings.receive_port in valid_ports
    assert settings.repeater_port in valid_ports
    assert settings.repeater_receive_port in valid_ports
    assert settings.reaper_port in valid_ports
    assert settings.reaper_receive_port in valid_ports
    assert settings.external_control_osc_port in valid_ports
    assert settings.cue_list_player in valid_cue_players
    assert isinstance(settings.forwarder_enabled, bool)
    assert isinstance(settings.always_on_top, bool)
    assert isinstance(settings.mmc_control_enabled, bool)
