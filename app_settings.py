import configparser
import threading
from configparser import ConfigParser
from logging import Logger

import constants
from logger_config import logger


class ThreadSafeSettings:
    def __init__(self):
        self._lock = threading.Lock()
        self._settings = {
            "console_ip": "192.0.2.11",
            "repeater_ip": "192.0.2.21",
            "repeater_port": 9999,
            "repeater_receive_port": 9998,
            "reaper_port": 49102,
            "reaper_receive_port": 49101,
            "console_port": 8001,
            "receive_port": 8000,
            "forwarder_enabled": False,
            "marker_mode": constants.PlaybackState.PLAYBACK_TRACK,
            "window_loc": (400, 222),
            "name_only_match": False,
            "console_type": "Digico",
            "daw_type": "Reaper",
            "always_on_top": False,
            "mmc_control_enabled": False,
            "external_control_osc_port": 49103,
            "external_control_midi_port": constants.MIDI_PORT_NONE,
            "allow_loading_while_playing": False,
            "cue_list_player": 1,
        }

    @property
    def console_ip(self) -> str:
        with self._lock:
            return self._settings["console_ip"]

    @console_ip.setter
    def console_ip(self, value):
        with self._lock:
            self._settings["console_ip"] = value

    @property
    def repeater_ip(self) -> str:
        with self._lock:
            return self._settings["repeater_ip"]

    @repeater_ip.setter
    def repeater_ip(self, value):
        with self._lock:
            self._settings["repeater_ip"] = value

    @property
    def repeater_port(self) -> int:
        with self._lock:
            return self._settings["repeater_port"]

    @repeater_port.setter
    def repeater_port(self, value):
        with self._lock:
            port_num = int(value)
            if not validate_port_num(port_num):
                raise ValueError("Invalid port number")
            self._settings["repeater_port"] = port_num

    @property
    def repeater_receive_port(self) -> int:
        with self._lock:
            return self._settings["repeater_receive_port"]

    @repeater_receive_port.setter
    def repeater_receive_port(self, value):
        with self._lock:
            port_num = int(value)
            if not validate_port_num(port_num):
                raise ValueError("Invalid port number")
            self._settings["repeater_receive_port"] = port_num

    @property
    def reaper_port(self) -> int:
        with self._lock:
            return self._settings["reaper_port"]

    @reaper_port.setter
    def reaper_port(self, value):
        with self._lock:
            port_num = int(value)
            if not validate_port_num(port_num):
                raise ValueError("Invalid port number")
            self._settings["reaper_port"] = port_num

    @property
    def reaper_receive_port(self) -> int:
        with self._lock:
            return self._settings["reaper_receive_port"]

    @reaper_receive_port.setter
    def reaper_receive_port(self, value):
        with self._lock:
            port_num = int(value)
            if not validate_port_num(port_num):
                raise ValueError("Invalid port number")
            self._settings["reaper_receive_port"] = port_num

    @property
    def console_port(self) -> int:
        with self._lock:
            return self._settings["console_port"]

    @console_port.setter
    def console_port(self, value):
        with self._lock:
            port_num = int(value)
            if not validate_port_num(port_num):
                raise ValueError("Invalid port number")
            self._settings["console_port"] = port_num

    @property
    def receive_port(self) -> int:
        with self._lock:
            return self._settings["receive_port"]

    @receive_port.setter
    def receive_port(self, value):
        with self._lock:
            port_num = int(value)
            if not validate_port_num(port_num):
                raise ValueError("Invalid port number")
            self._settings["receive_port"] = port_num

    @property
    def forwarder_enabled(self) -> bool:
        with self._lock:
            return self._settings["forwarder_enabled"]

    @forwarder_enabled.setter
    def forwarder_enabled(self, value):
        with self._lock:
            self._settings["forwarder_enabled"] = value

    @property
    def marker_mode(self) -> constants.PlaybackState:
        with self._lock:
            return self._settings["marker_mode"]

    @marker_mode.setter
    def marker_mode(self, value: constants.PlaybackState):
        with self._lock:
            self._settings["marker_mode"] = value

    @property
    def window_loc(self):
        with self._lock:
            return self._settings["window_loc"]

    @window_loc.setter
    def window_loc(self, value):
        with self._lock:
            self._settings["window_loc"] = value

    @property
    def name_only_match(self) -> bool:
        with self._lock:
            return self._settings["name_only_match"]

    @name_only_match.setter
    def name_only_match(self, value):
        with self._lock:
            self._settings["name_only_match"] = value

    @property
    def console_type(self) -> str:
        with self._lock:
            return self._settings["console_type"]

    @console_type.setter
    def console_type(self, value):
        with self._lock:
            self._settings["console_type"] = value

    @property
    def daw_type(self) -> str:
        with self._lock:
            return self._settings["daw_type"]

    @daw_type.setter
    def daw_type(self, value):
        with self._lock:
            self._settings["daw_type"] = value

    @property
    def always_on_top(self) -> bool:
        with self._lock:
            return self._settings["always_on_top"]

    @always_on_top.setter
    def always_on_top(self, value):
        with self._lock:
            self._settings["always_on_top"] = value

    @property
    def mmc_control_enabled(self) -> bool:
        with self._lock:
            return self._settings["mmc_control_enabled"]

    @mmc_control_enabled.setter
    def mmc_control_enabled(self, value: bool):
        with self._lock:
            self._settings["mmc_control_enabled"] = value

    @property
    def external_control_osc_port(self) -> int:
        with self._lock:
            return self._settings["external_control_osc_port"]

    @external_control_osc_port.setter
    def external_control_osc_port(self, value: int):
        with self._lock:
            port_num = int(value)
            if not validate_port_num(port_num):
                raise ValueError("Invalid port number")
            self._settings["external_control_osc_port"] = port_num

    @property
    def external_control_midi_port(self) -> str:
        with self._lock:
            return self._settings["external_control_midi_port"]

    @external_control_midi_port.setter
    def external_control_midi_port(self, value: str):
        with self._lock:
            self._settings["external_control_midi_port"] = value

    @property
    def allow_loading_while_playing(self) -> bool:
        with self._lock:
            return self._settings["allow_loading_while_playing"]

    @allow_loading_while_playing.setter
    def allow_loading_while_playing(self, value: bool):
        with self._lock:
            self._settings["allow_loading_while_playing"] = value

    @property
    def cue_list_player(self) -> int:
        with self._lock:
            return self._settings["cue_list_player"]

    @cue_list_player.setter
    def cue_list_player(self, value: int):
        with self._lock:
            cue_list_player_num = int(value)
            if not validate_cue_list_player(cue_list_player_num):
                raise ValueError("Invalid ControlPointAddress for CueListPlayer")
            self._settings["cue_list_player"] = cue_list_player_num

    def update_from_config_file(self, path: str) -> None:
        """Updates the currently loaded settings from the contents of the config file"""
        logger.info("Loading settings from config file")
        config = configparser.ConfigParser()
        config.read(path)
        self.update_from_config(config)

    def update_from_config(self, config: ConfigParser):
        # Update settings from a ConfigParser object
        with self._lock:
            string_properties = {
                "console_ip": "default_ip",
                "repeater_ip": "repeater_ip",
                "console_type": "console_type",
                "daw_type": "daw_type",
                "external_control_midi_port": "external_control_midi_port",
            }
            for settings_name, config_name in string_properties.items():
                self._settings[settings_name] = config.get(
                    "main", config_name, fallback=self._settings[settings_name]
                )

            int_properties = {
                "console_port": "default_digico_send_port",
                "receive_port": "default_digico_receive_port",
                "reaper_port": "default_reaper_send_port",
                "repeater_port": "default_repeater_send_port",
                "repeater_receive_port": "default_repeater_receive_port",
                "reaper_receive_port": "default_reaper_receive_port",
                "external_control_osc_port": "external_control_osc_port",
                "cue_list_player": "cue_list_player",
            }
            for settings_name, config_name in int_properties.items():
                self._settings[settings_name] = config.getint(
                    "main", config_name, fallback=self._settings[settings_name]
                )

            boolean_properties = {
                "forwarder_enabled": "forwarder_enabled",
                "name_only_match": "name_only_match",
                "always_on_top": "always_on_top",
                "mmc_control_enabled": "mmc_control_enabled",
                "allow_loading_while_playing": "allow_loading_while_playing",
            }
            for settings_name, config_name in boolean_properties.items():
                self._settings[settings_name] = config.getboolean(
                    "main", config_name, fallback=self._settings[settings_name]
                )

            # Not implementing fallbacks for this since it's been around since the v3 config
            try:
                self._settings.update(
                    {
                        "window_loc": (
                            int(config["main"]["window_pos_x"]),
                            int(config["main"]["window_pos_y"]),
                        )
                    }
                )
            except Exception as e:
                logger.warning("Could not load setting %s. %s", settings_name, e)
            self.log_settings()

    def log_settings(self, logger: Logger = logger) -> None:
        """Logs the current settings values, useful for troubleshooting"""
        logger.info("Current application settings:")
        max_length = max(len(setting) for setting in self._settings)
        for setting in self._settings:
            logger.info(
                f"{setting:>{max_length}.{max_length}}: {self._settings[setting]}"
            )


settings = ThreadSafeSettings()


def validate_port_num(port_num: int) -> bool:
    return 1 <= port_num <= 65535


def validate_cue_list_player(cue_list_player_num: int) -> bool:
    """Validate that a Cue List Player's index is a valid human-readable/display value, between 1 and 127, inclusive"""
    return 1 <= cue_list_player_num <= 127
