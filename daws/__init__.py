from .daw import Daw
from .reaper import Reaper
from .protools import ProTools
from .ardour import Ardour
from .bitwig import Bitwig
from .abletonlive import Ableton

DAWS = {
    "Reaper": Reaper,
    "ProTools": ProTools,
    "Ardour": Ardour,
    "Bitwig Studio": Bitwig,
    "AbletonLive": Ableton,
}


__all__ = ["Daw", "Reaper", "ProTools", "Ardour", "Bitwig", "Ableton"]
