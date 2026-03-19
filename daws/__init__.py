from .daw import Daw, DawFeature
from .reaper import Reaper
from .protools import ProTools
from .ardour import Ardour
from .bitwig import Bitwig
from .digitalperformer import DigitalPerformer

DAWS = {
    "Reaper": Reaper,
    "ProTools": ProTools,
    "Ardour": Ardour,
    "Bitwig Studio": Bitwig,
    "Digital Performer": DigitalPerformer,
}


__all__ = ["Daw", "DawFeature", "Reaper", "ProTools", "Ardour", "Bitwig"]
