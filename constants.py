import datetime
from enum import StrEnum, auto

APPLICATION_NAME = "MarkerMatic"
APPLICATION_NAME_LEGACY = "Digico-Reaper Link"
APPLICATION_AUTHOR = "Justin Stasiw"
APPLICATION_DESCRIPTION = (
    "A tool to automate cueing and marker placement between consoles and DAWs"
)
APPLICATION_COPYRIGHT = "© {} Justin Stasiw and Liam Steckler".format(
    datetime.datetime.now().year
)
BUNDLE_IDENTIFIER = "com.justinstasiw.markermatic"
CREDITS = "Solar Icons by 480 Design is licensed under CC BY 4.0"
CONFIG_FILENAME = "settings.ini"
CONFIG_FILENAME_LEGACY = "settingsV3.ini"
LOG_FILENAME = "MarkerMatic.log"
VERSION = "4.0.0"
WEBSITE = "https://markermatic.com"

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

IP_LISTEN_ALL = ""
IP_LOOPBACK = "127.0.0.1"
IP_OUTBOUND_ANY = "0.0.0.0"

MIDI_PORT_NONE = "None"

PORT_STUDER_EMBER_RECEIVE = 49104

WXPYTHON_USE_NATIVE_BUTTONS = False


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
