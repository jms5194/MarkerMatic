from .daw import Daw
from .reaper import Reaper
from .protools import ProTools
from .ardour import Ardour
from .bitwig import Bitwig

DAWS = {
    "Reaper": Reaper,
    "ProTools": ProTools,
    "Ardour": Ardour,
    "Bitwig Studio": Bitwig,
}


__all__ = ["Daw", "Reaper", "ProTools", "Ardour", "Bitwig"]
