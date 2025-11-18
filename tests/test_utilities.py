# tests/test_utilities.py
import configparser
import os
import threading

import constants
from constants import PyPubSubTopics
import utilities
from app_settings import settings


def test_get_ip_listen_any_loopback_ipv4():
    # Loopback IPv4 should be returned as‑is
    assert utilities.get_ip_listen_any("127.0.0.1") == "127.0.0.1"


def test_get_ip_listen_any_loopback_ipv6():
    # Loopback IPv6 should also be returned as‑is
    assert utilities.get_ip_listen_any("::1") == "::1"


def test_get_ip_listen_any_non_loopback_returns_listen_any():
    # Non‑loopback addresses should map to the "listen any" constant
    result = utilities.get_ip_listen_any("192.0.2.123")  # TEST-NET-1, non‑loopback
    assert result == constants.IP_LISTEN_ANY


def test_get_resources_directory_path_uses_RESOURCEPATH_env(monkeypatch):
    fake_path = "/tmp/py2app_resources"
    monkeypatch.setenv("RESOURCEPATH", fake_path)

    path = utilities.get_resources_directory_path()

    assert path == fake_path


def test_get_resources_directory_path_defaults_to_package_resources(monkeypatch):
    # Ensure RESOURCEPATH is not set
    monkeypatch.delenv("RESOURCEPATH", raising=False)

    path = utilities.get_resources_directory_path()

    # Should end with the "resources" directory next to the utilities module
    assert path.endswith(os.path.join("resources"))
    assert os.path.isdir(path), f"Expected directory to exist: {path}"


def test_daw_console_bridge_check_configuration_prefers_new_ini(tmp_path, monkeypatch):
    """If the v4 config exists, it should be used; legacy is ignored."""
    # Make all config dirs point into our temp directory
    def fake_user_config_dir(app_name, author):
        return str(tmp_path / app_name)

    monkeypatch.setattr("utilities.appdirs.user_config_dir", fake_user_config_dir)

    # Create both legacy and current ini files
    ini_dir = tmp_path / constants.APPLICATION_NAME
    legacy_dir = tmp_path / constants.APPLICATION_NAME_LEGACY
    ini_dir.mkdir(parents=True, exist_ok=True)
    legacy_dir.mkdir(parents=True, exist_ok=True)

    new_ini = ini_dir / constants.CONFIG_FILENAME
    legacy_ini = legacy_dir / constants.CONFIG_FILENAME_LEGACY

    new_ini.write_text("[main]\nforwarder_enabled = true\n")
    legacy_ini.write_text("[main]\nforwarder_enabled = false\n")

    called_with_paths = []

    def fake_update_from_config_file(path: str):
        called_with_paths.append(path)

    monkeypatch.setattr(settings, "update_from_config_file", fake_update_from_config_file)

    # Act: constructing DawConsoleBridge will call check_configuration()
    bridge = utilities.DawConsoleBridge()

    # Assert: only the new ini should be loaded
    assert called_with_paths == [str(new_ini)]

    # Sanity: paths on the instance point to our temp directory
    assert str(new_ini) == bridge._ini_path
    assert str(legacy_ini) == bridge._legacy_ini_path


def test_daw_console_bridge_check_configuration_falls_back_to_legacy(tmp_path, monkeypatch):
    """If only the legacy config exists, it should be used."""
    def fake_user_config_dir(app_name, author):
        return str(tmp_path / app_name)

    monkeypatch.setattr("utilities.appdirs.user_config_dir", fake_user_config_dir)

    ini_dir = tmp_path / constants.APPLICATION_NAME
    legacy_dir = tmp_path / constants.APPLICATION_NAME_LEGACY
    ini_dir.mkdir(parents=True, exist_ok=True)
    legacy_dir.mkdir(parents=True, exist_ok=True)

    # Only legacy exists
    legacy_ini = legacy_dir / constants.CONFIG_FILENAME_LEGACY
    legacy_ini.write_text("[main]\nforwarder_enabled = true\n")

    called_with_paths = []

    def fake_update_from_config_file(path: str):
        called_with_paths.append(path)

    monkeypatch.setattr(settings, "update_from_config_file", fake_update_from_config_file)

    utilities.DawConsoleBridge()

    assert called_with_paths == [str(legacy_ini)]


def test_update_configuration_file_writes_ini_and_updates_settings(tmp_path, monkeypatch):
    """update_configuration_file should write all fields and call settings.update_from_config_file."""
    def fake_user_config_dir(app_name, author):
        return str(tmp_path / app_name)

    monkeypatch.setattr("utilities.appdirs.user_config_dir", fake_user_config_dir)

    ini_dir = tmp_path / constants.APPLICATION_NAME
    ini_dir.mkdir(parents=True, exist_ok=True)

    called_with_paths = []

    def fake_update_from_config_file(path: str):
        called_with_paths.append(path)

    monkeypatch.setattr(settings, "update_from_config_file", fake_update_from_config_file)

    bridge = utilities.DawConsoleBridge()

    bridge.update_configuration_file(
        con_ip="192.0.2.10",
        rptr_ip="192.0.2.20",
        con_send=1111,
        con_rcv=1110,
        fwd_enable=True,
        rpr_send=2222,
        rpr_rcv=2221,
        rptr_snd=3333,
        rptr_rcv=3332,
        name_only=False,
        console_type="DiGiCo",
        daw_type="Reaper",
        always_on_top=True,
        external_control_osc_port=4444,
        external_control_midi_port="MyMidiPort",
        mmc_control_enabled=True,
        allow_loading_while_playing=True,
        cue_list_player=7,
    )

    # settings.update_from_config_file should be called with the new ini path
    assert called_with_paths == [bridge._ini_path]

    # The ini file should contain our values
    parser = configparser.ConfigParser()
    parser.read(bridge._ini_path)
    main = parser["main"]

    assert main.get("default_ip") == "192.0.2.10"
    assert main.get("repeater_ip") == "192.0.2.20"
    assert main.getint("default_digico_send_port") == 1111
    assert main.getint("default_digico_receive_port") == 1110
    assert main.getint("default_reaper_send_port") == 2222
    assert main.getint("default_reaper_receive_port") == 2221
    assert main.getint("default_repeater_send_port") == 3333
    assert main.getint("default_repeater_receive_port") == 3332
    assert main.getboolean("forwarder_enabled") is True
    assert main.getboolean("name_only_match") is False
    assert main.get("console_type") == "DiGiCo"
    assert main.get("daw_type") == "Reaper"
    assert main.getboolean("always_on_top") is True
    assert main.getint("external_control_osc_port") == 4444
    assert main.get("external_control_midi_port") == "MyMidiPort"
    assert main.getboolean("mmc_control_enabled") is True
    assert main.getboolean("allow_loading_while_playing") is True
    assert main.getint("cue_list_player") == 7


def test_update_pos_in_config_writes_window_position(tmp_path, monkeypatch):
    """update_pos_in_config should store window_pos_x / window_pos_y in the ini file."""
    def fake_user_config_dir(app_name, author):
        return str(tmp_path / app_name)

    monkeypatch.setattr("utilities.appdirs.user_config_dir", fake_user_config_dir)

    ini_dir = tmp_path / constants.APPLICATION_NAME
    ini_dir.mkdir(parents=True, exist_ok=True)

    # Avoid touching real config loading
    monkeypatch.setattr(settings, "update_from_config_file", lambda path: None)

    bridge = utilities.DawConsoleBridge()

    # First write a minimal config
    bridge.update_configuration_file(
        con_ip="192.0.2.10",
        rptr_ip="192.0.2.20",
        con_send=1111,
        con_rcv=1110,
        fwd_enable=True,
        rpr_send=2222,
        rpr_rcv=2221,
        rptr_snd=3333,
        rptr_rcv=3332,
        name_only=False,
        console_type="DiGiCo",
        daw_type="Reaper",
        always_on_top=False,
        external_control_osc_port=4444,
        external_control_midi_port="MyMidiPort",
        mmc_control_enabled=False,
        allow_loading_while_playing=False,
        cue_list_player=1,
    )

    bridge.update_pos_in_config((123, 456))

    parser = configparser.ConfigParser()
    parser.read(bridge._ini_path)
    main = parser["main"]

    assert main.getint("window_pos_x") == 123
    assert main.getint("window_pos_y") == 456


def test_start_managed_thread_passes_stop_event_when_expected(monkeypatch):
    """start_managed_thread should pass stop_event kwarg only if target accepts it."""

    bridge = utilities.DawConsoleBridge()

    created_threads = []

    class FakeThread:
        def __init__(self, target=None, kwargs=None, daemon=None):
            self.target = target
            self.kwargs = kwargs or {}
            self.daemon = daemon
            created_threads.append(self)

        def start(self):
            # Don't actually run; we just want to inspect construction
            pass

        def join(self, timeout=None):
            pass

    monkeypatch.setattr("utilities.threading.Thread", FakeThread)

    def target_with_stop_event(stop_event):
        # Signature includes stop_event
        pass

    def target_without_stop_event():
        # No stop_event parameter
        pass

    # Act
    bridge.start_managed_thread("with_stop_event", target_with_stop_event)
    bridge.start_managed_thread("without_stop_event", target_without_stop_event)

    # Assert
    assert len(created_threads) == 2

    thread_with = created_threads[0]
    thread_without = created_threads[1]

    # First thread should receive stop_event in kwargs
    assert "stop_event" in thread_with.kwargs
    assert isinstance(thread_with.kwargs["stop_event"], threading.Event)
    assert thread_with.daemon is True

    # Second thread should not have stop_event in kwargs
    assert thread_without.kwargs == {}
    assert thread_without.daemon is True

def test_close_servers_signals_shutdown_and_joins_threads(monkeypatch):
    """close_servers should set the shutdown event, publish SHUTDOWN_SERVERS, and join all threads."""

    bridge = utilities.DawConsoleBridge()

    # Track pubsub messages
    sent_messages = []

    def fake_send_message(topic, **kwargs):
        sent_messages.append((topic, kwargs))

    monkeypatch.setattr("utilities.pub.sendMessage", fake_send_message)

    # Prepare some fake threads
    class FakeThread:
        def __init__(self, name, alive=True):
            self.name = name
            self._alive = alive
            self.join_called_with = None

        def join(self, timeout=None):
            self.join_called_with = timeout
            # Simulate thread stopping after join
            self._alive = False

        def is_alive(self):
            return self._alive

        def __repr__(self):
            return f"<FakeThread {self.name}>"

    t1 = FakeThread("t1")
    t2 = FakeThread("t2")
    bridge._threads = [t1, t2]

    # Act
    result = bridge.close_servers()

    # Assert: shutdown flag is set
    assert bridge._shutdown_server_event.is_set()

    # SHUTDOWN_SERVERS should have been sent exactly once
    assert sent_messages == [(PyPubSubTopics.SHUTDOWN_SERVERS, {})]

    # All threads should have been joined with the configured timeout
    assert t1.join_called_with == constants.THREAD_JOIN_TIMEOUT
    assert t2.join_called_with == constants.THREAD_JOIN_TIMEOUT

    # And removed from _threads because they are no longer alive
    assert bridge._threads == []

    # close_servers returns True on completion
    assert result is True

def test_shutdown_and_restart_servers_runs_in_background_when_as_thread(monkeypatch):
    """shutdown_and_restart_servers(as_thread=True) should spawn a new thread and not block."""

    bridge = utilities.DawConsoleBridge()

    started = []

    class FakeThread:
        def __init__(self, target=None, args=None):
            self.target = target
            self.args = args
            started.append(self)

        def start(self):
            # Do not actually call target; we just want to ensure it’s scheduled
            pass

    monkeypatch.setattr("utilities.threading.Thread", FakeThread)

    # Act
    bridge.shutdown_and_restart_servers(as_thread=True)

    # Assert: one thread created targeting shutdown_and_restart_servers
    assert len(started) == 1
    assert started[0].target == bridge.shutdown_and_restart_servers
    assert started[0].args == (False,)


def test_shutdown_and_restart_servers_calls_close_and_restart(monkeypatch):
    """shutdown_and_restart_servers(as_thread=False) should call close_servers then restart_servers under a lock."""

    bridge = utilities.DawConsoleBridge()

    calls = []

    def fake_close_servers():
        calls.append("close")
        return True

    def fake_restart_servers():
        calls.append("restart")

    monkeypatch.setattr(bridge, "close_servers", fake_close_servers)
    monkeypatch.setattr(bridge, "restart_servers", fake_restart_servers)

    # Sanity check: lock starts unlocked
    assert not bridge._server_restart_lock.locked()

    # Act
    bridge.shutdown_and_restart_servers(as_thread=False)

    # Assert order: close then restart
    assert calls == ["close", "restart"]
    # Lock should not be left held
    assert not bridge._server_restart_lock.locked()