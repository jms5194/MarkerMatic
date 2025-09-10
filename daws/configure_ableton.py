import os
import pathlib
import shutil
import sys
from filecmp import dircmp

import utilities
from logger_config import logger


def verify_markermatic_bridge_in_user_dir():
    # Copy the Markermatic Bridge to the Ableton extensions directory
    check_available_dir = get_ableton_scripts_path()
    if check_available_dir.is_dir():
        pass
    else:
        check_available_dir.mkdir(exist_ok=True)
    bridge_full_path = get_ableton_scripts_path() / "AbletonOSC"
    logger.info(f"Checking for the AbletonOSC extension at {bridge_full_path}")
    source_loc = pathlib.Path(utilities.get_resources_directory_path())
    source_path = source_loc / "AbletonOSC"

    if os.path.exists(get_ableton_scripts_path()):
        if os.path.exists(bridge_full_path):
            # Need to add logic here to compare the bundled directory with the
            # directory on the user's computer to make sure they are the same
            pass
    else:
        os.makedirs(get_ableton_scripts_path(), exist_ok=True)
        copy_ableton_osc_script_to_user_folder(source_path)
        return False

def copy_ableton_osc_script_to_user_folder(package_file):
    destination_directory = get_ableton_scripts_path()
    filename = os.path.basename(package_file)
    destination_path = os.path.join(destination_directory, filename)
    if os.path.exists(destination_path):
        os.remove(destination_path)
    shutil.copy(package_file, destination_path)
    logger.info(f"Extension '{filename}' copied or replaced successfully.")
    logger.info("Copied Markermatic Bridge to Bitwig extensions directory.")


def get_ableton_scripts_path() -> pathlib.Path:
    # Return the path to the Bitwig extensions directory based on the OS
    if is_apple():
        return pathlib.Path.home() / "Documents" / "Music" / "Ableton" / "Extensions" / "Remote Scripts"
    elif is_windows():
        return pathlib.Path.home() / "Documents" / "Ableton" / "User Library" / "Remote Scripts"
    else:
        return pathlib.Path.home()


def is_apple() -> bool:
    """Return whether OS is macOS or OSX."""
    return sys.platform == "darwin"


def is_windows() -> bool:
    """Return whether OS is Windows."""
    return sys.platform == "win32"


def calculate_md5_checksum(file_path):
    """Calculates the MD5 checksum of a given file."""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:  # Open in binary read mode
        while True:
            chunk = f.read(8192)  # Read in chunks for large files
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()
