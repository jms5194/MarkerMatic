from enum import StrEnum, auto

APPLICATION_NAME = "MarkerMatic"
APPLICATION_NAME_LEGACY = "Digico-Reaper Link"
APPLICATION_AUTHOR = "Justin Stasiw"
APPLICATION_DESCRIPTION = (
    "A tool to automate cueing and marker placement between consoles and DAWs"
)
APPLICATION_COPYRIGHT = "© 2025 Justin Stasiw and Liam Steckler"
BUNDLE_IDENTIFIER = "com.justinstasiw.markermatic"
CONFIG_FILENAME = "settings.ini"
CONFIG_FILENAME_LEGACY = "settingsV3.ini"
ICON_MAC_FILENAME = "markermaticicon.icns"
ICON_WIN_FILENAME = "markermaticicon.ico"
LOG_FILENAME = "MarkerMatic.log"
VERSION = "4.3.0 (Build 1019)"
VERSION_EXTRA = "4.3.0.1019"
VERSION_SHORT = "4.3.0"
WEBSITE = "https://markermatic.com"
WEBSITE_DOCUMENTATION = "https://markermatic.com/docs"
WEBSITE_LICENSE = "https://markermatic.com/license"

CONNECTION_RECONNECTION_DELAY_SECONDS = 5
CONNECTION_TIMEOUT_SECONDS = 2
MESSAGE_TIMEOUT_SECONDS = 5
HIGHEST_THREAD_TIMEOUT = max(
    CONNECTION_RECONNECTION_DELAY_SECONDS,
    CONNECTION_TIMEOUT_SECONDS,
    MESSAGE_TIMEOUT_SECONDS,
)
THREAD_JOIN_TIMEOUT = HIGHEST_THREAD_TIMEOUT * 2

CHECK_CONNECTION_TIME = 10
CHECK_CONNECTION_TIMEOUT = 2
CHECK_CONNECTION_TIME_COMBINED = CHECK_CONNECTION_TIME + CHECK_CONNECTION_TIMEOUT

IP_LISTEN_ANY = ""
IP_LOOPBACK = "127.0.0.1"
IP_OUTBOUND_ANY = "0.0.0.0"

MAX_IP_LENGTH = 45

MIDI_PORT_NONE = "None"

PORT_STUDER_EMBER_RECEIVE = 49104

WXPYTHON_USE_NATIVE_BUTTONS = False

SPARKLE_BASE_URL = "https://markermatic.com/updates"
SPARKLE_MAC_ARM64_URL = f"{SPARKLE_BASE_URL}/macos-arm64-appcast.xml"
SPARKLE_MAC_X64_URL = f"{SPARKLE_BASE_URL}/macos-x64-appcast.xml"
SPARKLE_WIN_X64_URL = f"{SPARKLE_BASE_URL}/win-x64-appcast.xml"

SPARKLE_PUBLIC_ED_KEY = "Y6lCSD9GlDM0vOV2ZVVhNE1P9C4WDOPQeM0qzhuIRew="


class PlaybackState(StrEnum):
    RECORDING = "recording"
    PLAYBACK_TRACK = "playback-track"
    PLAYBACK_NO_TRACK = "playback-no-track"


class TransportAction(StrEnum):
    PLAY = "play"
    STOP = "stop"
    RECORD = "record"


class PyPubSubTopics(StrEnum):
    REQUEST_DAW_RESTART = auto()
    UPDATE_MAIN_WINDOW_DISPLAY_SETTINGS = auto()
    SHUTDOWN_SERVERS = auto()
    HANDLE_CUE_LOAD = auto()
    CONSOLE_CONNECTED = auto()
    CONSOLE_DISCONNECTED = auto()
    CHANGE_PLAYBACK_STATE = auto()
    PLACE_MARKER_WITH_NAME = auto()
    DAW_CONNECTION_STATUS = auto()
    TRANSPORT_ACTION = auto()
