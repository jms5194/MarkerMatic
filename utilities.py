import inspect
import ipaddress
import os.path
import platform
import threading
import time
from typing import Callable, List

import appdirs
from configupdater import ConfigUpdater
from pubsub import pub

import constants
import external_control
from app_settings import settings
from consoles import CONSOLES, Console
from constants import PyPubSubTopics, TransportAction
from daws import DAWS, Daw
from logger_config import logger


def get_ip_listen_any(ip: str) -> str:
    """Given a target device IP, returns the IP that should be bound to"""
    address = ipaddress.ip_address(ip)
    # If the IP is a loopback, listening on INADDR_ANY will fail on some OSes
    # (observed on Windows). Listening on the loopback address doesn't
    if address.is_loopback:
        return ip
    else:
        return constants.IP_LISTEN_ANY


class DawConsoleBridge:
    _console: Console
    _threads: List[threading.Thread] = list()

    def __init__(self):
        logger.info(f"Initializing DawConsoleBridge, Version {constants.VERSION}")
        logger.info(f"Platform: {platform.platform()}")
        self._shutdown_server_event = threading.Event()
        self._server_restart_lock = threading.Lock()
        self._console = Console()
        self._daw = Daw()

        # The path to the legacy (v3) configuration file, we only read this
        self._legacy_ini_path = os.path.join(
            appdirs.user_config_dir(
                constants.APPLICATION_NAME_LEGACY, constants.APPLICATION_AUTHOR
            ),
            constants.CONFIG_FILENAME_LEGACY,
        )
        # The folder that the current configuration file is saved in
        ini_folder = appdirs.user_config_dir(
            constants.APPLICATION_NAME, constants.APPLICATION_AUTHOR
        )
        self._ini_path = os.path.join(
            ini_folder,
            constants.CONFIG_FILENAME,
        )
        if not os.path.isdir(ini_folder):
            os.makedirs(ini_folder)
        self.check_configuration()
        pub.setListenerExcHandler(ListenerExceptionHandler())
        pub.subscribe(log_transport_action, PyPubSubTopics.TRANSPORT_ACTION)

    def check_configuration(self):
        "Check for a configuration file, and load settings from it"
        try:
            if os.path.isfile(self._ini_path):
                settings.update_from_config_file(self._ini_path)
            elif os.path.isfile(self._legacy_ini_path):
                logger.info("Loading settings from legacy (v3) ini")
                settings.update_from_config_file(self._legacy_ini_path)
        except Exception as e:
            logger.error(f"Failed to check/initialize config file: {e}")

    def update_configuration_file(
        self,
        con_ip,
        rptr_ip,
        con_send,
        con_rcv,
        fwd_enable,
        rpr_send,
        rpr_rcv,
        rptr_snd,
        rptr_rcv,
        name_only,
        console_type,
        daw_type,
        always_on_top,
        external_control_osc_port,
        external_control_midi_port,
        mmc_control_enabled,
        allow_loading_while_playing,
        cue_list_player,
    ):
        "Update the configuration files with new values"
        # TODO: This can likely re-use the mapping that's used for reading the config file and loop through properties
        logger.info("Updating configuration file")
        updater = ConfigUpdater()
        try:
            updater.read(self._ini_path)
        except FileNotFoundError:
            pass
        try:
            if not updater.has_section("main"):
                logger.info("Adding main section to config file")
                updater.add_section("main")
            updater["main"]["default_ip"] = con_ip
            updater["main"]["repeater_ip"] = rptr_ip
            updater["main"]["default_digico_send_port"] = str(con_send)
            updater["main"]["default_digico_receive_port"] = str(con_rcv)
            updater["main"]["default_reaper_send_port"] = str(rpr_send)
            updater["main"]["default_reaper_receive_port"] = str(rpr_rcv)
            updater["main"]["default_repeater_send_port"] = str(rptr_snd)
            updater["main"]["default_repeater_receive_port"] = str(rptr_rcv)
            updater["main"]["forwarder_enabled"] = str(fwd_enable)
            updater["main"]["name_only_match"] = str(name_only)
            updater["main"]["console_type"] = str(console_type)
            updater["main"]["daw_type"] = str(daw_type)
            updater["main"]["always_on_top"] = str(always_on_top)
            updater["main"]["external_control_osc_port"] = str(
                external_control_osc_port
            )
            updater["main"]["external_control_midi_port"] = str(
                external_control_midi_port
            )
            updater["main"]["mmc_control_enabled"] = str(mmc_control_enabled)
            updater["main"]["allow_loading_while_playing"] = str(
                allow_loading_while_playing
            )
            updater["main"]["cue_list_player"] = str(cue_list_player)
        except Exception as e:
            logger.error(f"Failed to update config file: {e}")
        with open(self._ini_path, "w") as file:
            updater.write(file, validate=False)
        settings.update_from_config_file(self._ini_path)

    def update_pos_in_config(self, win_pos_tuple):
        # Receives the position of the window from the UI and stores it in the preferences file
        logger.info("Updating window position in config file")
        updater = ConfigUpdater()
        try:
            updater.read(self._ini_path)
        except FileNotFoundError:
            pass
        try:
            if not updater.has_section("main"):
                logger.info("Adding main section to config file")
                updater.add_section("main")
            updater.set("main", "window_pos_x", str(win_pos_tuple[0]))
            updater.set("main", "window_pos_y", str(win_pos_tuple[1]))
        except Exception as e:
            logger.error(f"Failed to update window position in config file: {e}")
        with open(self._ini_path, "w") as file:
            updater.write(file, validate=False)

    def start_managed_thread(self, attr_name: str, target: Callable) -> None:
        if "stop_event" in inspect.getargs(target.__code__).args:
            kwargs = {"stop_event": self._shutdown_server_event}
        else:
            kwargs = None
        thread = threading.Thread(target=target, kwargs=kwargs, daemon=True)
        self._threads.append(thread)
        thread.start()

    def start_threads(self):
        # Start all OSC server threads, reinstantiating DAW and Console connections
        logger.info("Starting threads")
        if settings.daw_type in DAWS:
            daw_type = DAWS[settings.daw_type]
            self.daw = daw_type()
            self.daw.start_managed_threads(self.start_managed_thread)
        else:
            logger.error("DAW is not supported!")
        self.start_managed_thread("heartbeat_thread", self.heartbeat_loop)
        if settings.console_type in CONSOLES:
            console_type = CONSOLES[settings.console_type]
            self.console = console_type()
            self.console.start_managed_threads(self.start_managed_thread)
        else:
            logger.error("Console is not supported!")
        self.start_managed_thread(
            "external_osc_control", external_control.external_osc_control
        )
        self.start_managed_thread(
            "external_midi_control", external_control.external_midi_control
        )

    _console_lock = threading.Lock()

    @property
    def console(self) -> Console:
        with self._console_lock:
            return self._console

    @console.setter
    def console(self, value: Console) -> None:
        with self._console_lock:
            self._console = value
        pub.sendMessage(PyPubSubTopics.CONSOLE_DISCONNECTED)

    _daw_lock = threading.Lock()

    @property
    def daw(self) -> Daw:
        with self._daw_lock:
            return self._daw

    @daw.setter
    def daw(self, value: Daw) -> None:
        with self._daw_lock:
            self._daw = value
        pub.sendMessage(PyPubSubTopics.DAW_CONNECTION_STATUS, daw=value)

    # Console Functions:

    def heartbeat_loop(self):
        # Periodically requests the console name every 3 seconds
        # to verify connection status and update the UI
        while not self._shutdown_server_event.is_set():
            try:
                if isinstance(self.console, Console):
                    self.console.heartbeat()
            except Exception as e:
                logger.error(f"Console Heartbeat loop error: {e}")
                pub.sendMessage(PyPubSubTopics.CONSOLE_DISCONNECTED)
            time.sleep(3)

    def stop_all_threads(self):
        logger.info("Stopping all threads")
        for thread in self._threads:
            thread.join(timeout=constants.THREAD_JOIN_TIMEOUT)
            # Only remove threads that managed to shut down
            if not thread.is_alive():
                self._threads.remove(thread)
            else:
                logger.warning(f"Thread {thread} didn't stop in time")

    def close_servers(self):
        logger.info("Closing OSC servers...")
        self._shutdown_server_event.set()  # Signal heartbeat to exit
        pub.sendMessage(PyPubSubTopics.SHUTDOWN_SERVERS)
        self.stop_all_threads()
        logger.info("All servers closed and threads joined.")
        return True

    def restart_servers(self):
        logger.info("Restarting server threads")
        self._shutdown_server_event.clear()
        self.start_threads()

    def shutdown_and_restart_servers(self, as_thread: bool = True) -> None:
        if as_thread:
            threading.Thread(
                target=self.shutdown_and_restart_servers, args=(False,)
            ).start()
            return
        else:
            with self._server_restart_lock:
                self.close_servers()
                self.restart_servers()

    def attempt_reconnect(self):
        logger.info("Manual reconnection requested")
        self.shutdown_and_restart_servers()


class ListenerExceptionHandler(pub.IListenerExcHandler):
    def __call__(self, listenerID, topicObj):
        logger.error(
            "While processing a PubSub, %s threw an exception %s", listenerID, topicObj
        )


def log_transport_action(transport_action: TransportAction) -> None:
    logger.info(f"{transport_action} transport action requested")


def get_resources_directory_path() -> str:
    py2app_resource_path = os.environ.get("RESOURCEPATH")
    if py2app_resource_path is not None:
        return py2app_resource_path
    return os.path.join(os.path.dirname(__file__), "resources")
