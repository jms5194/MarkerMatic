import os
import shutil
import xml.etree.ElementTree
from logger_config import logger
import psutil
import sys
import xml.etree.ElementTree as ET
import time


def backup_config_file(config_file_path):
    # Backup config state before this software modified it.
    config_file_path = config_file_path + "/" + "config"
    before_file = config_file_path + ".before.bak"
    if not os.path.exists(before_file):
        shutil.copy(config_file_path, before_file)
    logger.info("Backing up original Ardour config file")
    # Backup current config
    shutil.copy(config_file_path, config_file_path + ".bak")
    logger.info("Backing up current Ardour config file")


def enable_osc_interface(resource_path):
    # Parse the XML configuration document
    try:
        while get_ardour_process_path() is not None:
            time.sleep(1.0)
    except RuntimeError:
        backup_config_file(resource_path)
        config_path = os.path.join(resource_path, "config")
        config = ET.parse(config_path)
        root = config.getroot()
        osc_config = root.find(
            "./ControlProtocols/Protocol[@name='Open Sound Control (OSC)']"
        )
        assert isinstance(osc_config, xml.etree.ElementTree.Element)
        osc_config.attrib["active"] = "1"
        config.write(config_path)
        logger.info("Wrote an updated Ardour config file with OSC enabled")


def osc_interface_exists(resource_path):
    config = ET.parse(os.path.join(resource_path, "config"))
    root = config.getroot()
    try:
        osc_config = root.find(
            "./ControlProtocols/Protocol[@name='Open Sound Control (OSC)']"
        )
    except xml.etree.ElementTree.ParseError as e:
        logger.error(f"Error parsing Ardour config: {e}")
        return False
    assert isinstance(osc_config, xml.etree.ElementTree.Element)
    try:
        if osc_config.attrib["active"] == "1":
            return True
        else:
            logger.info("OSC interface is not active")
            return False
    except KeyError:
        logger.error("Ardour config is missing keys")
        return False


def get_resource_path(detect_portable_install):
    for i in get_candidate_directories(detect_portable_install):
        if i is not None:
            if os.path.exists(os.path.join(i, "config")):
                return i
    raise RuntimeError("Cannot find resource path")


def get_candidate_directories(detect_portable_install):
    if detect_portable_install:
        yield get_portable_resource_directory()
    if is_apple():
        yield os.path.expanduser("~/Library/Preferences/ardour8")
    elif is_windows():
        yield os.path.expandvars(r"$LOCALAPPDATA\ardour8")
    else:
        yield os.path.expanduser("~/.config/ardour8")


def get_portable_resource_directory():
    try:
        process_path = get_ardour_process_path()
        if is_apple():
            return "/".join(process_path.split("/")[:-4])
        return os.path.dirname(process_path)
    except Exception as e:
        logger.info(f"Error getting portable resource directory: {e}")
        return None


def is_apple() -> bool:
    """Return whether OS is macOS or OSX."""
    return sys.platform == "darwin"


def is_windows() -> bool:
    """Return whether OS is Windows."""
    return os.name == "nt"


def get_ardour_process_path():
    # Return path to currently running Ardour8 process.
    # TODO: Fix this to work with other Ardour versions
    # (e.g. Ardour7, Ardour6, etc.)
    processes = [
        p
        for p in psutil.process_iter(["name", "exe"])
        if os.path.splitext(
            p.info["name"]  # type:ignore
        )[0].lower()
        in ["ardour8", "ardourgui"]
    ]
    if not processes:
        raise RuntimeError("No Ardour instance is currently running.")
    elif len(processes) > 1:
        raise RuntimeError("More than one Ardour instance is currently running.")
    return processes[0].info["exe"]  # type:ignore
